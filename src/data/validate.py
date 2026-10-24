"""Schema, type, range and duplicate validation.

Validation never mutates data: functions return masks or issue lists so that
cleaning code can decide (and log) what to exclude.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from src.utils.config import PLAUSIBLE_RANGES, VALUE_TYPES

# Expected schemas of processed tables: column -> dtype kind
#   "f" float, "i" integer, "M" datetime, "O" string/categorical, "b" bool
SCHEMAS: dict[str, dict[str, str]] = {
    "wb_daily": {
        "city_id": "O", "city_label": "O", "province": "O", "date": "M", "pm25": "f",
        "source_id": "O", "value_type": "O", "year": "i", "month": "i", "season": "O",
        "is_outlier": "b",
    },
    "wb_cities": {
        "city_id": "O", "geonameid": "i", "city": "O", "city_label": "O", "province": "O",
        "latitude": "f", "longitude": "f", "population": "i",
    },
    "hf_hourly": {
        "city_id": "O", "city": "O", "timestamp": "M", "date": "M", "hour": "i", "pm25": "f",
        "source_id": "O", "value_type": "O",
    },
    "hf_daily": {
        "city_id": "O", "city": "O", "date": "M", "pm25": "f", "n_hours": "i",
        "source_id": "O", "value_type": "O",
    },
    "weather_daily": {
        "city_id": "O", "date": "M", "temperature": "f", "humidity": "f", "wind_speed": "f",
        "precipitation": "f", "source_id": "O", "value_type": "O",
    },
}


@dataclass
class ValidationReport:
    table: str
    issues: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issues

    def raise_if_failed(self) -> None:
        if self.issues:
            raise ValueError(f"Validation failed for {self.table}: " + "; ".join(self.issues))


def _kind_matches(series: pd.Series, kind: str) -> bool:
    dtype = series.dtype
    if kind == "O":
        return pd.api.types.is_object_dtype(dtype) or pd.api.types.is_string_dtype(dtype) or \
            isinstance(dtype, pd.CategoricalDtype)
    if kind == "f":
        return pd.api.types.is_float_dtype(dtype)
    if kind == "i":
        return pd.api.types.is_integer_dtype(dtype)
    if kind == "M":
        return pd.api.types.is_datetime64_any_dtype(dtype)
    if kind == "b":
        return pd.api.types.is_bool_dtype(dtype)
    raise ValueError(f"Unknown dtype kind {kind!r}")


def validate_schema(df: pd.DataFrame, schema: dict[str, str] | str, table: str | None = None) -> ValidationReport:
    """Check that required columns exist with the expected dtype kinds."""
    if isinstance(schema, str):
        table = table or schema
        schema = SCHEMAS[schema]
    report = ValidationReport(table or "table")
    missing = [c for c in schema if c not in df.columns]
    if missing:
        report.issues.append(f"missing columns: {missing}")
    for col, kind in schema.items():
        if col in df.columns and not _kind_matches(df[col], kind):
            report.issues.append(f"column {col!r} has dtype {df[col].dtype}, expected kind {kind!r}")
    if "value_type" in df.columns:
        bad = set(df["value_type"].dropna().astype(str).unique()) - set(VALUE_TYPES)
        if bad:
            report.issues.append(f"unknown value_type labels: {sorted(bad)}")
    return report


def require_columns(df: pd.DataFrame, columns: list[str] | tuple[str, ...]) -> None:
    """Raise a KeyError naming every missing column (used by analysis functions)."""
    missing = [c for c in columns if c not in df.columns]
    if missing:
        raise KeyError(f"Required column(s) missing: {missing}")


def out_of_range_mask(df: pd.DataFrame, column: str, ranges: dict = PLAUSIBLE_RANGES) -> pd.Series:
    """True where a non-null value falls outside the plausible range for ``column``."""
    if column not in ranges:
        return pd.Series(False, index=df.index)
    lo, hi = ranges[column]
    values = pd.to_numeric(df[column], errors="coerce")
    return values.notna() & ((values < lo) | (values > hi))


def non_numeric_mask(series: pd.Series) -> pd.Series:
    """True where a value is present but cannot be parsed as a number."""
    coerced = pd.to_numeric(series, errors="coerce")
    return series.notna() & coerced.isna()


def duplicate_key_mask(df: pd.DataFrame, keys: list[str]) -> pd.Series:
    """True for every row whose key appears more than once."""
    return df.duplicated(keys, keep=False)


def conflicting_duplicates(df: pd.DataFrame, keys: list[str], value_cols: list[str]) -> pd.Series:
    """True for rows whose key is duplicated *and* whose values differ between copies."""
    dup = df[duplicate_key_mask(df, keys)]
    if dup.empty:
        return pd.Series(False, index=df.index)
    n_distinct = dup.groupby(keys, dropna=False)[value_cols].nunique(dropna=False).max(axis=1)
    conflicting_keys = n_distinct[n_distinct > 1].index
    key_index = pd.MultiIndex.from_frame(df[keys]) if len(keys) > 1 else pd.Index(df[keys[0]])
    return pd.Series(key_index.isin(conflicting_keys), index=df.index)


def check_plausible_ranges(df: pd.DataFrame, columns: list[str] | None = None) -> pd.DataFrame:
    """Summary of out-of-range counts per column."""
    cols = [c for c in (columns or df.columns) if c in PLAUSIBLE_RANGES and c in df.columns]
    rows = []
    for c in cols:
        lo, hi = PLAUSIBLE_RANGES[c]
        m = out_of_range_mask(df, c)
        rows.append({"column": c, "min_allowed": lo, "max_allowed": hi,
                     "n_out_of_range": int(m.sum()), "n_non_null": int(df[c].notna().sum())})
    return pd.DataFrame(rows)
