"""Sensitivity of headline results to data-handling choices.

Each scenario applies one documented rule change to the World Bank daily table
and recomputes the same metrics, so differences are attributable to that rule.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

from src.analysis.trends import complete_years
from src.data.validate import require_columns


def _scenarios(daily: pd.DataFrame, cities: pd.DataFrame | None = None) -> dict[str, pd.DataFrame]:
    years = complete_years(daily)
    lo, hi = daily["pm25"].quantile([0.01, 0.99])
    sc = {
        "Baseline (all retained data)": daily,
        "Exclude flagged outliers": daily[~daily["is_outlier"]],
        "Winsorise at 1st/99th percentile": daily.assign(pm25=daily["pm25"].clip(lo, hi)),
        "Complete calendar years only": daily[daily["year"].isin(years)] if years else daily.iloc[0:0],
        "Last 3 complete years only": daily[daily["year"].isin(years[-3:])] if years else daily.iloc[0:0],
        "Drop winter months (Dec–Feb)": daily[~daily["month"].isin([12, 1, 2])],
    }
    if cities is not None and "is_series_representative" in cities.columns:
        keep = set(cities.loc[cities["is_series_representative"], "city_id"].astype(str))
        sc["One place per identical model series"] = daily[daily["city_id"].astype(str).isin(keep)]
    if cities is not None and "artifact_flag" in cities.columns:
        bad = set(cities.loc[cities["artifact_flag"], "city_id"].astype(str))
        sc["Exclude model-artifact-flagged places"] = daily[~daily["city_id"].astype(str).isin(bad)]
    return sc


def scenario_metrics(daily: pd.DataFrame, cities: pd.DataFrame | None = None, top_n: int = 10) -> pd.DataFrame:
    """Overall median, median of city medians, top-N overlap and rank correlation vs baseline."""
    require_columns(daily, ["pm25", "city_id", "city_label", "year", "month", "is_outlier"])
    sc = _scenarios(daily, cities)
    base = daily.groupby("city_id", observed=True)["pm25"].median()
    base_top = set(base.nlargest(top_n).index)
    rows = []
    for name, d in sc.items():
        if d.empty:
            rows.append({"scenario": name, "rows": 0})
            continue
        med = d.groupby("city_id", observed=True)["pm25"].median()
        common = base.index.intersection(med.index)
        rho = stats.spearmanr(base[common], med[common]).statistic if len(common) > 2 else np.nan
        top = med.nlargest(top_n)
        rows.append({
            "scenario": name, "rows": int(len(d)), "rows_removed_pct": 100 * (1 - len(d) / len(daily)),
            "cities": int(d["city_id"].nunique()), "overall_median": float(d["pm25"].median()),
            "overall_mean": float(d["pm25"].mean()), "median_of_city_medians": float(med.median()),
            "top_city": d.loc[d["city_id"] == top.index[0], "city_label"].iloc[0],
            f"top{top_n}_overlap_with_baseline": len(set(top.index) & base_top),
            "rank_spearman_vs_baseline": float(rho),
        })
    return pd.DataFrame(rows)


def ranking_under_scenarios(daily: pd.DataFrame, cities: pd.DataFrame | None = None, top_n: int = 10) -> pd.DataFrame:
    """Long table of city ranks (by median) under each scenario, for the baseline top-N cities."""
    sc = _scenarios(daily, cities)
    base = daily.groupby("city_label", observed=True)["pm25"].median()
    keep = base.nlargest(top_n).index
    rows = []
    for name, d in sc.items():
        if d.empty:
            continue
        r = d.groupby("city_label", observed=True)["pm25"].median().rank(ascending=False, method="min")
        for c in keep:
            rows.append({"scenario": name, "city_label": c, "rank": float(r.get(c, np.nan))})
    return pd.DataFrame(rows)
