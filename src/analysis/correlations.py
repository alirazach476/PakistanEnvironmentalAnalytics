"""Correlation analysis with explicit sample sizes and autocorrelation adjustment.

Daily environmental series are strongly autocorrelated, so naive p-values
(which assume n independent pairs) are far too small. Each correlation therefore
also reports an *effective sample size* (Bretherton et al., 1999):

    n_eff = n · (1 − r1x·r1y) / (1 + r1x·r1y)

where r1x, r1y are lag-1 autocorrelations, and a p-value recomputed with n_eff.
Correlations of *deseasonalised anomalies* are offered because pollution and
weather share a strong annual cycle, which by itself produces large raw
correlations.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats
from statsmodels.stats.multitest import multipletests

from src.data.validate import require_columns
from src.utils.config import ALPHA


def _fisher_ci(r: float, n: float, se_scale: float = 1.0, ci: float = 0.95) -> tuple[float, float]:
    if not np.isfinite(r) or n <= 3 or abs(r) >= 1:
        return (np.nan, np.nan)
    z = np.arctanh(r)
    se = se_scale / np.sqrt(n - 3)
    q = stats.norm.ppf(0.5 + ci / 2)
    return float(np.tanh(z - q * se)), float(np.tanh(z + q * se))


def _p_from_r(r: float, n: float) -> float:
    if not np.isfinite(r) or n <= 2 or abs(r) >= 1:
        return np.nan
    t = r * np.sqrt((n - 2) / (1 - r * r))
    return float(2 * stats.t.sf(abs(t), df=n - 2))


def effective_n(x: pd.Series, y: pd.Series) -> tuple[float, float, float]:
    """Return (n_eff, r1x, r1y). Lag-1 autocorrelation is computed on the given order."""
    n = len(x)
    r1x = pd.Series(np.asarray(x, dtype=float)).autocorr(1)
    r1y = pd.Series(np.asarray(y, dtype=float)).autocorr(1)
    if not (np.isfinite(r1x) and np.isfinite(r1y)):
        return float(n), r1x, r1y
    prod = r1x * r1y
    n_eff = n * (1 - prod) / (1 + prod)
    return float(min(max(n_eff, 3.0), n)), float(r1x), float(r1y)


def correlation(x, y, method: str = "pearson", adjust_autocorrelation: bool = True) -> dict:
    """Pearson or Spearman correlation with n, 95 % CI and autocorrelation-adjusted p."""
    if method not in ("pearson", "spearman"):
        raise ValueError("method must be 'pearson' or 'spearman'")
    df = pd.DataFrame({"x": np.asarray(x, dtype=float), "y": np.asarray(y, dtype=float)}).dropna()
    n = len(df)
    out = {"method": method, "n": n, "r": np.nan, "p_value": np.nan, "ci_low": np.nan, "ci_high": np.nan,
           "n_eff": np.nan, "p_value_adjusted_n": np.nan, "lag1_x": np.nan, "lag1_y": np.nan}
    if n < 4 or df["x"].nunique() < 2 or df["y"].nunique() < 2:
        out["note"] = "insufficient data or zero variance"
        return out
    if method == "pearson":
        r, p = stats.pearsonr(df["x"], df["y"])
        se_scale = 1.0
    else:
        r, p = stats.spearmanr(df["x"], df["y"])
        se_scale = np.sqrt(1.06)  # Fieller et al. (1957) variance inflation for Spearman
    out.update({"r": float(r), "p_value": float(p)})
    out["ci_low"], out["ci_high"] = _fisher_ci(float(r), n, se_scale)
    if adjust_autocorrelation:
        n_eff, r1x, r1y = effective_n(df["x"], df["y"])
        out.update({"n_eff": n_eff, "lag1_x": r1x, "lag1_y": r1y,
                    "p_value_adjusted_n": _p_from_r(float(r), n_eff)})
        out["ci_low_adj"], out["ci_high_adj"] = _fisher_ci(float(r), n_eff, se_scale)
    return out


def correlation_matrix(df: pd.DataFrame, columns: list[str], method: str = "spearman") -> tuple[pd.DataFrame, pd.DataFrame]:
    """Pairwise-complete correlation matrix and matching pairwise n matrix."""
    cols = [c for c in columns if c in df.columns]
    if len(cols) < 2:
        raise KeyError("Need at least two available columns for a correlation matrix")
    corr = df[cols].corr(method=method)
    notna = df[cols].notna().astype(int)
    n = notna.T @ notna
    return corr, n


def add_anomalies(df: pd.DataFrame, columns: list[str], group_col: str = "city_id") -> pd.DataFrame:
    """Subtract each city's calendar-month mean from each variable (``<col>_anom``)."""
    require_columns(df, [group_col, "month", *columns])
    out = df.copy()
    for c in columns:
        out[f"{c}_anom"] = out[c] - out.groupby([group_col, "month"], observed=True)[c].transform("mean")
    return out


