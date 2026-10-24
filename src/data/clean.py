"""Source-specific cleaning with an explicit exclusion/transformation log.

Each ``clean_*`` function takes a raw frame, returns an analysis-ready frame and
appends every exclusion or transformation to an :class:`ExclusionLog`.
Sources are cleaned separately and are never merged row-wise.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from src.data import validate
from src.utils.config import ADM1_ANCHOR_CITIES, ADM1_LABELS, PLAUSIBLE_RANGES

# ---------------------------------------------------------------------------
# Exclusion log
# ---------------------------------------------------------------------------


@dataclass
class ExclusionLog:
    entries: list[dict] = field(default_factory=list)

    def add(self, source_id: str, step: str, rule: str, n_rows: int, action: str,
            column: str = "", example: str = "") -> None:
        self.entries.append({"source_id": source_id, "step": step, "rule": rule, "column": column,
                             "n_rows": int(n_rows), "action": action, "example": example[:200]})

    def to_frame(self) -> pd.DataFrame:
        cols = ["source_id", "step", "rule", "column", "n_rows", "action", "example"]
        return pd.DataFrame(self.entries, columns=cols)


# ---------------------------------------------------------------------------
# Name normalisation
# ---------------------------------------------------------------------------
COLUMN_SYNONYMS = {
    "pm2_5": "pm25", "pm2.5": "pm25", "pm_2_5": "pm25", "pm25_ugm3": "pm25",
    "pm_10": "pm10",
    "temp": "temperature", "temperature_2m": "temperature", "temperature_2m_mean": "temperature",
    "temperature_2m_max": "temperature_max", "temperature_2m_min": "temperature_min",
    "relative_humidity": "humidity", "relative_humidity_2m": "humidity", "relative_humidity_2m_mean": "humidity",
    "dew_point_2m_mean": "dew_point",
    "wind_speed_10m": "wind_speed", "wind_speed_10m_mean": "wind_speed", "wind_speed_10m_max": "wind_speed_max",
    "wind_direction_10m_dominant": "wind_direction",
    "precipitation_sum": "precipitation", "surface_pressure_mean": "pressure", "surface_pressure": "pressure",
    "lat": "latitude", "lon": "longitude", "lng": "longitude",
}

CITY_ALIASES = {
    "isb": "Islamabad", "islamabad capital territory": "Islamabad",
    "lhr": "Lahore", "khi": "Karachi", "pindi": "Rawalpindi",
    "d.i. khan": "Dera Ismail Khan", "di khan": "Dera Ismail Khan",
    "lyallpur": "Faisalabad", "ryk": "Rahim Yar Khan",
}


def normalize_column_name(name: str) -> str:
    s = unicodedata.normalize("NFKC", str(name)).strip().lower()
    s = s.replace("µ", "u").replace("³", "3")
    if s in COLUMN_SYNONYMS:
        return COLUMN_SYNONYMS[s]
    s = re.sub(r"[^0-9a-z.]+", "_", s).strip("_")
    return COLUMN_SYNONYMS.get(s, s.replace(".", "_"))


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    new = [normalize_column_name(c) for c in df.columns]
    dupes = {c for c in new if new.count(c) > 1}
    if dupes:
        raise ValueError(f"Column normalisation produced duplicate names: {sorted(dupes)}")
    return df.set_axis(new, axis=1)


def normalize_city_name(name) -> str | float:
    """Canonical display name: NFKC, trimmed, single-spaced, title-cased, alias-resolved."""
    if name is None or (isinstance(name, float) and np.isnan(name)):
        return np.nan
    s = unicodedata.normalize("NFKC", str(name))
    s = re.sub(r"\s+", " ", s).strip()
    if not s:
        return np.nan
    alias = CITY_ALIASES.get(s.lower())
    if alias:
        return alias
    # Title-case word by word; in mixed-case names short all-caps tokens (e.g. "DI Khan") are kept,
    # but a fully upper-case name ("RAHIM YAR KHAN") is title-cased throughout.
    keep_acronyms = not s.isupper()
    return " ".join(w if (keep_acronyms and w.isupper() and len(w) <= 3) else w[:1].upper() + w[1:].lower()
                    for w in s.split(" "))


def city_key(name) -> str | float:
    """Matching key: lowercase ASCII letters/digits only ("Arif Wala" == "Arifwala")."""
    n = normalize_city_name(name)
    if not isinstance(n, str):
        return np.nan
    ascii_ = unicodedata.normalize("NFKD", n).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", ascii_.lower())


# ---------------------------------------------------------------------------
# Date parsing
# ---------------------------------------------------------------------------


def parse_datetime(series: pd.Series, source_tz: str | None = None, target_tz: str | None = None,
                   normalize: bool = False) -> pd.Series:
    """Parse to naive datetimes; unparseable values become NaT.

    * tz-aware input is converted to ``target_tz`` (if given) and made naive.
    * naive input is localised to ``source_tz`` then converted, if both are given.
    """
    parsed = pd.to_datetime(series, errors="coerce", utc=False, format="mixed")
    if isinstance(parsed.dtype, pd.DatetimeTZDtype):
        if target_tz:
            parsed = parsed.dt.tz_convert(target_tz)
        parsed = parsed.dt.tz_localize(None)
    elif source_tz and target_tz and source_tz != target_tz:
        parsed = parsed.dt.tz_localize(source_tz).dt.tz_convert(target_tz).dt.tz_localize(None)
    if normalize:
        parsed = parsed.dt.normalize()
    return parsed


# ---------------------------------------------------------------------------
# Shared steps
# ---------------------------------------------------------------------------


def _drop_rows(df: pd.DataFrame, mask: pd.Series, log: ExclusionLog, source_id: str, step: str,
               rule: str, column: str = "", key_cols: list[str] | None = None) -> pd.DataFrame:
    n = int(mask.sum())
    if n:
        ex = ""
        if key_cols:
            ex = "; ".join(df.loc[mask, key_cols].head(3).astype(str).agg("|".join, axis=1))
        log.add(source_id, step, rule, n, "row excluded", column, ex)
    return df.loc[~mask].copy()


def _null_invalid_values(df: pd.DataFrame, columns: list[str], log: ExclusionLog, source_id: str) -> pd.DataFrame:
    """For multi-variable tables, invalid cells are set to NaN (row kept for other variables)."""
    for c in columns:
        if c not in df.columns:
            continue
        nn = validate.non_numeric_mask(df[c])
        df[c] = pd.to_numeric(df[c], errors="coerce").astype("float64")
        if nn.any():
            log.add(source_id, "type_validation", "non-numeric value", int(nn.sum()), "value set to NaN", c)
        oor = validate.out_of_range_mask(df, c)
        if oor.any():
            lo, hi = PLAUSIBLE_RANGES[c]
            log.add(source_id, "range_validation", f"outside plausible range [{lo}, {hi}]", int(oor.sum()),
                    "value set to NaN", c, ", ".join(map(str, df.loc[oor, c].head(5).tolist())))
            df.loc[oor, c] = np.nan
    return df


def _dedupe(df: pd.DataFrame, keys: list[str], value_cols: list[str], log: ExclusionLog,
            source_id: str) -> pd.DataFrame:
    """Drop exact duplicates (keep one); drop *all* copies of conflicting duplicates."""
    exact = df.duplicated(keys + value_cols, keep="first")
    df = _drop_rows(df, exact, log, source_id, "deduplication", "exact duplicate of key + values",
                    key_cols=keys)
    conflict = validate.conflicting_duplicates(df, keys, value_cols)
    df = _drop_rows(df, conflict, log, source_id, "deduplication",
                    "conflicting duplicate key (values differ) - all copies excluded", key_cols=keys)
    return df


# ---------------------------------------------------------------------------
# World Bank PM2.5 (daily, modelled)
# ---------------------------------------------------------------------------
WB_REQUIRED = ["geonameid", "city", "adm1cd_c", "latitude", "longitude", "population", "date", "pm25"]


def disambiguate_labels(cities: pd.DataFrame) -> pd.Series:
    """Unique display labels: 'City', or 'City (Province)', or 'City (lat°N, lon°E)'."""
    label = cities["city"].copy()
    dup = label.duplicated(keep=False)
    label[dup] = cities.loc[dup, "city"] + " (" + cities.loc[dup, "province"].astype(str) + ")"
    dup2 = label.duplicated(keep=False)
    label[dup2] = (cities.loc[dup2, "city"] + " (" + cities.loc[dup2, "latitude"].round(2).astype(str) + "°N, "
                   + cities.loc[dup2, "longitude"].round(2).astype(str) + "°E)")
    return label


def verify_adm1_anchors(cities: pd.DataFrame) -> dict[str, bool]:
    """True per ADM1 code when its anchor capital is found inside that code in the data."""
    out = {}
    for code, anchor in ADM1_ANCHOR_CITIES.items():
        sub = cities[cities["adm1_code"] == code]
        out[code] = bool((sub["city"] == anchor).any())
    return out


def name_ambiguity_flags(cities: pd.DataFrame) -> pd.Series:
    """True when another place with a different geonameid shares the same city_key."""
    keys = cities["city"].map(city_key)
    return keys.map(keys.value_counts()) > 1


def clean_wb(raw: pd.DataFrame, log: ExclusionLog) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (daily long table, city dimension table)."""
    src = "wb_pm25"
    df = normalize_columns(raw.copy())
    validate.require_columns(df, WB_REQUIRED)
    n0 = len(df)
    if "adm0_wb_a3" in df.columns:
        df = _drop_rows(df, df["adm0_wb_a3"] != "PAK", log, src, "scope", "country is not Pakistan (PAK)")

    df["date"] = parse_datetime(df["date"], normalize=True)
    df = _drop_rows(df, df["date"].isna(), log, src, "date_parsing", "unparseable date", "date")

    nn = validate.non_numeric_mask(df["pm25"])
    df["pm25"] = pd.to_numeric(df["pm25"], errors="coerce")
    df = _drop_rows(df, nn, log, src, "type_validation", "non-numeric PM2.5", "pm25")
    df = _drop_rows(df, df["pm25"].isna(), log, src, "missing_values", "missing PM2.5", "pm25")
    df = _drop_rows(df, validate.out_of_range_mask(df, "pm25"), log, src, "range_validation",
                    f"PM2.5 outside plausible range {PLAUSIBLE_RANGES['pm25']}", "pm25",
                    key_cols=["city", "date"])
    df = _dedupe(df, ["geonameid", "date"], ["pm25"], log, src)

    df["geonameid"] = df["geonameid"].astype("int64")
    df["city"] = df["city"].map(normalize_city_name)
    df["adm1_code"] = df["adm1cd_c"].astype(str)
    df["province"] = df["adm1_code"].map(ADM1_LABELS).fillna("Unknown (" + df["adm1_code"] + ")")
    df["city_id"] = "wb:" + df["geonameid"].astype(str)

    cities = (df.groupby("geonameid", as_index=False)
                .agg(city=("city", "first"), adm1_code=("adm1_code", "first"), province=("province", "first"),
                     latitude=("latitude", "first"), longitude=("longitude", "first"),
                     population=("population", "first"), n_days=("date", "nunique"),
                     first_date=("date", "min"), last_date=("date", "max")))
    cities["city_id"] = "wb:" + cities["geonameid"].astype(str)
    cities["population"] = pd.to_numeric(cities["population"], errors="coerce").fillna(-1).astype("int64")
    cities["city_label"] = disambiguate_labels(cities)
    cities["name_ambiguous"] = name_ambiguity_flags(cities)
    lat_ok = cities["latitude"].between(*PLAUSIBLE_RANGES["latitude"])
    lon_ok = cities["longitude"].between(*PLAUSIBLE_RANGES["longitude"])
    cities["coords_in_bbox"] = lat_ok & lon_ok
    if (~cities["coords_in_bbox"]).any():
        log.add(src, "geo_validation", "coordinates outside Pakistan bounding box",
                int((~cities["coords_in_bbox"]).sum()), "flagged (kept)")
    n_amb = int(cities["name_ambiguous"].sum())
    if n_amb:
        ex = ", ".join(cities.loc[cities["name_ambiguous"], "city_label"].head(6))
        log.add(src, "identity_check", "place name shared/near-identical across different GeoNames IDs",
                n_amb, "flagged (kept); labels disambiguated", "city", ex)

    df = df.merge(cities[["geonameid", "city_label"]], on="geonameid", how="left")
    df["source_id"] = src
    df["value_type"] = "modelled"
    keep = ["city_id", "geonameid", "city", "city_label", "province", "adm1_code", "latitude", "longitude",
            "population", "date", "pm25", "source_id", "value_type"]
    df = df[keep].sort_values(["city_id", "date"]).reset_index(drop=True)
    log.add(src, "summary", "rows retained after cleaning", len(df), f"retained {len(df):,} of {n0:,}")
    return df, cities


