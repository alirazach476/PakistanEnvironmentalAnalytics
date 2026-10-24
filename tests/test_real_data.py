"""Integration checks on the real prepared datasets (skipped if not prepared).

These assert *structural* properties (source separation, no synthetic rows,
no duplicate keys, units/ranges) — never specific findings.
"""

import pandas as pd
import pytest

from src.data import load
from src.data.validate import validate_schema
from src.utils.config import PLAUSIBLE_RANGES

pytestmark = pytest.mark.skipif(not load.processed_available(), reason="processed data not prepared")


def test_processed_tables_match_schema():
    for name in ("wb_daily", "wb_cities", "hf_hourly", "hf_daily", "weather_daily"):
        df = load.load_processed(name)
        validate_schema(df, name).raise_if_failed()


def test_sources_are_separate_and_labelled():
    wb = load.load_processed("wb_daily")
    hf = load.load_processed("hf_hourly")
    assert set(wb["source_id"].astype(str)) == {"wb_pm25"}
    assert set(hf["source_id"].astype(str)) == {"hf_aq"}
    assert set(wb["value_type"].astype(str)) == {"modelled"} and set(hf["value_type"].astype(str)) == {"modelled"}
    assert not set(wb["city_id"].astype(str)) & set(hf["city_id"].astype(str))


def test_no_synthetic_rows_in_real_outputs():
    for name in load.PROCESSED_TABLES:
        try:
            df = load.load_processed(name)
        except load.DataNotPreparedError:
            continue
        if "value_type" in df.columns:
            assert "synthetic" not in set(df["value_type"].astype(str)), name


def test_no_duplicate_keys_and_values_in_range():
    wb = load.load_processed("wb_daily")
    assert not wb.duplicated(["city_id", "date"]).any()
    lo, hi = PLAUSIBLE_RANGES["pm25"]
    assert wb["pm25"].between(lo, hi).all()
    hf = load.load_processed("hf_hourly")
    assert not hf.duplicated(["city_id", "timestamp"]).any()


def test_overlap_table_keeps_sources_in_separate_columns():
    ov = load.load_processed("source_overlap")
    assert {"pm25_hf", "pm25_wb", "distance_km"} <= set(ov.columns)
    assert (ov["distance_km"] <= 25).all()


def test_pipeline_is_idempotent(tmp_path, monkeypatch):
    """Running the pipeline again reproduces identical row counts (no accumulation)."""
    from src.data.pipeline import run_pipeline
    from src.utils import paths

    before = load.load_manifest()["outputs"]
    if not paths.WB_PAK_SUBSET.exists():
        pytest.skip("raw subset not available")
    after = run_pipeline(verbose=False)["outputs"]
    assert before == after
