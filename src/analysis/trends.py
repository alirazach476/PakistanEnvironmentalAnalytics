"""Temporal aggregation and autocorrelation-aware trend estimation.

Trends are estimated on *deseasonalised monthly anomalies* (monthly mean minus the
city's long-term mean for that calendar month), which removes the dominant seasonal
cycle. Two estimators are reported:

* OLS slope with Newey–West (HAC) standard errors — robust to serial correlation;
* Theil–Sen slope — robust to outliers (its CI assumes independence, so the HAC
  p-value is the one used for inference).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy import stats
from statsmodels.stats.multitest import multipletests

from src.data.transform import aggregate_period
from src.data.validate import require_columns
from src.utils.config import ALPHA

HAC_LAGS = 12  # months


def monthly_series(df: pd.DataFrame, value: str = "pm25", group_cols=("city_id",), complete_only: bool = True) -> pd.DataFrame:
    m = aggregate_period(df, value, "MS", group_cols)
    return m[m["complete"]] if complete_only else m


def annual_series(df: pd.DataFrame, value: str = "pm25", group_cols=("city_id",), complete_only: bool = True) -> pd.DataFrame:
    a = aggregate_period(df, value, "YS", group_cols)
    a["year"] = a["period"].dt.year
    return a[a["complete"]] if complete_only else a


def rolling_mean(daily: pd.DataFrame, value: str = "pm25", window: int = 30, group_col: str = "city_id",
                 min_frac: float = 0.7) -> pd.DataFrame:
    """Calendar-aware centred rolling mean (gaps are not bridged as if consecutive)."""
    require_columns(daily, [value, "date", group_col])
    if window < 1:
        raise ValueError("window must be >= 1")
    out = []
    for key, g in daily.groupby(group_col, observed=True):
        s = g.set_index("date")[value].sort_index().asfreq("D")
        r = s.rolling(window, center=True, min_periods=max(1, int(window * min_frac))).mean()
        out.append(pd.DataFrame({group_col: key, "date": r.index, f"{value}_rolling": r.to_numpy()}))
    if not out:
        return pd.DataFrame(columns=[group_col, "date", f"{value}_rolling"])
    return pd.concat(out, ignore_index=True)


def deseasonalize(monthly: pd.DataFrame, group_col: str = "city_id") -> pd.DataFrame:
    """Add ``climatology`` (city × calendar-month mean) and ``anomaly`` columns."""
    require_columns(monthly, ["period", "mean", group_col])
    m = monthly.copy()
    m["cal_month"] = m["period"].dt.month
    m["climatology"] = m.groupby([group_col, "cal_month"], observed=True)["mean"].transform("mean")
    m["anomaly"] = m["mean"] - m["climatology"]
    return m


def linear_trend(periods: pd.Series, values: pd.Series, hac_lags: int = HAC_LAGS) -> dict:
    """Slope per year with HAC (Newey–West) 95 % CI, plus Theil–Sen slope."""
    t = (pd.to_datetime(periods) - pd.Timestamp("2000-01-01")).dt.days.to_numpy() / 365.25
    y = np.asarray(values, dtype=float)
    ok = np.isfinite(t) & np.isfinite(y)
    t, y = t[ok], y[ok]
    n = int(t.size)
    res = {"n": n, "slope_per_year": np.nan, "ci_low": np.nan, "ci_high": np.nan, "p_value": np.nan,
           "theil_sen_slope": np.nan, "theil_sen_low": np.nan, "theil_sen_high": np.nan,
           "lag1_autocorr": np.nan}
    if n < 24:
        res["note"] = "fewer than 24 monthly points; trend not estimated"
        return res
    X = sm.add_constant(t)
    fit = sm.OLS(y, X).fit(cov_type="HAC", cov_kwds={"maxlags": min(hac_lags, n // 4)})
    lo, hi = fit.conf_int(alpha=0.05)[1]
    ts = stats.theilslopes(y, t, alpha=0.95)
    resid = fit.resid
    res.update({"slope_per_year": float(fit.params[1]), "ci_low": float(lo), "ci_high": float(hi),
                "p_value": float(fit.pvalues[1]), "theil_sen_slope": float(ts.slope),
                "theil_sen_low": float(ts.low_slope), "theil_sen_high": float(ts.high_slope),
                "lag1_autocorr": float(pd.Series(resid).autocorr(1))})
    return res


def city_trends(daily: pd.DataFrame, value: str = "pm25", group_col: str = "city_id",
                label_col: str = "city_label", alpha: float = ALPHA) -> pd.DataFrame:
    """Per-city deseasonalised trend with Benjamini–Hochberg FDR control across cities."""
    require_columns(daily, [value, "date", group_col, label_col])
    labels = daily.groupby(group_col, observed=True)[label_col].first()
    m = deseasonalize(monthly_series(daily, value, (group_col,)), group_col)
    rows = []
    for key, g in m.groupby(group_col, observed=True):
        r = linear_trend(g["period"], g["anomaly"])
        r.update({group_col: key, label_col: labels.get(key), "mean_level": float(g["mean"].mean())})
        rows.append(r)
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    valid = out["p_value"].notna()
    out["q_value"] = np.nan
    if valid.any():
        out.loc[valid, "q_value"] = multipletests(out.loc[valid, "p_value"], alpha=alpha, method="fdr_bh")[1]
    out["pct_change_per_year"] = 100 * out["slope_per_year"] / out["mean_level"]
    out["direction"] = np.select(
        [(out["q_value"] < alpha) & (out["slope_per_year"] < 0), (out["q_value"] < alpha) & (out["slope_per_year"] > 0)],
        ["decreasing", "increasing"], default="no clear trend")
    return out.sort_values("slope_per_year").reset_index(drop=True)


def trend_fit_line(periods: pd.Series, values: pd.Series, hac_lags: int = HAC_LAGS) -> pd.DataFrame:
    """Fitted OLS line with HAC 95 % confidence band for plotting."""
    p = pd.to_datetime(pd.Series(periods)).reset_index(drop=True)
    y = pd.Series(values, dtype=float).reset_index(drop=True)
    ok = y.notna()
    p, y = p[ok], y[ok]
    if len(y) < 24:
        return pd.DataFrame(columns=["period", "fit", "lower", "upper"])
    t = (p - pd.Timestamp("2000-01-01")).dt.days.to_numpy() / 365.25
    X = sm.add_constant(t)
    fit = sm.OLS(y.to_numpy(), X).fit(cov_type="HAC", cov_kwds={"maxlags": min(hac_lags, len(y) // 4)})
    pred = fit.get_prediction(X).summary_frame(alpha=0.05)
    return pd.DataFrame({"period": p.to_numpy(), "fit": pred["mean"].to_numpy(),
                         "lower": pred["mean_ci_lower"].to_numpy(), "upper": pred["mean_ci_upper"].to_numpy()})


def year_over_year(daily: pd.DataFrame, value: str = "pm25", group_col: str = "city_id") -> pd.DataFrame:
    """Annual means (complete years only) and change versus the previous complete year."""
    a = annual_series(daily, value, (group_col,))
    a = a.sort_values([group_col, "year"])
    prev = a.groupby(group_col, observed=True)["mean"].shift(1)
    prev_year = a.groupby(group_col, observed=True)["year"].shift(1)
    a["change"] = np.where(prev_year == a["year"] - 1, a["mean"] - prev, np.nan)
    a["pct_change"] = np.where(prev_year == a["year"] - 1, 100 * (a["mean"] - prev) / prev, np.nan)
    return a.reset_index(drop=True)


def complete_years(daily: pd.DataFrame, value: str = "pm25") -> list[int]:
    """Calendar years for which every city present has a complete annual mean."""
    a = annual_series(daily, value, ("city_id",), complete_only=False)
    ok = a.groupby("year")["complete"].all()
    return sorted(int(y) for y in ok[ok].index)
