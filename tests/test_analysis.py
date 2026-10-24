"""Descriptive statistics, correlations, trends, statistical tests and data-quality diagnostics."""

import numpy as np
import pandas as pd
import pytest
from scipy import stats

from src.analysis import correlations, data_quality, descriptive, seasonality, sensitivity, statistical_tests, trends
from tests.conftest import make_daily


# --- descriptive ---------------------------------------------------------------
def test_summary_stats_known_values():
    df = pd.DataFrame({"pm25": [1.0, 2.0, 3.0, 4.0, np.nan], "g": list("aabbb")})
    s = descriptive.summary_stats(df).iloc[0]
    assert s["n"] == 4 and s["missing_pct"] == pytest.approx(20)
    assert s["mean"] == pytest.approx(2.5) and s["median"] == pytest.approx(2.5)
    assert s["std"] == pytest.approx(np.std([1, 2, 3, 4], ddof=1))
    assert s["min"] == 1 and s["max"] == 4
    by = descriptive.summary_stats(df, by="g").set_index("g")
    assert by.loc["a", "mean"] == pytest.approx(1.5) and by.loc["b", "n"] == 2


def test_city_summary_ranks_and_exceedance(daily):
    s = descriptive.city_summary(daily)
    assert s["rank_by_median"].tolist() == sorted(s["rank_by_median"])
    assert s.iloc[0]["median"] == s["median"].max()
    assert ((s["pct_days_above_threshold"] >= 0) & (s["pct_days_above_threshold"] <= 100)).all()


def test_comparable_period_ranking_applies_coverage(daily):
    d = daily[~((daily["city_id"] == "syn:5") & (daily["date"] > "2019-03-01"))]
    r = descriptive.comparable_period_ranking(d, "2019-01-01", "2019-12-31", min_coverage=0.8)
    assert "syn:5" not in set(r["city_id"]) and len(r) == 5


def test_real_only_excludes_synthetic(daily):
    real = daily.assign(value_type="modelled").head(10)
    mixed = pd.concat([daily, real])
    out = descriptive.real_only(mixed)
    assert set(out["value_type"]) == {"modelled"} and len(out) == 10


def test_empty_inputs():
    empty = pd.DataFrame(columns=["pm25", "date", "city_id"])
    assert descriptive.dataset_overview(empty)["rows"] == 0
    with pytest.raises(KeyError):
        descriptive.dataset_overview(pd.DataFrame({"x": [1]}))


# --- correlations --------------------------------------------------------------
def test_correlation_matches_scipy_and_reports_n():
    rng = np.random.default_rng(0)
    x = rng.normal(size=300)
    y = 0.6 * x + rng.normal(size=300)
    r = correlations.correlation(x, y, "pearson")
    assert r["r"] == pytest.approx(stats.pearsonr(x, y).statistic)
    assert r["n"] == 300 and r["ci_low"] < r["r"] < r["ci_high"]
    s = correlations.correlation(x, y, "spearman")
    assert s["r"] == pytest.approx(stats.spearmanr(x, y).statistic)


def test_effective_n_shrinks_for_autocorrelated_series():
    rng = np.random.default_rng(1)
    n = 2000
    x, y = np.zeros(n), np.zeros(n)
    for t in range(1, n):
        x[t] = 0.9 * x[t - 1] + rng.normal()
        y[t] = 0.9 * y[t - 1] + rng.normal()
    r = correlations.correlation(x, y)
    assert r["n_eff"] < 0.3 * n
    assert r["p_value_adjusted_n"] >= r["p_value"]


def test_correlation_insufficient_data():
    r = correlations.correlation([1, 2], [3, 4])
    assert np.isnan(r["r"]) and "note" in r
    with pytest.raises(ValueError):
        correlations.correlation([1, 2, 3], [1, 2, 3], "kendall")


def test_lagged_correlation_recovers_known_lag():
    rng = np.random.default_rng(2)
    dates = pd.date_range("2020-01-01", periods=600)
    x = rng.normal(size=600)
    frames = []
    for c in range(3):
        y = np.r_[np.zeros(2), x[:-2]] + 0.1 * rng.normal(size=600)  # y(t) = x(t-2)
        frames.append(pd.DataFrame({"city_id": f"c{c}", "date": dates, "w": x, "pm25": y}))
    lags = correlations.lagged_correlation(pd.concat(frames), "w", lags=range(-3, 4))
    assert lags.loc[lags["median_r"].idxmax(), "lag"] == 2


def test_anomaly_correlation_removes_shared_seasonality():
    d = make_daily(n_cities=3, seasonal_amp=0.8)
    rng = np.random.default_rng(3)
    d["temperature"] = -10 * np.cos(2 * np.pi * (d["date"].dt.dayofyear - 15) / 365.25) + rng.normal(0, 1, len(d))
    raw = correlations.pooled_city_correlation(d, "temperature", deseasonalize=False)
    anom = correlations.pooled_city_correlation(d, "temperature", deseasonalize=True)
    assert raw["median_r"] < -0.5 and abs(anom["median_r"]) < abs(raw["median_r"])


