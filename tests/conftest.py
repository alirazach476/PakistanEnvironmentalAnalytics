"""Synthetic fixtures for unit tests.

All rows generated here carry ``value_type == "synthetic"`` and live only in
memory; they are never written to data/ and never reach real-data results.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.data.transform import add_calendar  # noqa: E402


def make_wb_raw(n_cities: int = 4, start: str = "2019-01-01", end: str = "2021-12-31", seed: int = 0) -> pd.DataFrame:
    """Raw-format World Bank rows (schema of the real source) with a seasonal cycle."""
    rng = np.random.default_rng(seed)
    dates = pd.date_range(start, end, freq="D")
    rows = []
    for i in range(n_cities):
        base = 40 + 20 * i
        season = 1 + 0.5 * np.cos(2 * np.pi * (dates.dayofyear - 15) / 365.25)  # peak mid-January
        vals = base * season * rng.lognormal(0, 0.15, len(dates))
        rows.append(pd.DataFrame({
            "wb_region": "test", "nam_0": "Pakistan", "adm0_wb_a3": "PAK", "pm25_iso3": "PAK",
            "adm1cd_c": ["PAK006", "PAK007", "PAK005", "PAK002"][i % 4], "geonameid": 1000 + i,
            "city": f"Town {chr(65 + i)}", "latitude": 25.0 + i, "longitude": 67.0 + i,
            "population": 10_000 * (i + 1), "date": dates.strftime("%Y-%m-%d"), "pm25": vals}))
    return pd.concat(rows, ignore_index=True)


def make_daily(n_cities: int = 6, start: str = "2019-01-01", end: str = "2022-12-31", seed: int = 1,
               trend_per_year: float = 0.0, seasonal_amp: float = 0.5) -> pd.DataFrame:
    """Clean daily long table in the processed WB schema (value_type = synthetic)."""
    rng = np.random.default_rng(seed)
    dates = pd.date_range(start, end, freq="D")
    years = (dates - dates[0]).days / 365.25
    frames = []
    for i in range(n_cities):
        level = 50 + 10 * i
        season = 1 + seasonal_amp * np.cos(2 * np.pi * (dates.dayofyear - 15) / 365.25)
        noise = rng.normal(0, 3, len(dates))
        v = level * season + trend_per_year * years + noise
        frames.append(pd.DataFrame({
            "city_id": f"syn:{i}", "city_label": f"City {i}", "city": f"City {i}",
            "province": ["Punjab", "Sindh"][i % 2], "latitude": 25.0 + i, "longitude": 67.0 + i,
            "population": 1000 * (n_cities - i), "date": dates, "pm25": np.clip(v, 1, None),
            "source_id": "synthetic_test", "value_type": "synthetic"}))
    df = add_calendar(pd.concat(frames, ignore_index=True))
    df["is_outlier"] = False
    return df


@pytest.fixture
def wb_raw():
    return make_wb_raw()


@pytest.fixture
def daily():
    return make_daily()


@pytest.fixture
def hf_raw():
    ts = pd.date_range("2025-11-06", periods=72, freq="h")
    rows = []
    for c in ("Lahore", "  karachi "):
        rows.append(pd.DataFrame({
            "timestamp": ts.strftime("%Y-%m-%d %H:%M:%S"), "city": c, "latitude": 31.5, "longitude": 74.3,
            "pm10": 100.0, "pm2_5": 80.0, "ozone": 50.0, "temperature": 15.0, "humidity": 60.0,
            "precipitation": 0.5, "wind_speed": 5.0, "wind_direction": 350.0, "pressure": 1015.0,
            "date": ts.strftime("%Y-%m-%d"), "hour": ts.hour, "season": "Winter", "aqi_category": "Unhealthy"}))
    return pd.concat(rows, ignore_index=True)