def pooled_city_correlation(df: pd.DataFrame, x: str, y: str = "pm25", method: str = "spearman",
                            group_col: str = "city_id", deseasonalize: bool = False) -> dict:
    """Correlation within each city, summarised across cities (the city is the unit).

    Returns the median of per-city coefficients, the range, the number of cities and how many
    are significant after BH-FDR using autocorrelation-adjusted p-values.
    """
    per_city = city_correlations(df, x, y, method, group_col, deseasonalize)
    if per_city.empty:
        return {"x": x, "y": y, "n_cities": 0}
    return {"x": x, "y": y, "method": method, "deseasonalized": deseasonalize,
            "n_cities": int(len(per_city)), "median_r": float(per_city["r"].median()),
            "min_r": float(per_city["r"].min()), "max_r": float(per_city["r"].max()),
            "n_obs_total": int(per_city["n"].sum()),
            "n_significant_fdr": int((per_city["q_value"] < ALPHA).sum()),
            "n_positive": int((per_city["r"] > 0).sum()), "n_negative": int((per_city["r"] < 0).sum())}


def city_correlations(df: pd.DataFrame, x: str, y: str = "pm25", method: str = "spearman",
                      group_col: str = "city_id", deseasonalize: bool = False) -> pd.DataFrame:
    require_columns(df, [x, y, group_col, "date"])
    work = add_anomalies(df, [x, y], group_col) if deseasonalize else df
    xc, yc = (f"{x}_anom", f"{y}_anom") if deseasonalize else (x, y)
    rows = []
    for key, g in work.sort_values("date").groupby(group_col, observed=True):
        r = correlation(g[xc], g[yc], method)
        r[group_col] = key
        rows.append(r)
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    p = out["p_value_adjusted_n"]
    out["q_value"] = np.nan
    ok = p.notna()
    if ok.any():
        out.loc[ok, "q_value"] = multipletests(p[ok], method="fdr_bh")[1]
    return out


def lagged_correlation(df: pd.DataFrame, x: str, y: str = "pm25", lags=range(-3, 4), method: str = "spearman",
                       group_col: str = "city_id", freq: str = "D", time_col: str = "date",
                       deseasonalize: bool = False) -> pd.DataFrame:
    """Correlation of y(t) with x(t − lag), computed per city and summarised.

    Positive lag = x leads y. Shifting is done on the calendar index (not row order),
    so gaps never pair non-adjacent periods.
    """
    require_columns(df, [x, y, group_col, time_col])
    work = add_anomalies(df, [x, y], group_col) if deseasonalize and "month" in df.columns else df
    xc, yc = (f"{x}_anom", f"{y}_anom") if deseasonalize and "month" in df.columns else (x, y)
    rows = []
    for lag in lags:
        rs, ns = [], []
        for _, g in work.groupby(group_col, observed=True):
            s = g.set_index(time_col)[[xc, yc]].sort_index()
            s = s[~s.index.duplicated()].asfreq(freq)
            shifted = s[xc].shift(lag)
            pair = pd.DataFrame({"x": shifted, "y": s[yc]}).dropna()
            if len(pair) >= 10 and pair["x"].nunique() > 1 and pair["y"].nunique() > 1:
                rs.append(pair["x"].corr(pair["y"], method=method))
                ns.append(len(pair))
        rows.append({"lag": lag, "median_r": float(np.median(rs)) if rs else np.nan,
                     "q25_r": float(np.quantile(rs, 0.25)) if rs else np.nan,
                     "q75_r": float(np.quantile(rs, 0.75)) if rs else np.nan,
                     "n_cities": len(rs), "n_pairs": int(sum(ns))})
    return pd.DataFrame(rows)
