"""Aggregation rules, calendar features, outlier flags and source linkage."""

import numpy as np
import pandas as pd
import pytest

from src.data import transform
from tests.conftest import make_daily


def _hourly(hours=24, city="A", start="2024-01-01"):
    ts = pd.date_range(start, periods=hours, freq="h")
    return pd.DataFrame({"city_id": f"x:{city}", "city": city, "timestamp": ts,
                         "pm25": np.arange(hours, dtype=float), "precipitation": 1.0,
                         "wind_direction": np.where(np.arange(hours) % 2, 350.0, 10.0)})


def test_hourly_to_daily_mean_sum_and_circular():
    d = transform.hourly_to_daily(_hourly(24), ["pm25", "precipitation", "wind_direction"])
    r = d.iloc[0]
    assert r["n_hours"] == 24
    assert r["pm25"] == pytest.approx(11.5)
    assert r["precipitation"] == pytest.approx(24.0)          # summed, not averaged
    assert min(r["wind_direction"], 360 - r["wind_direction"]) < 1e-6  # circular mean of 350/10 = 0°


def test_hourly_to_daily_completeness_rule():
    d = transform.hourly_to_daily(_hourly(10), ["pm25"], min_hours=18)
    assert d["n_hours"].iloc[0] == 10 and np.isnan(d["pm25"].iloc[0])


def test_add_calendar_seasons_and_weekend():
    df = transform.add_calendar(pd.DataFrame({"date": pd.to_datetime(["2024-01-06", "2024-07-15", "2024-10-01"])}))
    assert df["season"].astype(str).tolist() == ["Winter", "Monsoon", "Post-monsoon"]
    assert df["is_weekend"].tolist() == [True, False, False]


def test_aggregate_period_monthly_completeness():
    dates = pd.date_range("2024-01-01", "2024-02-29")
    df = pd.DataFrame({"city_id": "c", "date": dates, "pm25": 10.0})
    df.loc[df["date"].dt.month == 2, "pm25"] = np.where(np.arange(29) < 10, 20.0, np.nan)  # 10 valid Feb days
    m = transform.aggregate_period(df, "pm25", "MS")
    assert m["complete"].tolist() == [True, False]
    assert m["n"].tolist() == [31, 10]


def test_aggregate_period_annual_uses_monthly_means():
    dates = pd.date_range("2023-01-01", "2023-12-31")
    df = pd.DataFrame({"city_id": "c", "date": dates, "pm25": np.where(dates.month == 1, 100.0, 10.0)})
    a = transform.aggregate_period(df, "pm25", "YS")
    assert a["mean"].iloc[0] == pytest.approx((100 + 11 * 10) / 12)
    assert bool(a["complete"].iloc[0])


def test_aggregate_period_rejects_bad_freq(daily):
    with pytest.raises(ValueError):
        transform.aggregate_period(daily, "pm25", "W")


def test_flag_outliers_finds_injected_spike(daily):
    d = daily.copy()
    idx = d.index[100]
    d.loc[idx, "pm25"] = d["pm25"].max() * 50
    flags = transform.flag_outliers(d)
    assert flags.loc[idx] and flags.mean() < 0.01


def test_identical_series_groups_and_independent_units(daily):
    twin = daily[daily["city_id"] == "syn:0"].assign(city_id="syn:twin", city_label="Twin", population=1)
    d = pd.concat([daily, twin], ignore_index=True)
    cities = d.groupby("city_id", as_index=False).agg(city_label=("city_label", "first"),
                                                      population=("population", "first"))
    g = transform.identical_series_groups(d, cities)
    grp = g.set_index("city_id")
    assert grp.loc["syn:0", "series_group"] == grp.loc["syn:twin", "series_group"]
    assert grp.loc["syn:0", "series_group_size"] == 2
    assert grp.loc["syn:0", "is_series_representative"] and not grp.loc["syn:twin", "is_series_representative"]
    assert transform.independent_units(d, g)["city_id"].nunique() == daily["city_id"].nunique()


def test_source_overlap_pairs_but_never_pools():
    wb = make_daily(n_cities=2, start="2025-11-01", end="2025-11-30")
    cities = wb.groupby("city_id", as_index=False).agg(city_label=("city_label", "first"),
                                                       latitude=("latitude", "first"), longitude=("longitude", "first"))
    hf = pd.DataFrame({"city_id": "hf:a", "city": "A", "latitude": 25.01, "longitude": 67.01,
                       "date": pd.date_range("2025-11-10", periods=5), "pm25": 1.0, "n_hours": 24})
    ov = transform.build_source_overlap(hf, wb, cities, max_km=25)
    assert len(ov) == 5 and set(ov["match_city_id"]) == {"syn:0"}
    assert {"pm25_hf", "pm25_wb"} <= set(ov.columns) and "pm25" not in ov.columns
    far = hf.assign(latitude=35.0, longitude=60.0)
    assert transform.build_source_overlap(far, wb, cities, max_km=25).empty


def test_join_weather_inner_on_city_and_date(daily):
    w = pd.DataFrame({"city_id": "syn:1", "geonameid": 1, "date": daily["date"].unique()[:10], "temperature": 20.0,
                      "grid_latitude": 1.0, "grid_longitude": 2.0, "source_id": "openmeteo_era5", "value_type": "modelled"})
    j = transform.join_weather(daily, w)
    assert len(j) == 10 and set(j["city_id"]) == {"syn:1"} and "weather_grid_lat" in j.columns
    assert transform.join_weather(daily, w.iloc[0:0]).empty
