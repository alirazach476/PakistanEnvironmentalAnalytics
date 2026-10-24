"""Export the prepared datasets and precomputed analysis to web/data/ for the static dashboard.

Everything the website shows is either computed here by the same tested Python
functions used by the Streamlit app and reports, or computed in the browser from
the exported daily values. Nothing is hand-written.

Outputs (web/data/):
  meta.json        sources, coverage, rules, manifest, artifact/identity tables, DQ tables, sensitivity
  cities.json      one record per World Bank place (+ flags)
  pm25.bin         Uint16 little-endian, PM2.5 × 10, city-major [n_cities × n_dates]
  outliers.json    flagged (city index, date index) pairs
  weather.bin      Int16 little-endian, value × 10, [n_weather_cities × n_vars × n_dates]
  analysis.json    trends (with HAC fit parameters), tests, correlations, lags, matrices
  hourly.json      Kaggle/HF hourly summaries, diurnal profiles, timestamp diagnostic, source comparison

Usage:
    python scripts/export_web_data.py
"""

from __future__ import annotations

import datetime
import json
import math
import shutil
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.analysis import correlations, data_quality as dq, descriptive, sensitivity  # noqa: E402
from src.analysis import statistical_tests as st, trends  # noqa: E402
from src.data import load  # noqa: E402
from src.data.transform import independent_units  # noqa: E402
from src.utils.config import (LABELS, MIN_DAYS_PER_MONTH, MIN_MONTHS_PER_YEAR, OUTLIER_ROBUST_Z, SEASON_BY_MONTH,  # noqa: E402
                              SEASON_ORDER, SOURCES, UNITS, WHO_PM25_24H, WHO_PM25_ANNUAL)

OUT = ROOT / "web" / "data"
WX_VARS = ["temperature", "humidity", "wind_speed", "precipitation", "pressure", "dew_point"]
HF_POLS = ["pm25", "pm10", "carbon_monoxide", "nitrogen_dioxide", "sulphur_dioxide", "ozone", "dust"]


def clean(o):
    """JSON-safe conversion (NaN -> None, numpy/pandas scalars -> Python, timestamps -> ISO date)."""
    if isinstance(o, dict):
        return {str(k): clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    if isinstance(o, pd.DataFrame):
        return clean(o.to_dict(orient="records"))
    if isinstance(o, (pd.Timestamp, np.datetime64)):
        return None if pd.isna(o) else str(pd.Timestamp(o).date())
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating, float)):
        return None if not math.isfinite(float(o)) else round(float(o), 4)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if o is pd.NaT:
        return None
    if isinstance(o, (datetime.date, datetime.datetime)):
        return o.isoformat()[:10]
    return o


