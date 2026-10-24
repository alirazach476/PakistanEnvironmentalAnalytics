"""Calendar features, documented aggregation rules, outlier flags and source linkage.

Aggregation rules (also in docs/methodology.md):
* hourly -> daily: arithmetic mean for concentrations/temperature/humidity/wind speed/pressure,
  **sum** for precipitation, circular (vector) mean for wind direction. A day is kept only with
  at least ``MIN_HOURS_PER_DAY`` valid hours for that variable.
* daily -> monthly: mean of daily values with at least ``MIN_DAYS_PER_MONTH`` valid days.
* monthly -> annual: mean of monthly means with at least ``MIN_MONTHS_PER_YEAR`` valid months.
"""

from __future__ import annotations

import hashlib

import numpy as np
import pandas as pd

from src.data.validate import require_columns
from src.utils.config import (MIN_DAYS_PER_MONTH, MIN_HOURS_PER_DAY, MIN_MONTHS_PER_YEAR, MONTH_NAMES,
                              OUTLIER_ROBUST_Z, OVERLAP_MAX_KM, SEASON_BY_MONTH, SEASON_ORDER)

SUM_VARS = {"precipitation"}
CIRCULAR_VARS = {"wind_direction"}


def add_calendar(df: pd.DataFrame, date_col: str = "date") -> pd.DataFrame:
    require_columns(df, [date_col])
    out = df.copy()
    d = pd.to_datetime(out[date_col])
    out["year"] = d.dt.year.astype("int64")
    out["month"] = d.dt.month.astype("int64")
    out["month_name"] = pd.Categorical(d.dt.month.map(lambda m: MONTH_NAMES[m - 1]), categories=MONTH_NAMES,
                                       ordered=True)
    out["season"] = pd.Categorical(d.dt.month.map(SEASON_BY_MONTH), categories=SEASON_ORDER, ordered=True)
    out["day_of_week"] = d.dt.day_name()
    out["is_weekend"] = d.dt.dayofweek >= 5  # Saturday/Sunday (see methodology caveat)
    return out


def _circular_mean_deg(values: pd.Series) -> float:
    v = values.dropna().to_numpy()
    if v.size == 0:
        return np.nan
    rad = np.deg2rad(v)
    ang = np.rad2deg(np.arctan2(np.sin(rad).mean(), np.cos(rad).mean()))
    return float(ang % 360)


def hourly_to_daily(df: pd.DataFrame, value_cols: list[str], group_cols: tuple[str, ...] = ("city_id", "city"),
                    min_hours: int = MIN_HOURS_PER_DAY, time_col: str = "timestamp") -> pd.DataFrame:
    """Aggregate hourly rows to daily values per group, enforcing ``min_hours`` per variable."""
    require_columns(df, [time_col, *group_cols])
    work = df.copy()
    work["date"] = pd.to_datetime(work[time_col]).dt.normalize()
    keys = [*group_cols, "date"]
    g = work.groupby(keys, observed=True)
    out = g.size().rename("n_hours").reset_index()
    for c in value_cols:
        if c not in work.columns:
            continue
        cnt = g[c].count().rename(f"_{c}_n")
        if c in SUM_VARS:
            agg = g[c].sum(min_count=1)
        elif c in CIRCULAR_VARS:
            agg = g[c].apply(_circular_mean_deg)
        else:
            agg = g[c].mean()
        agg = agg.where(cnt >= min_hours)
        out = out.merge(agg.rename(c).reset_index(), on=keys, how="left")
    out["n_hours"] = out["n_hours"].astype("int64")
    for extra in ("latitude", "longitude", "source_id", "value_type"):
        if extra in work.columns:
            first = g[extra].first().reset_index()
            out = out.merge(first, on=keys, how="left")
    return out


def aggregate_period(df: pd.DataFrame, value: str, freq: str, group_cols: list[str] | tuple[str, ...] = ("city_id",),
                     min_count: int | None = None, date_col: str = "date") -> pd.DataFrame:
    """Daily -> monthly ('MS') or annual ('YS') means with an explicit completeness rule.

    Annual means are computed from *monthly* means (each requiring MIN_DAYS_PER_MONTH days) so
    that months with more observations do not dominate the annual figure.
    Returns columns: group_cols, period, mean, n (contributing units), complete (bool).
    """
    require_columns(df, [date_col, value, *group_cols])
    group_cols = list(group_cols)
    if freq == "MS":
        min_count = MIN_DAYS_PER_MONTH if min_count is None else min_count
        work = df[[*group_cols, date_col, value]].dropna(subset=[value]).copy()
        work["period"] = pd.to_datetime(work[date_col]).dt.to_period("M").dt.to_timestamp()
        out = (work.groupby([*group_cols, "period"], observed=True)[value]
                   .agg(mean="mean", n="count").reset_index())
    elif freq == "YS":
        min_count = MIN_MONTHS_PER_YEAR if min_count is None else min_count
        monthly = aggregate_period(df, value, "MS", group_cols, date_col=date_col)
        monthly = monthly[monthly["complete"]]
        monthly["period"] = monthly["period"].dt.to_period("Y").dt.to_timestamp()
        out = (monthly.groupby([*group_cols, "period"], observed=True)["mean"]
                      .agg(mean="mean", n="count").reset_index())
    else:
        raise ValueError("freq must be 'MS' (monthly) or 'YS' (annual)")
    out["complete"] = out["n"] >= min_count
    return out