# ---------------------------------------------------------------------------
# Kaggle / Hugging Face hourly air quality + weather
# ---------------------------------------------------------------------------
HF_VALUE_COLS = ["pm10", "pm25", "carbon_monoxide", "nitrogen_dioxide", "sulphur_dioxide", "ozone", "dust",
                 "temperature", "humidity", "precipitation", "wind_speed", "wind_direction", "pressure"]
HF_DERIVED_COLS = ["date", "hour", "day_of_week", "month", "month_name", "year", "is_weekend", "season",
                   "aqi_category"]


def clean_hf(raw: pd.DataFrame, log: ExclusionLog) -> pd.DataFrame:
    src = "hf_aq"
    df = normalize_columns(raw.copy())
    validate.require_columns(df, ["timestamp", "city", "pm25"])
    n0 = len(df)

    dropped = [c for c in HF_DERIVED_COLS if c in df.columns]
    if dropped:
        df = df.drop(columns=dropped)
        log.add(src, "transformation", "source-derived calendar/AQI columns dropped; calendar fields are "
                "recomputed from timestamp and AQI categories are not used", n0, "columns removed",
                ",".join(dropped))

    df["timestamp"] = parse_datetime(df["timestamp"])
    df = _drop_rows(df, df["timestamp"].isna(), log, src, "date_parsing", "unparseable timestamp", "timestamp")
    df["city"] = df["city"].map(normalize_city_name)
    df = _drop_rows(df, df["city"].isna(), log, src, "missing_values", "missing city", "city")

    df = _null_invalid_values(df, [c for c in HF_VALUE_COLS if c in df.columns], log, src)
    present = [c for c in HF_VALUE_COLS if c in df.columns]
    df = _dedupe(df, ["city", "timestamp"], present, log, src)

    if {"pm25", "pm10"} <= set(df.columns):
        bad = df["pm25"] > df["pm10"]
        if bad.any():
            log.add(src, "consistency_check", "PM2.5 greater than PM10", int(bad.sum()), "flagged (kept)")

    df["city_id"] = "hf:" + df["city"].map(city_key)
    df["date"] = df["timestamp"].dt.normalize()
    df["hour"] = df["timestamp"].dt.hour.astype("int64")
    df["source_id"] = src
    df["value_type"] = "modelled"
    front = ["city_id", "city", "latitude", "longitude", "timestamp", "date", "hour"]
    df = df[front + present + ["source_id", "value_type"]].sort_values(["city_id", "timestamp"])
    log.add(src, "summary", "rows retained after cleaning", len(df), f"retained {len(df):,} of {n0:,}")
    return df.reset_index(drop=True)


