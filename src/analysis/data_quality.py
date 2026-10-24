"""Data-quality diagnostics: completeness, gaps, duplicates, validity, outliers,
identity checks, timestamp alignment and source-to-source comparison."""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.analysis.correlations import correlation
from src.data.transform import haversine_km
from src.data.validate import check_plausible_ranges, require_columns
from src.utils.config import ANNUAL_CONST_REL_TOL, ARTIFACT_BREAK_REL, ARTIFACT_BREAK_T, ARTIFACT_MIN_FIXED_YEARS


def completeness_by_city(df: pd.DataFrame, date_col: str = "date", city_col: str = "city_id",
                         value: str = "pm25", start=None, end=None, freq: str = "D") -> pd.DataFrame:
    """Observed vs expected periods per city over [start, end] (defaults to the data's span)."""
    require_columns(df, [date_col, city_col, value])
    d = pd.to_datetime(df[date_col])
    start = pd.Timestamp(start) if start is not None else d.min()
    end = pd.Timestamp(end) if end is not None else d.max()
    expected = len(pd.date_range(start, end, freq=freq))
    sub = df[(d >= start) & (d <= end)]
    obs = sub.dropna(subset=[value]).groupby(city_col, observed=True)[date_col].nunique()
    out = obs.rename("n_observed").reset_index()
    out["n_expected"] = expected
    out["completeness_pct"] = 100 * out["n_observed"] / expected
    return out.sort_values("completeness_pct").reset_index(drop=True)


def find_gaps(dates: pd.Series, freq: str = "D") -> pd.DataFrame:
    """Runs of missing periods between the first and last date: start, end, length."""
    d = pd.DatetimeIndex(pd.to_datetime(pd.Series(dates).dropna().unique())).sort_values()
    if d.empty:
        return pd.DataFrame(columns=["gap_start", "gap_end", "length"])
    full = pd.date_range(d.min(), d.max(), freq=freq)
    missing = full.difference(d)
    if missing.empty:
        return pd.DataFrame(columns=["gap_start", "gap_end", "length"])
    s = pd.Series(missing)
    run = (s.diff() != pd.Timedelta(1, unit=freq if freq != "D" else "D")).cumsum()
    g = s.groupby(run).agg(["min", "max", "count"])
    return g.rename(columns={"min": "gap_start", "max": "gap_end", "count": "length"}).reset_index(drop=True)


def missing_dates_pattern(gaps: pd.DataFrame) -> dict:
    """Describe whether missing dates are systematically month-end days."""
    if gaps.empty:
        return {"n_missing": 0, "all_month_end": False, "share_month_end": np.nan}
    days = pd.concat([pd.Series(pd.date_range(r.gap_start, r.gap_end)) for r in gaps.itertuples()])
    month_end = days.dt.is_month_end
    return {"n_missing": int(len(days)), "all_month_end": bool(month_end.all()),
            "share_month_end": float(month_end.mean()), "max_run": int(gaps["length"].max())}


def city_gap_summary(df: pd.DataFrame, date_col: str = "date", city_col: str = "city_id") -> pd.DataFrame:
    rows = []
    for key, g in df.groupby(city_col, observed=True):
        gaps = find_gaps(g[date_col])
        rows.append({city_col: key, "n_gaps": len(gaps), "missing_days": int(gaps["length"].sum()) if len(gaps) else 0,
                     "longest_gap": int(gaps["length"].max()) if len(gaps) else 0})
    return pd.DataFrame(rows)


def missingness_matrix(df: pd.DataFrame, columns: list[str], by: str = "city") -> pd.DataFrame:
    """Percentage of missing values per group (rows) and variable (columns)."""
    cols = [c for c in columns if c in df.columns]
    require_columns(df, [by])
    return df.groupby(by, observed=True)[cols].apply(lambda g: g.isna().mean() * 100)


def duplicate_summary(df: pd.DataFrame, keys: list[str]) -> dict:
    require_columns(df, keys)
    n = len(df)
    dup_keys = int(df.duplicated(keys, keep="first").sum())
    exact = int(df.duplicated(keep="first").sum())
    return {"rows": n, "duplicate_key_rows": dup_keys, "exact_duplicate_rows": exact,
            "duplicate_key_rate_pct": 100 * dup_keys / n if n else np.nan}