def flag_outliers(df: pd.DataFrame, value: str = "pm25", group_col: str = "city_id",
                  threshold: float = OUTLIER_ROBUST_Z) -> pd.Series:
    """Robust z-score on log(value) within each group: |0.6745 (x - median) / MAD| > threshold.

    Log-transform is used because concentrations are right-skewed. Non-positive values and
    groups with MAD == 0 are never flagged. Outliers are *flagged*, not removed.
    """
    require_columns(df, [value, group_col])
    x = np.log(df[value].where(df[value] > 0))
    med = x.groupby(df[group_col], observed=True).transform("median")
    mad = (x - med).abs().groupby(df[group_col], observed=True).transform("median")
    z = 0.6745 * (x - med) / mad.replace(0, np.nan)
    return (z.abs() > threshold).fillna(False).astype(bool)


def identical_series_groups(daily: pd.DataFrame, cities: pd.DataFrame, value: str = "pm25",
                            decimals: int = 6) -> pd.DataFrame:
    """Group places whose entire daily series is identical (same model grid cell).

    Adds ``series_group`` (shared id), ``series_group_size`` and ``is_series_representative``
    (most populous member) to ``cities``. Inferential tests use representatives only, so one
    modelled series is never counted as several independent cities.
    """
    require_columns(daily, ["city_id", "date", value])
    wide = daily.pivot_table(index="date", columns="city_id", values=value, observed=True).round(decimals)
    sig = wide.T.apply(lambda r: hashlib.sha1(r.to_numpy(dtype="float64").tobytes()).hexdigest(), axis=1)
    codes = pd.Series(pd.factorize(sig)[0], index=sig.index, name="series_group")
    out = cities.drop(columns=["series_group", "series_group_size", "is_series_representative"], errors="ignore")
    out = out.merge(codes.rename_axis("city_id").reset_index(), on="city_id", how="left")
    out["series_group_size"] = out.groupby("series_group")["city_id"].transform("size")
    rep = out.sort_values(["series_group", "population"], ascending=[True, False]).drop_duplicates("series_group")
    out["is_series_representative"] = out["city_id"].isin(rep["city_id"])
    return out


def independent_units(df: pd.DataFrame, cities: pd.DataFrame) -> pd.DataFrame:
    """Keep only rows of series-representative cities (for inferential statistics)."""
    if "is_series_representative" not in cities.columns:
        return df
    keep = set(cities.loc[cities["is_series_representative"], "city_id"].astype(str))
    return df[df["city_id"].astype(str).isin(keep)]


def haversine_km(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 6371.0 * 2 * np.arcsin(np.sqrt(a))


def match_nearest_city(points: pd.DataFrame, candidates: pd.DataFrame, max_km: float = OVERLAP_MAX_KM) -> pd.DataFrame:
    """For each row of ``points`` (city, latitude, longitude) find the nearest candidate city.

    Returns one row per point with ``match_city_id``/``distance_km``; matches beyond ``max_km``
    are left empty.
    """
    rows = []
    for _, p in points.iterrows():
        d = haversine_km(p["latitude"], p["longitude"], candidates["latitude"].to_numpy(),
                         candidates["longitude"].to_numpy())
        i = int(np.argmin(d))
        ok = d[i] <= max_km
        rows.append({"city_id": p["city_id"], "city": p["city"],
                     "match_city_id": candidates.iloc[i]["city_id"] if ok else None,
                     "match_city_label": candidates.iloc[i]["city_label"] if ok else None,
                     "distance_km": float(d[i])})
    return pd.DataFrame(rows)


def build_source_overlap(hf_daily: pd.DataFrame, wb_daily: pd.DataFrame, wb_cities: pd.DataFrame,
                         max_km: float = OVERLAP_MAX_KM) -> pd.DataFrame:
    """Pair HF daily PM2.5 with the nearest WB city's PM2.5 on the same calendar date.

    Used only for source-to-source *comparison*; the two series are never pooled.
    """
    if hf_daily.empty or wb_daily.empty:
        return pd.DataFrame()
    pts = hf_daily.groupby("city_id", as_index=False).agg(city=("city", "first"), latitude=("latitude", "first"),
                                                          longitude=("longitude", "first"))
    matches = match_nearest_city(pts, wb_cities, max_km).dropna(subset=["match_city_id"])
    left = hf_daily[["city_id", "date", "pm25", "n_hours"]].rename(columns={"pm25": "pm25_hf"})
    left = left.merge(matches, on="city_id")
    right = wb_daily[["city_id", "date", "pm25"]].rename(columns={"city_id": "match_city_id", "pm25": "pm25_wb"})
    out = left.merge(right, on=["match_city_id", "date"], how="inner").dropna(subset=["pm25_hf", "pm25_wb"])
    return out.sort_values(["city", "date"]).reset_index(drop=True)


def join_weather(wb_daily: pd.DataFrame, weather: pd.DataFrame) -> pd.DataFrame:
    """Inner-join WB daily PM2.5 with ERA5 weather on (city_id, calendar date).

    Caveat (documented): WB daily day boundary is not specified by the source; weather uses
    the local (Asia/Karachi) day. Lagged correlations (±1 day) are reported as a sensitivity check.
    """
    if weather.empty:
        return pd.DataFrame()
    wcols = [c for c in weather.columns if c not in ("geonameid", "source_id", "value_type")]
    w = weather[wcols].rename(columns={"grid_latitude": "weather_grid_lat", "grid_longitude": "weather_grid_lon"})
    out = wb_daily.merge(w, on=["city_id", "date"], how="inner")
    out["weather_source_id"] = "openmeteo_era5"
    return out
