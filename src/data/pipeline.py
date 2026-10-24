"""End-to-end, idempotent data preparation.

Every run rebuilds all processed tables from the raw files (outputs are
overwritten, never appended), so repeated runs cannot accumulate duplicates.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from src.data import clean, load, transform, validate
from src.utils import paths
from src.utils.config import (MIN_DAYS_PER_MONTH, MIN_HOURS_PER_DAY, MIN_MONTHS_PER_YEAR, OUTLIER_ROBUST_Z,
                              OVERLAP_MAX_KM, SOURCES)


def sha256(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while block := fh.read(chunk):
            h.update(block)
    return h.hexdigest()


def _write(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    df.to_parquet(tmp, index=False)
    tmp.replace(path)


def run_pipeline(verbose: bool = True) -> dict:
    log = clean.ExclusionLog()
    say = print if verbose else (lambda *a, **k: None)
    inputs: dict[str, dict] = {}

    # --- World Bank ---------------------------------------------------------
    wb_raw = load.load_wb_raw()
    inputs["wb_pm25"] = {"file": str(paths.WB_PAK_SUBSET.relative_to(paths.ROOT)), "rows": len(wb_raw),
                         "sha256": sha256(paths.WB_PAK_SUBSET)}
    zip_path = paths.WB_RAW_DIR / paths.WB_ZIP_NAME
    if zip_path.exists():
        inputs["wb_pm25"]["archive_sha256"] = sha256(zip_path)
    wb, wb_cities = clean.clean_wb(wb_raw, log)
    wb = transform.add_calendar(wb)
    wb["is_outlier"] = transform.flag_outliers(wb, "pm25", "city_id")
    log.add("wb_pm25", "outlier_flag", f"robust |z| > {OUTLIER_ROBUST_Z} on log(PM2.5) within city",
            int(wb["is_outlier"].sum()), "flagged (kept)", "pm25")
    wb_cities = transform.identical_series_groups(wb, wb_cities)
    shared = wb_cities[wb_cities["series_group_size"] > 1]
    if len(shared):
        log.add("wb_pm25", "identity_check", "identical daily PM2.5 series shared by several places "
                "(same model grid cell)", len(shared), "flagged (kept); inferential tests use one "
                "representative per series", "pm25", ", ".join(shared["city_label"].head(6)))
    from src.analysis.data_quality import model_artifact_flags
    flags = model_artifact_flags(wb)
    wb_cities = wb_cities.drop(columns=[c for c in flags.columns if c != "city_id"], errors="ignore").merge(
        flags, on="city_id", how="left")
    wb_cities["artifact_flag"] = wb_cities["artifact_flag"].fillna(False).astype(bool)
    wb_cities["artifact_reason"] = wb_cities["artifact_reason"].fillna("")
    for reason, n in wb_cities.loc[wb_cities["artifact_flag"], "artifact_reason"].value_counts().items():
        log.add("wb_pm25", "model_artifact_screen", reason, int(n), "city flagged (kept); optional exclusion filter",
                "pm25", ", ".join(wb_cities.loc[wb_cities["artifact_reason"] == reason, "city_label"].head(5)))
    say(f"Model-artifact screen: {int(wb_cities['artifact_flag'].sum())} of {len(wb_cities)} places flagged")
    for c in ("city_id", "city", "city_label", "province", "adm1_code", "source_id", "value_type", "day_of_week"):
        wb[c] = wb[c].astype("category")
    anchors = clean.verify_adm1_anchors(wb_cities)
    say(f"WB: {len(wb):,} rows, {wb['city_id'].nunique()} cities; ADM1 anchors verified: {anchors}")

    # --- Kaggle/HF hourly ---------------------------------------------------
    hf_path = paths.HF_RAW_DIR / paths.HF_CSV_NAME
    hf_hourly = pd.DataFrame()
    hf_daily = pd.DataFrame()
    if hf_path.exists():
        hf_raw = load.load_hf_raw(hf_path)
        inputs["hf_aq"] = {"file": str(hf_path.relative_to(paths.ROOT)), "rows": len(hf_raw), "sha256": sha256(hf_path)}
        hf_hourly = clean.clean_hf(hf_raw, log)
        value_cols = [c for c in clean.HF_VALUE_COLS if c in hf_hourly.columns]
        hf_daily = transform.hourly_to_daily(hf_hourly, value_cols)
        hf_daily = transform.add_calendar(hf_daily)
        short_days = int((hf_daily["n_hours"] < MIN_HOURS_PER_DAY).sum())
        log.add("hf_aq", "aggregation", f"hourly->daily requires >= {MIN_HOURS_PER_DAY} valid hours",
                short_days, "daily value set to NaN" if short_days else "no days affected")
        hf_hourly = transform.add_calendar(hf_hourly)
        say(f"HF: {len(hf_hourly):,} hourly rows -> {len(hf_daily):,} city-days")
    else:
        say(f"HF source not found at {hf_path}; skipped")

    # --- Open-Meteo ERA5 weather ---------------------------------------------
    payloads, wmanifest = load.load_weather_raw()
    weather = clean.clean_weather(payloads, log)
    if payloads:
        inputs["openmeteo_era5"] = {"dir": str(paths.WEATHER_RAW_DIR.relative_to(paths.ROOT)),
                                    "cities": len(payloads), "model": wmanifest.get("model"),
                                    "timezone": wmanifest.get("timezone")}
    wb_weather = transform.join_weather(wb, weather) if not weather.empty else pd.DataFrame()
    if not wb_weather.empty:
        for c in ("city_id", "city", "city_label", "province", "adm1_code", "source_id", "value_type"):
            wb_weather[c] = wb_weather[c].astype(str)
    say(f"Weather: {weather['city_id'].nunique() if not weather.empty else 0} cities, "
        f"{len(wb_weather):,} PM2.5-weather city-days")

    # --- Source overlap -------------------------------------------------------
    overlap = transform.build_source_overlap(hf_daily, wb.astype({"city_id": str}), wb_cities, OVERLAP_MAX_KM)
    say(f"Overlap: {len(overlap):,} paired city-days across {overlap['city_id'].nunique() if len(overlap) else 0} cities")

    # --- Validate & write ----------------------------------------------------
    reports = {
        "wb_daily": validate.validate_schema(wb, "wb_daily"),
        "wb_cities": validate.validate_schema(wb_cities, "wb_cities"),
    }
    if not hf_hourly.empty:
        reports["hf_hourly"] = validate.validate_schema(hf_hourly, "hf_hourly")
        reports["hf_daily"] = validate.validate_schema(hf_daily, "hf_daily")
    if not weather.empty:
        reports["weather_daily"] = validate.validate_schema(weather, "weather_daily")
    for r in reports.values():
        r.raise_if_failed()
    for name, keys, frame in (("wb_daily", ["city_id", "date"], wb), ("hf_hourly", ["city_id", "timestamp"], hf_hourly),
                              ("weather_daily", ["city_id", "date"], weather)):
        if not frame.empty and frame.duplicated(keys).any():
            raise ValueError(f"{name} still contains duplicate keys after cleaning")

    _write(wb, paths.WB_DAILY)
    _write(wb_cities, paths.WB_CITIES)
    for frame, path in ((hf_hourly, paths.HF_HOURLY), (hf_daily, paths.HF_DAILY), (weather, paths.WEATHER_DAILY),
                        (wb_weather, paths.WB_WEATHER_DAILY), (overlap, paths.SOURCE_OVERLAP)):
        if frame.empty:
            path.unlink(missing_ok=True)
        else:
            _write(frame, path)
    log.to_frame().to_csv(paths.EXCLUSIONS_LOG, index=False)

    manifest = {
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "inputs": inputs,
        "sources": {k: v for k, v in SOURCES.items() if k in inputs},
        "outputs": {
            "wb_daily": {"rows": len(wb), "cities": int(wb["city_id"].nunique()),
                         "date_min": str(wb["date"].min().date()), "date_max": str(wb["date"].max().date())},
            "hf_hourly": {"rows": len(hf_hourly), "cities": int(hf_hourly["city_id"].nunique()) if len(hf_hourly) else 0},
            "hf_daily": {"rows": len(hf_daily)},
            "weather_daily": {"rows": len(weather), "cities": int(weather["city_id"].nunique()) if len(weather) else 0},
            "wb_weather_daily": {"rows": len(wb_weather)},
            "source_overlap": {"rows": len(overlap)},
        },
        "adm1_anchor_check": anchors,
        "rules": {"min_hours_per_day": MIN_HOURS_PER_DAY, "min_days_per_month": MIN_DAYS_PER_MONTH,
                  "min_months_per_year": MIN_MONTHS_PER_YEAR, "outlier_robust_z": OUTLIER_ROBUST_Z,
                  "overlap_max_km": OVERLAP_MAX_KM},
    }
    paths.PIPELINE_MANIFEST.write_text(json.dumps(manifest, indent=2))
    say(f"Wrote processed tables to {paths.PROCESSED_DIR}")
    return manifest
