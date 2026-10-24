"""Rebuild all processed, analysis-ready datasets from data/raw.

Usage:
    python scripts/prepare_data.py            # uses existing raw files
    python scripts/prepare_data.py --extract  # first (re)extract the Pakistan subset from the WB zip
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.data.pipeline import run_pipeline  # noqa: E402
from src.utils import paths  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--extract", action="store_true", help="re-extract the Pakistan subset from the WB archive")
    args = ap.parse_args()
    if args.extract or not paths.WB_PAK_SUBSET.exists():
        from scripts.extract_worldbank_pakistan import extract
        extract()
    run_pipeline(verbose=True)


if __name__ == "__main__":
    main()
