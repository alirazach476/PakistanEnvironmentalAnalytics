"""Extract Pakistan rows from the World Bank Global PM2.5 Watch regional archive.

The regional archive (~75 MB zipped, ~1 GB CSV) is streamed in chunks and only
rows with ``adm0_wb_a3 == 'PAK'`` are written to a Parquet subset. The original
zip is never modified.

Usage:
    python scripts/extract_worldbank_pakistan.py
"""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.utils.paths import WB_RAW_DIR, WB_ZIP_NAME, WB_PAK_SUBSET  # noqa: E402

COUNTRY_CODE = "PAK"
CHUNK_ROWS = 1_000_000


def extract(zip_path: Path = WB_RAW_DIR / WB_ZIP_NAME, out_path: Path = WB_PAK_SUBSET) -> pd.DataFrame:
    if not zip_path.exists():
        raise FileNotFoundError(
            f"World Bank archive not found at {zip_path}. Download it manually from "
            "https://datacatalogfiles.worldbank.org/ddh-published/0067162/DR0096340/"
            "PM25_Middle_East_North_Africa_Afghanistan_Pakistan.zip and place it there."
        )
    parts: list[pd.DataFrame] = []
    total = 0
    with zipfile.ZipFile(zip_path) as zf:
        csv_name = next(n for n in zf.namelist() if n.lower().endswith(".csv"))
        with zf.open(csv_name) as fh:
            reader = pd.read_csv(fh, chunksize=CHUNK_ROWS, dtype={"adm1cd_c": "string", "geonameid": "Int64"})
            for chunk in reader:
                total += len(chunk)
                sub = chunk[chunk["adm0_wb_a3"] == COUNTRY_CODE]
                if not sub.empty:
                    parts.append(sub)
    if not parts:
        raise ValueError(f"No rows with adm0_wb_a3 == {COUNTRY_CODE!r} found in {zip_path.name}")
    df = pd.concat(parts, ignore_index=True)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out_path, index=False)
    print(f"Scanned {total:,} rows; wrote {len(df):,} Pakistan rows "
          f"({df['geonameid'].nunique()} cities) to {out_path}")
    return df


if __name__ == "__main__":
    extract()
