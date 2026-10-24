"""One-time acquisition of daily ERA5 weather from the Open-Meteo archive API.

Weather is fetched for (a) the WEATHER_CITY_TOP_N most populous World Bank cities
and (b) the World Bank city nearest to each Kaggle/HF city (within OVERLAP_MAX_KM),
over the full World Bank date range. Raw JSON responses are stored unchanged in
data/raw/openmeteo_weather/ with a manifest. The dashboard never calls the API.

Already-downloaded cities are skipped, so the script can be re-run safely.

Usage:
    python scripts/fetch_openmeteo_weather.py
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.utils.config import LOCAL_TZ, OVERLAP_MAX_KM, WEATHER_CITY_TOP_N  # noqa: E402
from src.utils.paths import HF_CSV_NAME, HF_RAW_DIR, RAW_DIR, WB_PAK_SUBSET  # noqa: E402

OUT_DIR = RAW_DIR / "openmeteo_weather"
API = "https://archive-api.open-meteo.com/v1/archive"
DAILY_VARS = [
    "temperature_2m_mean", "temperature_2m_max", "temperature_2m_min",
    "relative_humidity_2m_mean", "dew_point_2m_mean",
    "wind_speed_10m_mean", "wind_speed_10m_max", "wind_direction_10m_dominant",
    "precipitation_sum", "surface_pressure_mean",
]


def haversine_km(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 6371.0 * 2 * np.arcsin(np.sqrt(a))


def select_cities() -> tuple[pd.DataFrame, str, str]:
    wb = pd.read_parquet(WB_PAK_SUBSET)
    cities = wb.drop_duplicates("geonameid")[["geonameid", "city", "latitude", "longitude", "population"]]
    chosen = cities.nlargest(WEATHER_CITY_TOP_N, "population").assign(reason="top_population")

    hf = pd.read_csv(HF_RAW_DIR / HF_CSV_NAME, usecols=["city", "latitude", "longitude"]).drop_duplicates("city")
    extra = []
    for _, r in hf.iterrows():
        d = haversine_km(r.latitude, r.longitude, cities.latitude.values, cities.longitude.values)
        i = int(np.argmin(d))
        if d[i] <= OVERLAP_MAX_KM:
            extra.append(cities.iloc[[i]].assign(reason=f"nearest_to_hf:{r.city}"))
    if extra:
        chosen = pd.concat([chosen, *extra]).drop_duplicates("geonameid", keep="first")
    return chosen.reset_index(drop=True), str(wb["date"].min()), str(wb["date"].max())


def fetch_city(row, start: str, end: str, session: requests.Session) -> dict:
    params = {
        "latitude": row.latitude, "longitude": row.longitude,
        "start_date": start, "end_date": end,
        "daily": ",".join(DAILY_VARS), "models": "era5", "timezone": LOCAL_TZ,
    }
    for attempt in range(6):
        resp = session.get(API, params=params, timeout=120)
        if resp.status_code == 429 or resp.status_code >= 500:
            wait = 30 * (attempt + 1)
            print(f"  HTTP {resp.status_code}; retrying in {wait}s")
            time.sleep(wait)
            continue
        resp.raise_for_status()
        payload = resp.json()
        if payload.get("error"):
            raise RuntimeError(payload.get("reason"))
        return payload
    raise RuntimeError(f"Failed to fetch {row.city} after retries")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    chosen, start, end = select_cities()
    manifest_path = OUT_DIR / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {"cities": {}}
    session = requests.Session()
    for row in chosen.itertuples():
        out = OUT_DIR / f"era5_daily_{row.geonameid}.json"
        if out.exists():
            print(f"skip {row.city} (already downloaded)")
            continue
        print(f"fetch {row.city} ({row.reason})")
        payload = fetch_city(row, start, end, session)
        out.write_text(json.dumps(payload))
        manifest["cities"][str(row.geonameid)] = {
            "city": row.city, "reason": row.reason,
            "requested_lat": row.latitude, "requested_lon": row.longitude,
            "grid_lat": payload["latitude"], "grid_lon": payload["longitude"],
            "start_date": start, "end_date": end, "file": out.name,
            "retrieved_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        manifest.update({"api": API, "model": "era5", "timezone": LOCAL_TZ, "daily_variables": DAILY_VARS,
                         "license": "CC BY 4.0 (Open-Meteo)"})
        manifest_path.write_text(json.dumps(manifest, indent=2))
        time.sleep(12)  # stay well inside the free-tier per-minute weighting
    print(f"done: {len(manifest['cities'])} cities in {OUT_DIR}")


if __name__ == "__main__":
    main()
