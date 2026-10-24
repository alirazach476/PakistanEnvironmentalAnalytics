"""Seasonal, monthly, weekly and diurnal profiles."""

from __future__ import annotations

import pandas as pd

from src.data.validate import require_columns
from src.utils.config import MONTH_NAMES, SEASON_ORDER

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def temporal_resolution(df: pd.DataFrame, time_col: str = "timestamp", group_col: str = "city_id") -> str:
    """'hourly', 'daily' or 'unknown', from the modal spacing within groups."""
    if time_col not in df.columns or df.empty:
        return "unknown"
    t = pd.to_datetime(df[time_col])
    step = t.groupby(df[group_col], observed=True).diff().dropna()
    if step.empty:
        return "unknown"
    mode = step.mode().iloc[0]
    if mode == pd.Timedelta(hours=1):
        return "hourly"
    if mode == pd.Timedelta(days=1):
        return "daily"
    return "unknown"


def month_city_matrix(df: pd.DataFrame, value: str = "pm25", city_col: str = "city_label",
                      stat: str = "median") -> pd.DataFrame:
    """Rows: cities, columns: calendar months (Jan..Dec) of the chosen statistic."""
    require_columns(df, [value, city_col, "month"])
    m = df.groupby([city_col, "month"], observed=True)[value].agg(stat).unstack("month")
    m = m.reindex(columns=range(1, 13))
    m.columns = MONTH_NAMES
    return m


def seasonal_summary(df: pd.DataFrame, value: str = "pm25", by: str | None = None) -> pd.DataFrame:
    require_columns(df, [value, "season"] + ([by] if by else []))
    keys = ([by] if by else []) + ["season"]
    out = df.groupby(keys, observed=True)[value].agg(
        n="count", mean="mean", median="median", p25=lambda s: s.quantile(0.25),
        p75=lambda s: s.quantile(0.75)).reset_index()
    out["season"] = pd.Categorical(out["season"], categories=SEASON_ORDER, ordered=True)
    return out.sort_values(keys).reset_index(drop=True)


def month_profile(df: pd.DataFrame, value: str = "pm25", by: str | None = None) -> pd.DataFrame:
    """Median and inter-quartile range by calendar month."""
    require_columns(df, [value, "month"] + ([by] if by else []))
    keys = ([by] if by else []) + ["month"]
    out = df.groupby(keys, observed=True)[value].agg(
        median="median", p25=lambda s: s.quantile(0.25), p75=lambda s: s.quantile(0.75), n="count").reset_index()
    out["month_name"] = out["month"].map(lambda m: MONTH_NAMES[m - 1])
    return out


def city_season_medians(df: pd.DataFrame, value: str = "pm25", city_col: str = "city_id") -> pd.DataFrame:
    """Wide table: one row per city, one column per season (median). Unit for paired tests."""
    require_columns(df, [value, city_col, "season"])
    w = df.groupby([city_col, "season"], observed=True)[value].median().unstack("season")
    return w.reindex(columns=[s for s in SEASON_ORDER if s in w.columns])


def weekday_profile(df: pd.DataFrame, value: str = "pm25", by: str | None = None) -> pd.DataFrame:
    require_columns(df, [value, "day_of_week"] + ([by] if by else []))
    keys = ([by] if by else []) + ["day_of_week"]
    out = df.groupby(keys, observed=True)[value].agg(mean="mean", median="median", n="count").reset_index()
    out["day_of_week"] = pd.Categorical(out["day_of_week"], categories=WEEKDAYS, ordered=True)
    return out.sort_values(keys).reset_index(drop=True)


def weekday_weekend_by_city(df: pd.DataFrame, value: str = "pm25", city_col: str = "city_id") -> pd.DataFrame:
    """Per-city mean on weekdays vs weekends (Sat/Sun) and their difference."""
    require_columns(df, [value, city_col, "is_weekend"])
    w = df.groupby([city_col, "is_weekend"], observed=True)[value].mean().unstack("is_weekend")
    w = w.rename(columns={False: "weekday_mean", True: "weekend_mean"}).dropna()
    w["difference"] = w["weekday_mean"] - w["weekend_mean"]
    return w.reset_index()


def hour_profile(hourly: pd.DataFrame, value: str = "pm25", by: str | None = None) -> pd.DataFrame:
    """Diurnal profile. Raises if data are not genuinely hourly."""
    if temporal_resolution(hourly) != "hourly":
        raise ValueError("Hour-of-day profiles require genuinely hourly data")
    require_columns(hourly, [value, "hour"] + ([by] if by else []))
    keys = ([by] if by else []) + ["hour"]
    return hourly.groupby(keys, observed=True)[value].agg(
        mean="mean", median="median", p25=lambda s: s.quantile(0.25), p75=lambda s: s.quantile(0.75),
        n="count").reset_index()