# ---------------------------------------------------------------------------
# Open-Meteo ERA5 daily weather
# ---------------------------------------------------------------------------
WEATHER_COLS = ["temperature", "temperature_max", "temperature_min", "humidity", "dew_point", "wind_speed",
                "wind_speed_max", "wind_direction", "precipitation", "pressure"]


def clean_weather(payloads: list[dict], log: ExclusionLog) -> pd.DataFrame:
    src = "openmeteo_era5"
    frames = []
    for item in payloads:
        p = item["payload"]
        daily = pd.DataFrame(p["daily"])
        daily = normalize_columns(daily)
        daily["geonameid"] = int(item["geonameid"])
        daily["grid_latitude"] = p.get("latitude")
        daily["grid_longitude"] = p.get("longitude")
        daily["grid_elevation_m"] = p.get("elevation")
        frames.append(daily)
    if not frames:
        return pd.DataFrame(columns=["city_id", "geonameid", "date", *WEATHER_COLS, "source_id", "value_type"])
    df = pd.concat(frames, ignore_index=True).rename(columns={"time": "date"})
    df["date"] = parse_datetime(df["date"], normalize=True)
    df = _drop_rows(df, df["date"].isna(), log, src, "date_parsing", "unparseable date", "date")
    df = _null_invalid_values(df, [c for c in WEATHER_COLS if c in df.columns], log, src)
    present = [c for c in WEATHER_COLS if c in df.columns]
    df = _dedupe(df, ["geonameid", "date"], present, log, src)
    df["city_id"] = "wb:" + df["geonameid"].astype(str)
    df["source_id"] = src
    df["value_type"] = "modelled"
    cols = ["city_id", "geonameid", "date", *present, "grid_latitude", "grid_longitude", "grid_elevation_m",
            "source_id", "value_type"]
    log.add(src, "summary", "rows retained after cleaning", len(df), f"{df['geonameid'].nunique()} cities")
    return df[cols].sort_values(["city_id", "date"]).reset_index(drop=True)
