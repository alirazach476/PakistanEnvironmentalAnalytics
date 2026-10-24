"""Canonical filesystem locations used across the project."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
SAMPLE_DIR = DATA_DIR / "sample"
REPORTS_DIR = ROOT / "reports"
DOCS_DIR = ROOT / "docs"

WB_RAW_DIR = RAW_DIR / "worldbank_pm25"
WB_ZIP_NAME = "PM25_Middle_East_North_Africa_Afghanistan_Pakistan.zip"
WB_PAK_SUBSET = WB_RAW_DIR / "worldbank_pm25_pakistan_subset.parquet"

HF_RAW_DIR = RAW_DIR / "hf_pakistan_aq"
HF_CSV_NAME = "pakistan_air_quality_final_clean.csv"

WEATHER_RAW_DIR = RAW_DIR / "openmeteo_weather"

# Processed, analysis-ready outputs (one per source: sources are never merged row-wise)
WB_DAILY = PROCESSED_DIR / "wb_pm25_daily.parquet"
WB_CITIES = PROCESSED_DIR / "wb_cities.parquet"
HF_HOURLY = PROCESSED_DIR / "hf_hourly.parquet"
HF_DAILY = PROCESSED_DIR / "hf_daily.parquet"
WEATHER_DAILY = PROCESSED_DIR / "weather_daily.parquet"
WB_WEATHER_DAILY = PROCESSED_DIR / "wb_weather_daily.parquet"
EXCLUSIONS_LOG = PROCESSED_DIR / "exclusions_log.csv"
PIPELINE_MANIFEST = PROCESSED_DIR / "pipeline_manifest.json"
SOURCE_OVERLAP = PROCESSED_DIR / "source_overlap_daily.parquet"
