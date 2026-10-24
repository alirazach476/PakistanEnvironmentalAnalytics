"""Loading, schema/unit validation, date parsing, city normalisation, duplicates,
missing data and empty/missing-column handling."""

import numpy as np
import pandas as pd
import pytest

from src.data import clean, load, validate
from src.data.clean import ExclusionLog


# --- loading -------------------------------------------------------------------
def test_load_table_csv_and_parquet(tmp_path):
    df = pd.DataFrame({"a": [1, 2], "b": ["x", "y"]})
    df.to_csv(tmp_path / "t.csv", index=False)
    df.to_parquet(tmp_path / "t.parquet", index=False)
    pd.testing.assert_frame_equal(load.load_table(tmp_path / "t.csv"), df)
    pd.testing.assert_frame_equal(load.load_table(tmp_path / "t.parquet"), df)


def test_load_table_errors(tmp_path):
    with pytest.raises(FileNotFoundError):
        load.load_table(tmp_path / "missing.csv")
    (tmp_path / "x.txt").write_text("hi")
    with pytest.raises(ValueError):
        load.load_table(tmp_path / "x.txt")


def test_load_processed_unknown_and_missing(monkeypatch, tmp_path):
    with pytest.raises(KeyError):
        load.load_processed("nope")
    monkeypatch.setitem(load.PROCESSED_TABLES, "wb_daily", tmp_path / "absent.parquet")
    with pytest.raises(load.DataNotPreparedError):
        load.load_processed("wb_daily")


# --- normalisation -------------------------------------------------------------
@pytest.mark.parametrize("raw,expected", [
    ("PM2.5", "pm25"), ("pm2_5", "pm25"), (" Temperature ", "temperature"), ("relative_humidity_2m_mean", "humidity"),
    ("Wind Speed (km/h)", "wind_speed_km_h"), ("precipitation_sum", "precipitation"), ("lat", "latitude"),
])
def test_normalize_column_name(raw, expected):
    assert clean.normalize_column_name(raw) == expected


def test_normalize_columns_rejects_collisions():
    with pytest.raises(ValueError):
        clean.normalize_columns(pd.DataFrame(columns=["PM2.5", "pm2_5"]))


@pytest.mark.parametrize("raw,expected", [
    ("  lahore ", "Lahore"), ("RAHIM  YAR KHAN", "Rahim Yar Khan"), ("islamabad capital territory", "Islamabad"),
    ("D.I. Khan", "Dera Ismail Khan"), ("", np.nan), (None, np.nan),
])
def test_normalize_city_name(raw, expected):
    out = clean.normalize_city_name(raw)
    assert (pd.isna(out) and pd.isna(expected)) or out == expected


def test_city_key_merges_spacing_variants():
    assert clean.city_key("Arif Wala") == clean.city_key("Arifwala") == "arifwala"


# --- dates ---------------------------------------------------------------------
def test_parse_datetime_invalid_becomes_nat():
    s = clean.parse_datetime(pd.Series(["2024-01-05", "not a date", None]))
    assert s.iloc[0] == pd.Timestamp("2024-01-05") and s.iloc[1:].isna().all()


def test_parse_datetime_timezone_conversion():
    aware = clean.parse_datetime(pd.Series(["2024-01-01T00:00:00Z"]), target_tz="Asia/Karachi")
    assert aware.iloc[0] == pd.Timestamp("2024-01-01 05:00:00") and aware.dt.tz is None
    naive = clean.parse_datetime(pd.Series(["2024-01-01 00:00"]), source_tz="UTC", target_tz="Asia/Karachi")
    assert naive.iloc[0] == pd.Timestamp("2024-01-01 05:00:00")
    norm = clean.parse_datetime(pd.Series(["2024-03-04 17:45"]), normalize=True)
    assert norm.iloc[0] == pd.Timestamp("2024-03-04")


# --- validation ----------------------------------------------------------------
def test_validate_schema_detects_problems():
    df = pd.DataFrame({"city_id": ["a"], "date": ["2024-01-01"], "value_type": ["guess"]})
    rep = validate.validate_schema(df, {"city_id": "O", "date": "M", "pm25": "f"}, "t")
    text = " ".join(rep.issues)
    assert not rep.ok and "missing columns" in text and "'date'" in text and "value_type" in text
    with pytest.raises(ValueError):
        rep.raise_if_failed()