def dump(name: str, obj) -> None:
    p = OUT / name
    p.write_text(json.dumps(clean(obj), separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
    print(f"  {name:16s} {p.stat().st_size / 1024:8.1f} KB")


def hac_params(periods: pd.Series, values: pd.Series) -> dict | None:
    """OLS on anomalies vs years-since-2000 with Newey–West covariance (same spec as trends.linear_trend)."""
    t = (pd.to_datetime(periods) - pd.Timestamp("2000-01-01")).dt.days.to_numpy() / 365.25
    y = np.asarray(values, dtype=float)
    if len(y) < 24:
        return None
    fit = sm.OLS(y, sm.add_constant(t)).fit(cov_type="HAC", cov_kwds={"maxlags": min(trends.HAC_LAGS, len(y) // 4)})
    c = fit.cov_params()
    return {"a": fit.params[0], "b": fit.params[1], "vaa": c[0, 0], "vbb": c[1, 1], "vab": c[0, 1]}


def test_payload(results: list) -> list[dict]:
    out = []
    for r in results:
        d = r.to_dict()
        d["details"] = r.details.head(400) if r.details is not None else None
        out.append(d)
    return out


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    print("Loading prepared data …")
    wb = descriptive.real_only(load.load_processed("wb_daily"))
    cities = load.load_processed("wb_cities")
    ww = load.load_processed("wb_weather_daily")
    weather = load.load_processed("weather_daily")
    hf = load.load_processed("hf_hourly")
    overlap = load.load_processed("source_overlap")
    manifest = load.load_manifest()
    print("Writing web/data:")

    # ---- cities + daily matrix ----------------------------------------------------
    cities = cities.sort_values(["population"], ascending=False).reset_index(drop=True)
    cities["idx"] = np.arange(len(cities))
    dates = np.sort(wb["date"].unique())
    wide = wb.pivot_table(index="city_id", columns="date", values="pm25", observed=True).reindex(
        index=cities["city_id"].astype(str), columns=dates)
    if wide.isna().any().any():
        raise ValueError("daily matrix has gaps; the web export assumes a shared date index")
    (np.round(wide.to_numpy() * 10).astype("<u2")).tofile(OUT / "pm25.bin")
    print(f"  {'pm25.bin':16s} {(OUT / 'pm25.bin').stat().st_size / 1024:8.1f} KB")
    pos = {c: i for i, c in enumerate(cities["city_id"].astype(str))}
    didx = {pd.Timestamp(d): i for i, d in enumerate(dates)}
    o = wb[wb["is_outlier"]]
    dump("outliers.json", [[pos[str(c)], didx[pd.Timestamp(d)]] for c, d in zip(o["city_id"], o["date"])])

    keep = ["idx", "city_id", "city_label", "province", "latitude", "longitude", "population", "name_ambiguous",
            "series_group", "series_group_size", "is_series_representative", "artifact_flag", "artifact_reason",
            "fixed_annual_run", "fixed_annual_from", "fixed_annual_to", "break_date", "break_shift", "break_shift_rel",
            "break_t"]
    cdf = cities[keep].copy()
    for c in ("city_id", "city_label", "province"):
        cdf[c] = cdf[c].astype(str)
    dump("cities.json", cdf)

    # ---- weather matrix ---------------------------------------------------------------
    wx_ids = [c for c in cities["city_id"].astype(str) if c in set(ww["city_id"].astype(str))]
    arr = np.zeros((len(wx_ids), len(WX_VARS), len(dates)), dtype="<i2")
    for i, cid in enumerate(wx_ids):
        g = ww[ww["city_id"].astype(str) == cid].set_index("date").reindex(dates)
        for j, v in enumerate(WX_VARS):
            arr[i, j] = np.round(g[v].to_numpy() * 10).astype("<i2")
    arr.tofile(OUT / "weather.bin")
    print(f"  {'weather.bin':16s} {(OUT / 'weather.bin').stat().st_size / 1024:8.1f} KB")

    # ---- analysis ---------------------------------------------------------------------
    print("Computing trends, tests, correlations …")
    tr = trends.city_trends(wb)
    m = trends.deseasonalize(trends.monthly_series(wb))
    params = {cid: hac_params(g["period"], g["anomaly"]) for cid, g in m.groupby("city_id", observed=True)}
    tr["fit"] = tr["city_id"].astype(str).map(lambda c: params.get(c))
    tr["city_id"] = tr["city_id"].astype(str)
    tr["city_label"] = tr["city_label"].astype(str)

    flagged = set(cities.loc[cities["artifact_flag"], "city_id"].astype(str))

    def battery(daily: pd.DataFrame, wxd: pd.DataFrame) -> list:
        iu = independent_units(daily, cities)
        yrs = trends.complete_years(iu)
        med = iu.groupby(["city_id", "province"], observed=True)["pm25"].median().reset_index()
        mean = iu.groupby(["city_id", "province"], observed=True)["pm25"].mean().reset_index()
        res = [st.seasonal_friedman(iu), st.group_kruskal(med, "pm25"), st.group_anova_if_justified(mean, "pm25"),
               st.weekday_weekend_test(iu), st.period_change_test(trends.annual_series(iu), yrs[0], yrs[-1])]
        res += [st.weather_correlation_test(wxd, x, deseasonalize=True) for x in ("temperature", "humidity",
                                                                                  "wind_speed", "precipitation")]
        return res

    tests_all = battery(wb, ww)
    wb_clean = wb[~wb["city_id"].astype(str).isin(flagged)]
    ww_clean = ww[~ww["city_id"].astype(str).isin(flagged)]
    tests_clean = battery(wb_clean, ww_clean)

    per_city, pooled, lags, mats = {}, [], {}, {}
    for x in WX_VARS:
        for des in (False, True):
            k = f"{x}|{'anom' if des else 'raw'}"
            pc = correlations.city_correlations(ww, x, "pm25", "spearman", deseasonalize=des)
            pc["city_id"] = pc["city_id"].astype(str)
            per_city[k] = pc[["city_id", "r", "n", "n_eff", "ci_low_adj", "ci_high_adj", "p_value_adjusted_n", "q_value"]]
            pooled.append(correlations.pooled_city_correlation(ww, x, deseasonalize=des))
            lags[k] = correlations.lagged_correlation(ww, x, deseasonalize=des)
    for des in (False, True):
        cols = ["pm25"] + WX_VARS
        d = correlations.add_anomalies(ww, cols) if des else ww
        cc = [f"{c}_anom" for c in cols] if des else cols
        corr, n = correlations.correlation_matrix(d, cc, "spearman")
        mats["anom" if des else "raw"] = {"vars": cols, "r": corr.to_numpy().round(3).tolist(), "n": n.to_numpy().tolist()}

    sens, ranks = sensitivity.scenario_metrics(wb, cities), sensitivity.ranking_under_scenarios(wb, cities, top_n=8)
    dump("analysis.json", {"trends": tr, "tests_all": test_payload(tests_all), "tests_clean": test_payload(tests_clean),
                           "per_city_corr": per_city, "pooled_corr": pooled, "lags": lags, "matrices": mats,
                           "sensitivity": sens, "sensitivity_ranks": ranks})

    # ---- hourly (Kaggle/HF) -------------------------------------------------------------
    hourly = {}
    if not hf.empty:
        pols = [p for p in HF_POLS if p in hf.columns]
        prof = {p: hf.groupby(["city", "hour"])[p].mean().unstack("hour").round(2) for p in pols}
        summ = {p: descriptive.summary_stats(hf, p, "city").assign(city=lambda x: x["city"].astype(str)) for p in pols}
        hist = {}
        for p in pols:
            v = hf[p].dropna().to_numpy()
            cnt, edges = np.histogram(v, bins=60)
            hist[p] = {"counts": cnt.tolist(), "edges": edges.round(3).tolist(), "median": float(np.median(v)), "n": int(v.size)}
        al = dq.diurnal_peak_alignment(hf)
        vars_all = [c for c in pols + ["temperature", "humidity", "precipitation", "wind_speed", "pressure"] if c in hf.columns]
        same = pd.concat([dq.identical_series(hf, v, "timestamp", "city") for v in vars_all], ignore_index=True)
        hourly = {
            "cities": sorted(hf["city"].astype(str).unique()), "pollutants": pols,
            "start": hf["timestamp"].min(), "end": hf["timestamp"].max(), "rows": len(hf),
            "profiles": {p: {"cities": list(prof[p].index.astype(str)), "values": prof[p].to_numpy().tolist()} for p in pols},
            "summary": summ, "hist": hist,
            "alignment": {k: v for k, v in al.items() if k != "profile"},
            "alignment_profile": al["profile"],
            "identical": same,
            "missingness": dq.missingness_matrix(hf, vars_all, "city").round(2).reset_index(),
            "comparison": dq.source_comparison(overlap),
            "overlap": overlap[["city", "date", "pm25_hf", "pm25_wb"]],
        }
    dump("hourly.json", hourly)

    # ---- meta -----------------------------------------------------------------------
    gaps = dq.find_gaps(wb["date"])
    cov = dq.source_coverage({"wb_pm25": (wb, "date"), "hf_aq": (hf, "timestamp"), "openmeteo_era5": (weather, "date")},
                             SOURCES)
    pc_cons = dq.province_consistency(cities)
    meta = {
        "generated": pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%d %H:%M UTC"),
        "prepared": manifest["generated_utc"],
        "dates": [str(pd.Timestamp(d).date()) for d in dates],
        "n_cities": len(cities),
        "weather_city_ids": wx_ids, "weather_vars": WX_VARS,
        "labels": LABELS, "units": UNITS, "season_by_month": SEASON_BY_MONTH, "season_order": SEASON_ORDER,
        "rules": {**manifest["rules"], "who_24h": WHO_PM25_24H, "who_annual": WHO_PM25_ANNUAL,
                  "min_days_per_month": MIN_DAYS_PER_MONTH, "min_months_per_year": MIN_MONTHS_PER_YEAR,
                  "outlier_z": OUTLIER_ROBUST_Z},
        "sources": SOURCES, "coverage": cov, "manifest_inputs": manifest["inputs"],
        "adm1_anchor_check": manifest["adm1_anchor_check"],
        "gaps": gaps, "gap_pattern": dq.missing_dates_pattern(gaps),
        "exclusions": load.load_exclusions().fillna(""),
        "province_review": pc_cons[~pc_cons["consistent"]].astype({"city_id": str, "city_label": str, "province": str}),
        "duplicates": dq.duplicate_summary(wb, ["city_id", "date"]),
    }
    dump("meta.json", meta)

    import markdown
    docs = {}
    for name in ("methodology", "data_sources", "data_dictionary"):
        text = (ROOT / "docs" / f"{name}.md").read_text(encoding="utf-8")
        docs[name] = markdown.markdown(text, extensions=["tables", "fenced_code"])
    dump("docs.json", docs)

    vendor = ROOT / "web" / "vendor"
    vendor.mkdir(exist_ok=True)
    import plotly
    shutil.copy(Path(plotly.__file__).parent / "package_data" / "plotly.min.js", vendor / "plotly.min.js")
    print("  vendor/plotly.min.js copied")


if __name__ == "__main__":
    main()
