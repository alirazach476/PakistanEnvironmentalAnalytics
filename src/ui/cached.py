"""Cached analysis results keyed by the (hashable) global filter values."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from src.analysis import descriptive, sensitivity, statistical_tests as st_tests, trends
from src.analysis.correlations import city_correlations, correlation_matrix, lagged_correlation
from src.ui.common import _filtered, get, independent

WEATHER_X = ["temperature", "humidity", "wind_speed", "precipitation", "pressure", "dew_point"]


def _wb(fk: tuple) -> pd.DataFrame:
    get("wb_daily")
    return _filtered("wb_daily", *fk)


def key(f: dict) -> tuple:
    return (f["start"], f["end"], f["provinces"], f["seasons"], f["no_outliers"], f.get("no_artifacts", False))


@st.cache_data(show_spinner="Summarising cities…", max_entries=8)
def city_summary(fk: tuple) -> pd.DataFrame:
    df = _wb(fk)
    if df.empty:
        return pd.DataFrame()
    s = descriptive.city_summary(df)
    p = df.groupby("city_id", observed=True)["pm25"].quantile([0.05, 0.25, 0.75]).unstack()
    p.columns = ["p5", "p25", "p75"]
    return s.merge(p.reset_index(), on="city_id", how="left")


@st.cache_data(show_spinner="Estimating trends for every city…", max_entries=8)
def city_trends(fk: tuple) -> pd.DataFrame:
    df = _wb(fk)
    return trends.city_trends(df) if not df.empty else pd.DataFrame()


@st.cache_data(show_spinner=False, max_entries=8)
def monthly_all(fk: tuple) -> pd.DataFrame:
    df = _wb(fk)
    return trends.monthly_series(df) if not df.empty else pd.DataFrame()


@st.cache_data(show_spinner="Running statistical tests…", max_entries=8)
def test_battery(fk: tuple) -> list:
    df = _wb(fk)
    if df.empty:
        return []
    iu = independent(df)
    years = trends.complete_years(iu)
    city_level = iu.groupby(["city_id", "province"], observed=True)["pm25"].median().reset_index()
    city_mean = iu.groupby(["city_id", "province"], observed=True)["pm25"].mean().reset_index()
    out = [st_tests.seasonal_friedman(iu), st_tests.group_kruskal(city_level, "pm25"),
           st_tests.group_anova_if_justified(city_mean, "pm25"), st_tests.weekday_weekend_test(iu)]
    if len(years) >= 2:
        out.append(st_tests.period_change_test(trends.annual_series(iu), years[0], years[-1]))
    ww = _filtered("wb_weather_daily", fk[0], fk[1], fk[2], fk[3], False, fk[5])
    if not ww.empty:
        for x in ("temperature", "humidity", "wind_speed", "precipitation"):
            out.append(st_tests.weather_correlation_test(ww, x, deseasonalize=True))
    return out


@st.cache_data(show_spinner="Running sensitivity scenarios…", max_entries=4)
def sensitivity_tables(fk: tuple) -> tuple[pd.DataFrame, pd.DataFrame]:
    df = _wb(fk)
    if df.empty:
        return pd.DataFrame(), pd.DataFrame()
    cities = get("wb_cities")
    return sensitivity.scenario_metrics(df, cities), sensitivity.ranking_under_scenarios(df, cities, top_n=8)


@st.cache_data(show_spinner="Computing correlations…", max_entries=16)
def weather_corr(fk: tuple, x: str, deseasonalize: bool) -> pd.DataFrame:
    ww = _filtered("wb_weather_daily", fk[0], fk[1], fk[2], fk[3], False, fk[5])
    return city_correlations(ww, x, "pm25", "spearman", deseasonalize=deseasonalize) if not ww.empty else pd.DataFrame()


@st.cache_data(show_spinner="Computing lagged correlations…", max_entries=16)
def weather_lags(fk: tuple, x: str, deseasonalize: bool) -> pd.DataFrame:
    ww = _filtered("wb_weather_daily", fk[0], fk[1], fk[2], fk[3], False, fk[5])
    return lagged_correlation(ww, x, deseasonalize=deseasonalize) if not ww.empty else pd.DataFrame()


@st.cache_data(show_spinner=False, max_entries=16)
def weather_matrix(fk: tuple, deseasonalize: bool) -> tuple[pd.DataFrame, pd.DataFrame]:
    from src.analysis.correlations import add_anomalies
    ww = _filtered("wb_weather_daily", fk[0], fk[1], fk[2], fk[3], False, fk[5])
    if ww.empty:
        return pd.DataFrame(), pd.DataFrame()
    cols = ["pm25"] + [c for c in WEATHER_X if c in ww.columns]
    if deseasonalize:
        ww = add_anomalies(ww, cols)
        cols = [f"{c}_anom" for c in cols]
    return correlation_matrix(ww, cols, "spearman")
