"""Loading raw source files and processed analytical tables.

Raw loaders return source data untouched (apart from parsing the file format).
Processed loaders raise a clear, actionable error if the pipeline has not run.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from src.utils import paths


class DataNotPreparedError(FileNotFoundError):
    """Raised when a processed dataset is missing."""


def load_table(path: str | Path, **kwargs) -> pd.DataFrame:
    """Load a CSV or Parquet file based on its extension."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    suffix = "".join(path.suffixes[-2:]).lower() if path.suffix == ".gz" else path.suffix.lower()
    if suffix in (".parquet", ".pq"):
        return pd.read_parquet(path, **kwargs)
    if suffix in (".csv", ".csv.gz"):
        return pd.read_csv(path, **kwargs)
    raise ValueError(f"Unsupported file type for {path.name!r}; expected .csv, .csv.gz or .parquet")


# ---------------------------------------------------------------------------
# Raw sources
# ---------------------------------------------------------------------------
def load_wb_raw(path: Path = paths.WB_PAK_SUBSET) -> pd.DataFrame:
    """Pakistan subset of the World Bank archive (created by scripts/extract_worldbank_pakistan.py)."""
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. Run `python scripts/extract_worldbank_pakistan.py` after placing "
            f"{paths.WB_ZIP_NAME} in {paths.WB_RAW_DIR}."
        )
    return load_table(path)


def load_hf_raw(path: Path = paths.HF_RAW_DIR / paths.HF_CSV_NAME) -> pd.DataFrame:
    return load_table(path)


def load_weather_raw(directory: Path = paths.WEATHER_RAW_DIR) -> tuple[list[dict], dict]:
    """Return the stored Open-Meteo JSON payloads and their manifest."""
    manifest_path = directory / "manifest.json"
    if not manifest_path.exists():
        return [], {}
    manifest = json.loads(manifest_path.read_text())
    payloads = []
    for geonameid, meta in manifest.get("cities", {}).items():
        f = directory / meta["file"]
        if f.exists():
            payloads.append({"geonameid": int(geonameid), "meta": meta, "payload": json.loads(f.read_text())})
    return payloads, manifest


# ---------------------------------------------------------------------------
# Processed tables
# ---------------------------------------------------------------------------
PROCESSED_TABLES = {
    "wb_daily": paths.WB_DAILY,
    "wb_cities": paths.WB_CITIES,
    "hf_hourly": paths.HF_HOURLY,
    "hf_daily": paths.HF_DAILY,
    "weather_daily": paths.WEATHER_DAILY,
    "wb_weather_daily": paths.WB_WEATHER_DAILY,
    "source_overlap": paths.SOURCE_OVERLAP,
}


def load_processed(name: str) -> pd.DataFrame:
    if name not in PROCESSED_TABLES:
        raise KeyError(f"Unknown processed table {name!r}; choose from {sorted(PROCESSED_TABLES)}")
    path = PROCESSED_TABLES[name]
    if not path.exists():
        raise DataNotPreparedError(
            f"Processed table {path.name} is missing. Run `python scripts/prepare_data.py` first."
        )
    return pd.read_parquet(path)


def load_manifest() -> dict:
    if not paths.PIPELINE_MANIFEST.exists():
        raise DataNotPreparedError("Pipeline manifest missing. Run `python scripts/prepare_data.py` first.")
    return json.loads(paths.PIPELINE_MANIFEST.read_text())


def load_exclusions() -> pd.DataFrame:
    if not paths.EXCLUSIONS_LOG.exists():
        return pd.DataFrame(columns=["source_id", "step", "rule", "column", "n_rows", "action", "example"])
    return pd.read_csv(paths.EXCLUSIONS_LOG)


def processed_available() -> bool:
    return all(p.exists() for p in (paths.WB_DAILY, paths.WB_CITIES, paths.PIPELINE_MANIFEST))