def test_correlation_matrix_shapes(daily):
    d = daily.assign(t=daily["pm25"] * 2)
    corr, n = correlations.correlation_matrix(d, ["pm25", "t"])
    assert corr.shape == (2, 2) and corr.loc["pm25", "t"] == pytest.approx(1.0) and n.loc["pm25", "t"] == len(d)
    with pytest.raises(KeyError):
        correlations.correlation_matrix(d, ["pm25"])


# --- trends --------------------------------------------------------------------
def test_linear_trend_recovers_slope():
    periods = pd.date_range("2015-01-01", periods=120, freq="MS")
    y = 2.0 * (periods - periods[0]).days / 365.25 + np.random.default_rng(4).normal(0, 0.5, 120)
    r = trends.linear_trend(pd.Series(periods), y)
    assert r["slope_per_year"] == pytest.approx(2.0, abs=0.1) and r["ci_low"] < 2 < r["ci_high"]
    assert r["theil_sen_slope"] == pytest.approx(2.0, abs=0.15)


def test_linear_trend_too_short():
    r = trends.linear_trend(pd.Series(pd.date_range("2020-01-01", periods=10, freq="MS")), np.arange(10.0))
    assert np.isnan(r["slope_per_year"]) and "note" in r


def test_city_trends_fdr_and_direction():
    d = make_daily(n_cities=4, trend_per_year=-8.0, start="2018-01-01", end="2023-12-31")
    t = trends.city_trends(d)
    assert len(t) == 4 and (t["direction"] == "decreasing").all()
    assert (t["q_value"] >= t["p_value"] - 1e-12).all()


def test_complete_years_and_yoy(daily):
    assert trends.complete_years(daily) == [2019, 2020, 2021, 2022]
    y = trends.year_over_year(daily)
    assert y.groupby("city_id")["pct_change"].apply(lambda s: s.isna().sum()).eq(1).all()


def test_rolling_mean_respects_calendar_gaps():
    dates = pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-10"])
    df = pd.DataFrame({"city_id": "a", "date": dates, "pm25": [1.0, 3.0, 100.0]})
    r = trends.rolling_mean(df, window=3, min_frac=0.6).set_index("date")["pm25_rolling"]
    assert r.loc["2024-01-01"] == pytest.approx(2.0) and np.isnan(r.loc["2024-01-05"])


# --- seasonality ---------------------------------------------------------------
def test_month_matrix_and_resolution(daily):
    m = seasonality.month_city_matrix(daily)
    assert list(m.columns)[0] == "Jan" and m.shape == (6, 12)
    assert m.loc["City 0", "Jan"] > m.loc["City 0", "Jul"]
    assert seasonality.temporal_resolution(daily, "date") == "daily"
    with pytest.raises(ValueError):
        seasonality.hour_profile(daily.assign(hour=0, timestamp=daily["date"]))


# --- statistical tests ---------------------------------------------------------
REQUIRED_FIELDS = {"question", "null_hypothesis", "n", "statistic", "p_value", "effect_size", "assumptions",
                   "interpretation", "unit_of_analysis"}


def test_friedman_detects_seasonality_and_reports_everything():
    d = make_daily(n_cities=12, seasonal_amp=0.6)
    r = statistical_tests.seasonal_friedman(d)
    assert REQUIRED_FIELDS <= set(r.to_dict())
    assert r.p_value < 0.001 and r.effect_size > 0.5 and r.n == 12
    assert "p_holm" in r.details.columns


def test_friedman_single_season_is_not_justified():
    d = make_daily(n_cities=8)
    r = statistical_tests.seasonal_friedman(d[d["season"] == "Winter"])
    assert not r.justified and np.isnan(r.p_value)


def test_kruskal_and_anova_gate():
    rng = np.random.default_rng(5)
    city = pd.DataFrame({"province": np.repeat(["A", "B", "C"], 15),
                         "pm25": np.r_[rng.lognormal(3, 1, 15), rng.lognormal(3.5, 1, 15), rng.lognormal(4, 1, 15)]})
    k = statistical_tests.group_kruskal(city, "pm25")
    assert k.justified and 0 <= k.p_value <= 1 and np.isfinite(k.effect_size)
    a = statistical_tests.group_anova_if_justified(city.assign(pm25=np.exp(city["pm25"] / 10) ** 8), "pm25")
    assert "shapiro_p_by_group" in a.assumption_checks
    if not a.justified:
        assert "not reported" in a.interpretation


def test_kruskal_excludes_small_groups():
    city = pd.DataFrame({"province": ["A"] * 5 + ["B"] * 5 + ["C"] * 2, "pm25": range(12)})
    k = statistical_tests.group_kruskal(city, "pm25", min_group=3)
    assert k.assumption_checks["groups_excluded_small_n"] == ["C"] and k.n == 10


