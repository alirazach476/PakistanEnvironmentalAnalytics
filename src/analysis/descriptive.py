"""Descriptive statistics computed dynamically from whichever frame is passed in."""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.data.validate import require_columns
from src.utils.config import WHO_PM25_24H

PERCENTILES = (5, 25, 50, 75, 95)


def real_only(df: pd.DataFrame) -> pd.DataFrame:
    """Drop synthetic rows. Every analysis entry point in the app calls this first."""
    if "value_type" not in df.columns:
        return df
    return df[df["value_type"].astype(str) != "synthetic"]


def dataset_overview(df: pd.DataFrame, value: str = "pm25", date_col: str = "date",
                     city_col: str = "city_id") -> dict:
    """Dimensions, coverage and headline distribution figures for a long table."""
    require_columns(df, [value, date_col, city_col])
    if df.empty:
        return {"rows": 0, "cities": 0, "date_min": None, "date_max": None, "n_dates": 0,
                "n_values": 0, "median": np.nan, "mean": np.nan, "missing_pct": np.nan}
    d = pd.to_datetime(df[date_col])
    vals = df[value]
    return {
        "rows": int(len(df)),
        "cities": int(df[city_col].nunique()),
        "date_min": d.min(),
        "date_max": d.max(),
        "n_dates": int(d.dt.normalize().nunique()),
        "n_values": int(vals.notna().sum()),
        "median": float(vals.median()),
        "mean": float(vals.mean()),
        "missing_pct": float(vals.isna().mean() * 100),
    }


def summary_stats(df: pd.DataFrame, value: str = "pm25", by: str | list[str] | None = None,
                  percentiles: tuple[int, ...] = PERCENTILES) -> pd.DataFrame:
    """n, missing %, mean, std, min, percentiles, max — overall or per group."""
    require_columns(df, [value] + ([by] if isinstance(by, str) else list(by or [])))

    def _stats(s: pd.Series) -> pd.Series:
        v = s.dropna()
        out = {"n": int(v.size), "missing_pct": float(s.isna().mean() * 100) if len(s) else np.nan,
               "mean": v.mean(), "std": v.std(ddof=1), "min": v.min()}
        for p in percentiles:
            out[f"p{p}"] = v.quantile(p / 100) if v.size else np.nan
        out["max"] = v.max()
        out["median"] = out.get("p50", v.median())
        return pd.Series(out)

    if by is None:
        return _stats(df[value]).to_frame().T
    return df.groupby(by, observed=True)[value].apply(_stats).unstack().reset_index()


def city_summary(daily: pd.DataFrame, value: str = "pm25", label_col: str = "city_label",
                 threshold: float = WHO_PM25_24H) -> pd.DataFrame:
    """Per-city distribution summary plus share of days above a reference threshold.

    Rank 1 = highest median. Ranks are only comparable when cities share the same period;
    use :func:`comparable_period_ranking` for a guaranteed common window.
    """
    group = ["city_id", label_col] + [c for c in ("province", "latitude", "longitude", "population")
                                      if c in daily.columns]
    require_columns(daily, [value, *group, "date"])
    g = daily.groupby(group, observed=True)
    out = g[value].agg(n="count", mean="mean", median="median", std="std", min="min",
                       p95=lambda s: s.quantile(0.95), max="max").reset_index()
    out["pct_days_above_threshold"] = g[value].apply(lambda s: (s > threshold).mean() * 100).to_numpy()
    span = g["date"].agg(["min", "max"]).reset_index(drop=True)
    out["first_date"], out["last_date"] = span["min"].to_numpy(), span["max"].to_numpy()
    out["rank_by_median"] = out["median"].rank(ascending=False, method="min").astype(int)
    return out.sort_values("rank_by_median").reset_index(drop=True)


def comparable_period_ranking(daily: pd.DataFrame, start=None, end=None, value: str = "pm25",
                              label_col: str = "city_label", min_coverage: float = 0.8) -> pd.DataFrame:
    """Rank cities on the median over a common window, keeping cities with >= ``min_coverage``
    of that window's observed dates (dates present for any city)."""
    require_columns(daily, [value, "date", "city_id", label_col])
    d = daily
    if start is not None:
        d = d[d["date"] >= pd.Timestamp(start)]
    if end is not None:
        d = d[d["date"] <= pd.Timestamp(end)]
    if d.empty:
        return pd.DataFrame(columns=["city_id", label_col, "median", "n", "coverage", "rank"])
    n_dates = d["date"].nunique()
    r = d.groupby(["city_id", label_col], observed=True)[value].agg(median="median", n="count").reset_index()
    r["coverage"] = r["n"] / n_dates
    r = r[r["coverage"] >= min_coverage].copy()
    r["rank"] = r["median"].rank(ascending=False, method="min").astype(int)
    return r.sort_values("rank").reset_index(drop=True)


def observations_per_city(df: pd.DataFrame, city_col: str = "city_label", value: str = "pm25") -> pd.DataFrame:
    require_columns(df, [city_col, value])
    return (df.groupby(city_col, observed=True)[value].count().rename("n_observations")
              .reset_index().sort_values("n_observations", ascending=False))


def observations_per_month(df: pd.DataFrame, date_col: str = "date", value: str = "pm25",
                           by: str | None = None) -> pd.DataFrame:
    require_columns(df, [date_col, value] + ([by] if by else []))
    work = df.assign(period=pd.to_datetime(df[date_col]).dt.to_period("M").dt.to_timestamp())
    keys = ["period"] + ([by] if by else [])
    return work.groupby(keys, observed=True)[value].count().rename("n_observations").reset_index()


def percentile_table(df: pd.DataFrame, value: str = "pm25", by: str = "city_label",
                     percentiles: tuple[int, ...] = (10, 25, 50, 75, 90, 99)) -> pd.DataFrame:
    require_columns(df, [value, by])
    q = df.groupby(by, observed=True)[value].quantile([p / 100 for p in percentiles]).unstack()
    q.columns = [f"p{p}" for p in percentiles]
    return q.reset_index()


def bootstrap_median_ci(values, n_boot: int = 2000, ci: float = 0.95, seed: int = 0) -> tuple[float, float, float]:
    """Percentile bootstrap CI for the median of independent units (e.g. city medians)."""
    v = np.asarray(pd.Series(values).dropna(), dtype=float)
    if v.size < 2:
        return (float(np.median(v)) if v.size else np.nan, np.nan, np.nan)
    rng = np.random.default_rng(seed)
    meds = np.median(rng.choice(v, size=(n_boot, v.size), replace=True), axis=1)
    a = (1 - ci) / 2
    return float(np.median(v)), float(np.quantile(meds, a)), float(np.quantile(meds, 1 - a))