def test_out_of_range_and_non_numeric_masks():
    df = pd.DataFrame({"pm25": [10, -1, 2000, np.nan], "humidity": [50, 101, 0, 100]})
    assert validate.out_of_range_mask(df, "pm25").tolist() == [False, True, True, False]
    assert validate.out_of_range_mask(df, "humidity").tolist() == [False, True, False, False]
    assert validate.non_numeric_mask(pd.Series(["1", "x", None])).tolist() == [False, True, False]


def test_conflicting_duplicates():
    df = pd.DataFrame({"k": [1, 1, 2, 2], "v": [5.0, 5.0, 1.0, 9.0]})
    assert validate.conflicting_duplicates(df, ["k"], ["v"]).tolist() == [False, False, True, True]


def test_require_columns_names_all_missing():
    with pytest.raises(KeyError, match="a.*b"):
        validate.require_columns(pd.DataFrame({"c": [1]}), ["a", "b", "c"])


# --- World Bank cleaning --------------------------------------------------------
def test_clean_wb_happy_path(wb_raw):
    log = ExclusionLog()
    df, cities = clean.clean_wb(wb_raw, log)
    assert len(df) == len(wb_raw) and df["city_id"].nunique() == 4
    assert set(df["value_type"]) == {"modelled"} and set(df["source_id"]) == {"wb_pm25"}
    assert pd.api.types.is_datetime64_any_dtype(df["date"])
    assert set(cities["province"]) == {"Punjab", "Sindh", "Khyber Pakhtunkhwa", "Balochistan"}
    assert not df.duplicated(["city_id", "date"]).any()


def test_clean_wb_exclusions_are_logged(wb_raw):
    bad = wb_raw.astype({"pm25": object})
    bad.loc[0, "pm25"] = -5                                  # out of range
    bad.loc[1, "pm25"] = "abc"                                # non-numeric
    bad.loc[2, "date"] = "2019-13-45"                         # bad date
    bad.loc[3, "pm25"] = np.nan                               # missing
    dup_exact = bad.iloc[[10]]
    dup_conflict = bad.iloc[[20]].assign(pm25=999.0)
    other = bad.iloc[[30]].assign(adm0_wb_a3="AFG")
    bad = pd.concat([bad, dup_exact, dup_conflict, other], ignore_index=True)
    log = ExclusionLog()
    df, _ = clean.clean_wb(bad, log)
    rules = log.to_frame().set_index("rule")["n_rows"]
    assert rules["unparseable date"] == 1
    assert rules["non-numeric PM2.5"] == 1
    assert rules["missing PM2.5"] == 1
    assert rules.filter(like="plausible range").iloc[0] == 1
    assert rules["exact duplicate of key + values"] == 1
    assert rules.filter(like="conflicting duplicate").iloc[0] == 2
    assert rules["country is not Pakistan (PAK)"] == 1
    assert len(df) == len(wb_raw) - 4 - 1  # 4 invalid rows, 1 original row whose key conflicted


def test_clean_wb_disambiguates_shared_names(wb_raw):
    raw = wb_raw.copy()
    raw.loc[raw["geonameid"] == 1001, "city"] = "Town A"   # two places named Town A, different provinces
    df, cities = clean.clean_wb(raw, ExclusionLog())
    assert cities["city_label"].is_unique
    assert cities["name_ambiguous"].sum() == 2


def test_clean_wb_missing_column_raises(wb_raw):
    with pytest.raises(KeyError):
        clean.clean_wb(wb_raw.drop(columns=["pm25"]), ExclusionLog())


def test_clean_wb_rerun_is_idempotent(wb_raw):
    a, _ = clean.clean_wb(wb_raw, ExclusionLog())
    b, _ = clean.clean_wb(pd.concat([wb_raw, wb_raw]), ExclusionLog())   # duplicated input
    pd.testing.assert_frame_equal(a, b)


# --- HF cleaning ---------------------------------------------------------------
def test_clean_hf(hf_raw):
    raw = hf_raw.copy()
    raw.loc[0, "humidity"] = 150          # invalid cell -> NaN, row kept
    raw.loc[1, "pm10"] = 10.0             # pm2.5 > pm10 -> flagged
    log = ExclusionLog()
    df = clean.clean_hf(raw, log)
    assert len(df) == len(raw)
    assert "aqi_category" not in df.columns and "season" not in df.columns
    assert df["humidity"].isna().sum() == 1
    assert set(df["city"]) == {"Lahore", "Karachi"}
    assert set(df["value_type"]) == {"modelled"}
    assert (log.to_frame()["rule"] == "PM2.5 greater than PM10").any()


def test_clean_weather_empty_payloads():
    out = clean.clean_weather([], ExclusionLog())
    assert out.empty and "temperature" in out.columns