def validation_summary(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    s = check_plausible_ranges(df, columns)
    if not s.empty:
        s["invalid_rate_pct"] = 100 * s["n_out_of_range"] / s["n_non_null"].replace(0, np.nan)
    return s


def outlier_summary(df: pd.DataFrame, flag_col: str = "is_outlier", by: str = "city_label") -> pd.DataFrame:
    require_columns(df, [flag_col, by])
    g = df.groupby(by, observed=True)[flag_col]
    return pd.DataFrame({"n_outliers": g.sum().astype(int), "n": g.size(),
                         "outlier_pct": 100 * g.mean()}).reset_index().sort_values("n_outliers", ascending=False)


def iqr_outlier_mask(values: pd.Series, k: float = 1.5) -> pd.Series:
    """Tukey fences (used for box-plot style display; the pipeline flag uses robust z)."""
    q1, q3 = values.quantile([0.25, 0.75])
    iqr = q3 - q1
    return (values < q1 - k * iqr) | (values > q3 + k * iqr)


def province_consistency(cities: pd.DataFrame, k: int = 5) -> pd.DataFrame:
    """Flag cities whose ADM1 code differs from the majority of their k nearest neighbours."""
    require_columns(cities, ["city_id", "latitude", "longitude", "adm1_code"])
    lat, lon = cities["latitude"].to_numpy(), cities["longitude"].to_numpy()
    rows = []
    for i, r in enumerate(cities.itertuples()):
        d = haversine_km(r.latitude, r.longitude, lat, lon)
        d[i] = np.inf
        nn = np.argsort(d)[:k]
        majority = cities.iloc[nn]["adm1_code"].mode().iloc[0]
        rows.append({"city_id": r.city_id, "neighbour_majority_adm1": majority,
                     "nearest_km": float(d[nn[0]]), "consistent": majority == r.adm1_code})
    return cities[["city_id", "city_label", "adm1_code", "province"]].merge(pd.DataFrame(rows), on="city_id")


def annual_mean_constancy(daily: pd.DataFrame, years: list[int] | None = None, rel_tol: float = ANNUAL_CONST_REL_TOL,
                          city_col: str = "city_id") -> pd.DataFrame:
    """Longest run of consecutive complete years whose annual means differ by less than ``rel_tol``.

    Real annual means typically vary by several percent from year to year; runs of near-identical values indicate
    that the model scales daily values to a fixed annual level for that place.
    """
    require_columns(daily, [city_col, "year", "pm25"])
    from src.analysis.trends import annual_series, complete_years
    years = years if years is not None else complete_years(daily)
    a = annual_series(daily, "pm25", (city_col,))
    a = a[a["year"].isin(years)].pivot_table(index=city_col, columns="year", values="mean", observed=True)
    rows = []
    for cid, r in a.iterrows():
        v = r.dropna()
        best, run, start, best_span = 1, 1, v.index[0] if len(v) else None, (None, None)
        for i in range(1, len(v)):
            if v.index[i] == v.index[i - 1] + 1 and abs(v.iloc[i] - v.iloc[i - 1]) < rel_tol * abs(v.iloc[i - 1]):
                run += 1
            else:
                run, start = 1, v.index[i]
            if run > best:
                best, best_span = run, (start, v.index[i])
        rows.append({city_col: cid, "fixed_annual_run": best if best > 1 else 0,
                     "fixed_annual_from": best_span[0] if best > 1 else np.nan,
                     "fixed_annual_to": best_span[1] if best > 1 else np.nan})
    return pd.DataFrame(rows)


def level_shift_scan(daily: pd.DataFrame, min_segment: int = 12, city_col: str = "city_id") -> pd.DataFrame:
    """Single most likely mean shift in each city's deseasonalised monthly anomalies.

    For every candidate break k (≥ ``min_segment`` months each side) a Welch t-statistic for the
    difference in means is computed; the maximum is reported with its date and size. This is a
    screening diagnostic (the max over many k inflates t), not a formal change-point test.
    """
    from src.analysis.trends import deseasonalize, monthly_series
    m = deseasonalize(monthly_series(daily, "pm25", (city_col,)), city_col)
    rows = []
    for cid, g in m.groupby(city_col, observed=True):
        g = g.sort_values("period")
        y, n = g["anomaly"].to_numpy(), len(g)
        best = (np.nan, pd.NaT, np.nan)
        for k in range(min_segment, n - min_segment + 1):
            a, b = y[:k], y[k:]
            se = np.sqrt(a.var(ddof=1) / a.size + b.var(ddof=1) / b.size)
            if se > 0:
                t = abs(b.mean() - a.mean()) / se
                if not np.isfinite(best[0]) or t > best[0]:
                    best = (t, g["period"].iloc[k], b.mean() - a.mean())
        rows.append({city_col: cid, "break_t": best[0], "break_date": best[1], "break_shift": best[2],
                     "mean_level": float(g["mean"].mean())})
    out = pd.DataFrame(rows)
    if len(out):
        out["break_shift_rel"] = out["break_shift"] / out["mean_level"]
    return out


def model_artifact_flags(daily: pd.DataFrame, city_col: str = "city_id") -> pd.DataFrame:
    """Combine both diagnostics into a per-city ``artifact_flag`` with a reason string."""
    const = annual_mean_constancy(daily, city_col=city_col)
    shift = level_shift_scan(daily, city_col=city_col)
    out = const.merge(shift, on=city_col, how="outer")
    fixed = out["fixed_annual_run"] >= ARTIFACT_MIN_FIXED_YEARS
    step = (out["break_t"] >= ARTIFACT_BREAK_T) & (out["break_shift_rel"].abs() >= ARTIFACT_BREAK_REL)
    out["artifact_flag"] = fixed | step
    out["artifact_reason"] = np.select(
        [fixed & step, fixed, step],
        ["fixed annual mean + abrupt level shift", "fixed annual mean across years", "abrupt level shift"], "")
    return out


def identical_series(df: pd.DataFrame, value: str, time_col: str = "date", city_col: str = "city") -> pd.DataFrame:
    """Pairs of cities whose full series of ``value`` are identical (shared model grid cell)."""
    require_columns(df, [value, time_col, city_col])
    wide = df.pivot_table(index=time_col, columns=city_col, values=value, observed=True)
    cols = list(wide.columns)
    rows = []
    for i, a in enumerate(cols):
        for b in cols[i + 1:]:
            pair = wide[[a, b]].dropna()
            if len(pair) and np.allclose(pair[a], pair[b]):
                rows.append({"city_a": a, "city_b": b, "variable": value, "n_identical": len(pair)})
    return pd.DataFrame(rows, columns=["city_a", "city_b", "variable", "n_identical"])


def diurnal_peak_alignment(hourly: pd.DataFrame, pollutant: str = "ozone", weather: str = "temperature") -> dict:
    """Compare the hour of mean ozone maximum with the hour of mean temperature maximum.

    Both normally peak in the early/mid afternoon local time. A large offset between them
    in the same table suggests the columns use different time references.
    """
    require_columns(hourly, ["hour", pollutant, weather])
    po = hourly.groupby("hour")[pollutant].mean()
    we = hourly.groupby("hour")[weather].mean()
    off = int(we.idxmax() - po.idxmax())
    off = (off + 12) % 24 - 12
    return {"pollutant": pollutant, "weather": weather, "pollutant_peak_hour": int(po.idxmax()),
            "weather_peak_hour": int(we.idxmax()), "pollutant_min_hour": int(po.idxmin()),
            "weather_min_hour": int(we.idxmin()), "offset_hours": off,
            "profile": pd.DataFrame({pollutant: po, weather: we}).reset_index()}


def source_comparison(overlap: pd.DataFrame) -> pd.DataFrame:
    """Per-city agreement between HF daily PM2.5 and nearest WB city on the same dates."""
    if overlap.empty:
        return pd.DataFrame()
    rows = []
    for (cid, city, wbl), g in overlap.groupby(["city_id", "city", "match_city_label"], observed=True):
        diff = g["pm25_hf"] - g["pm25_wb"]
        c = correlation(g["pm25_hf"], g["pm25_wb"], "pearson")
        rows.append({"city": city, "wb_match": wbl, "distance_km": float(g["distance_km"].iloc[0]), "n_days": len(g),
                     "median_hf": g["pm25_hf"].median(), "median_wb": g["pm25_wb"].median(),
                     "mean_bias_hf_minus_wb": diff.mean(), "mae": diff.abs().mean(),
                     "ratio_of_medians": g["pm25_hf"].median() / g["pm25_wb"].median(),
                     "pearson_r": c["r"], "r_ci_low_adj": c.get("ci_low_adj"), "r_ci_high_adj": c.get("ci_high_adj"),
                     "n_eff": c["n_eff"]})
    return pd.DataFrame(rows).sort_values("city").reset_index(drop=True)


def source_coverage(tables: dict[str, pd.DataFrame], meta: dict) -> pd.DataFrame:
    """One row per source: resolution, value type, cities, period, rows."""
    rows = []
    for sid, (df, time_col) in tables.items():
        if df is None or df.empty:
            continue
        t = pd.to_datetime(df[time_col])
        m = meta.get(sid, {})
        rows.append({"source_id": sid, "source": m.get("short", sid), "value_type": m.get("value_type"),
                     "resolution": m.get("resolution"), "license": m.get("license"),
                     "cities": int(df["city_id"].nunique()), "start": t.min().date(), "end": t.max().date(),
                     "rows": int(len(df))})
    return pd.DataFrame(rows)