def test_weekday_weekend_null_effect_small(daily):
    r = statistical_tests.weekday_weekend_test(daily)
    assert r.n == 6 and abs(r.effect_size) <= 1


def test_period_change_detects_decline():
    d = make_daily(n_cities=10, trend_per_year=-10.0, start="2018-01-01", end="2023-12-31")
    a = trends.annual_series(d)
    r = statistical_tests.period_change_test(a, 2018, 2023)
    assert r.effect_size < 0 and r.assumption_checks["n_cities_decreased"] == 10


def test_effect_label():
    assert statistical_tests.effect_label(0.05, "r") == "negligible"
    assert statistical_tests.effect_label(-0.6, "r") == "large"


# --- data quality --------------------------------------------------------------
def test_find_gaps_and_month_end_pattern():
    dates = pd.date_range("2024-01-01", "2024-04-30")
    kept = dates[~dates.is_month_end]
    gaps = data_quality.find_gaps(pd.Series(kept))
    assert len(gaps) == 3  # Jan 31, Feb 29, Mar 31 (Apr 30 is the end of the data)
    pat = data_quality.missing_dates_pattern(gaps)
    assert pat["all_month_end"] and pat["n_missing"] == 3
    assert data_quality.find_gaps(pd.Series(dates)).empty


def test_completeness_by_city():
    df = pd.DataFrame({"city_id": ["a"] * 5 + ["b"] * 10, "pm25": 1.0,
                       "date": list(pd.date_range("2024-01-01", periods=5)) + list(pd.date_range("2024-01-01", periods=10))})
    c = data_quality.completeness_by_city(df).set_index("city_id")
    assert c.loc["a", "completeness_pct"] == 50 and c.loc["b", "completeness_pct"] == 100


def test_duplicate_summary():
    df = pd.DataFrame({"k": [1, 1, 2], "v": [1, 1, 3]})
    s = data_quality.duplicate_summary(df, ["k"])
    assert s["duplicate_key_rows"] == 1 and s["exact_duplicate_rows"] == 1


def test_artifact_diagnostics_detect_fixed_level_and_step():
    d = make_daily(n_cities=3, start="2018-01-01", end="2023-12-31", seasonal_amp=0.3)
    rng = np.random.default_rng(6)
    # Realistic inter-annual variability (real annual means differ by several percent year to year)
    year_factor = dict(zip(range(2018, 2024), [1.0, 0.9, 1.08, 0.95, 1.12, 0.97]))
    d["pm25"] = d["pm25"] * d["year"].map(year_factor)
    # City 1: scale each year's values to an identical annual mean (fixed annual anchor)
    m1 = d["city_id"] == "syn:1"
    yearly = d[m1].groupby("year")["pm25"].transform("mean")
    d.loc[m1, "pm25"] = d.loc[m1, "pm25"] / yearly * 80.0
    # City 2: abrupt halving in Jan 2021
    m2 = (d["city_id"] == "syn:2") & (d["date"] >= "2021-01-01")
    d.loc[m2, "pm25"] = d.loc[m2, "pm25"] * 0.4 + rng.normal(0, 0.5, m2.sum())
    f = data_quality.model_artifact_flags(d).set_index("city_id")
    assert f.loc["syn:1", "fixed_annual_run"] >= 3 and f.loc["syn:1", "artifact_flag"]
    assert f.loc["syn:2", "artifact_flag"] and f.loc["syn:2", "break_date"] == pd.Timestamp("2021-01-01")
    assert not f.loc["syn:0", "artifact_flag"]


def test_diurnal_alignment_offset():
    hours = np.tile(np.arange(24), 5)
    h = pd.DataFrame({"hour": hours, "ozone": np.cos(2 * np.pi * (hours - 9) / 24),
                      "temperature": np.cos(2 * np.pi * (hours - 15) / 24)})
    a = data_quality.diurnal_peak_alignment(h)
    assert a["pollutant_peak_hour"] == 9 and a["weather_peak_hour"] == 15 and a["offset_hours"] == 6


def test_identical_series_detection():
    t = pd.date_range("2024-01-01", periods=48, freq="h")
    df = pd.concat([pd.DataFrame({"city": c, "timestamp": t, "pm25": v})
                    for c, v in (("A", np.arange(48.0)), ("B", np.arange(48.0)), ("C", np.arange(48.0) + 1))])
    s = data_quality.identical_series(df, "pm25", "timestamp")
    assert s[["city_a", "city_b"]].values.tolist() == [["A", "B"]]


def test_sensitivity_scenarios(daily):
    m = sensitivity.scenario_metrics(daily, top_n=3)
    base = m.iloc[0]
    assert base["rank_spearman_vs_baseline"] == pytest.approx(1.0) and base["rows_removed_pct"] == 0
    assert len(m) >= 5
