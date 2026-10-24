"""Regenerate every report in reports/ from the prepared datasets.

All figures in the outputs — including the narrative in reports/findings.md —
are computed here at run time; nothing is hard-coded.

Usage:
    python scripts/generate_reports.py
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from statsmodels.stats.multitest import multipletests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.analysis import correlations, data_quality as dq, descriptive, seasonality, sensitivity  # noqa: E402
from src.analysis import statistical_tests as st, trends  # noqa: E402
from src.data import load  # noqa: E402
from src.data.transform import independent_units  # noqa: E402
from src.utils.config import SOURCES, WHO_PM25_24H  # noqa: E402
from src.utils.paths import REPORTS_DIR  # noqa: E402


def save(df: pd.DataFrame, name: str) -> Path:
    p = REPORTS_DIR / f"{name}.csv"
    df.to_csv(p, index=False, float_format="%.4f")
    return p


def md_table(df: pd.DataFrame, floatfmt: str = ".1f") -> str:
    d = df.copy()
    for c in d.columns:
        if pd.api.types.is_float_dtype(d[c]):
            d[c] = d[c].map(lambda v: "" if pd.isna(v) else format(v, floatfmt))
    d = d.astype(str)
    head = "| " + " | ".join(d.columns) + " |\n|" + "---|" * len(d.columns) + "\n"
    return head + "\n".join("| " + " | ".join(r) + " |" for r in d.to_numpy())


def main() -> None:
    REPORTS_DIR.mkdir(exist_ok=True)
    wb = descriptive.real_only(load.load_processed("wb_daily"))
    cities = load.load_processed("wb_cities")
    hf = load.load_processed("hf_hourly")
    weather = load.load_processed("weather_daily")
    ww = load.load_processed("wb_weather_daily")
    overlap = load.load_processed("source_overlap")
    manifest = load.load_manifest()
    excl = load.load_exclusions()
    out: list[Path] = []
    print("Computing reports …")

    # --- City, monthly, seasonal ----------------------------------------------------
    cs = descriptive.city_summary(wb).merge(
        cities[["city_id", "artifact_flag", "artifact_reason", "series_group_size", "name_ambiguous"]], on="city_id")
    out.append(save(cs, "city_summary"))
    monthly = trends.monthly_series(wb, group_cols=("city_id", "city_label"), complete_only=False)
    out.append(save(monthly, "monthly_city_summary"))
    nat = monthly[monthly["complete"]].groupby("period")["mean"].describe(percentiles=[0.25, 0.5, 0.75]).reset_index()
    out.append(save(nat, "monthly_national_summary"))
    season_all = seasonality.seasonal_summary(wb)
    season_prov = seasonality.seasonal_summary(wb, by="province")
    out.append(save(pd.concat([season_all.assign(province="All"), season_prov]), "seasonal_comparison"))

    # --- Trends ---------------------------------------------------------------------
    tr = trends.city_trends(wb).merge(cities[["city_id", "artifact_flag", "artifact_reason"]], on="city_id")
    out.append(save(tr, "city_trends"))

    # --- Statistical tests ------------------------------------------------------------
    iu = independent_units(wb, cities)
    years = trends.complete_years(iu)
    city_med = iu.groupby(["city_id", "province"], observed=True)["pm25"].median().reset_index()
    city_mean = iu.groupby(["city_id", "province"], observed=True)["pm25"].mean().reset_index()
    tests = [st.seasonal_friedman(iu), st.group_kruskal(city_med, "pm25"),
             st.group_anova_if_justified(city_mean, "pm25"), st.weekday_weekend_test(iu),
             st.period_change_test(trends.annual_series(iu), years[0], years[-1])]
    clean_iu = iu[~iu["city_id"].astype(str).isin(set(cities.loc[cities["artifact_flag"], "city_id"].astype(str)))]
    t_clean = st.period_change_test(trends.annual_series(clean_iu), years[0], years[-1])
    t_clean.name += " — artifact-flagged places excluded"
    tests.append(t_clean)
    for x in ("temperature", "humidity", "wind_speed", "precipitation"):
        for des in (False, True):
            tests.append(st.weather_correlation_test(ww, x, deseasonalize=des))
    tt = st.results_table(tests)
    ok = tt["justified"] & tt["p_value"].notna()
    tt["p_holm_family"] = np.nan
    tt.loc[ok, "p_holm_family"] = multipletests(tt.loc[ok, "p_value"], method="holm")[1]
    out.append(save(tt, "statistical_tests"))

    # --- Correlations ---------------------------------------------------------------
    corr_rows = []
    for x in ("temperature", "humidity", "wind_speed", "precipitation", "pressure", "dew_point"):
        for des in (False, True):
            s = correlations.pooled_city_correlation(ww, x, deseasonalize=des)
            corr_rows.append(s)
    corr = pd.DataFrame(corr_rows)
    out.append(save(corr, "correlation_summary"))
    lag = pd.concat([correlations.lagged_correlation(ww, x, deseasonalize=True).assign(variable=x)
                     for x in ("temperature", "humidity", "wind_speed", "precipitation")])
    out.append(save(lag, "lagged_correlations"))

    # --- Data quality ---------------------------------------------------------------
    gaps = dq.find_gaps(wb["date"])
    pat = dq.missing_dates_pattern(gaps)
    comp = dq.completeness_by_city(wb).merge(cities[["city_id", "city_label"]], on="city_id")
    out.append(save(comp, "completeness_by_city"))
    out.append(save(gaps, "missing_dates"))
    out.append(save(excl, "pipeline_exclusions"))
    art = cities[cities["artifact_flag"]][["city_id", "city_label", "province", "artifact_reason", "fixed_annual_run",
                                           "fixed_annual_from", "fixed_annual_to", "break_date", "break_shift",
                                           "break_shift_rel", "break_t"]]
    out.append(save(art, "model_artifact_flags"))
    al = dq.diurnal_peak_alignment(hf) if not hf.empty else None
    hf_vars = [c for c in ("pm25", "pm10", "carbon_monoxide", "nitrogen_dioxide", "sulphur_dioxide", "ozone", "dust",
                           "temperature", "humidity", "precipitation", "wind_speed", "pressure") if c in hf.columns]
    hf_same = (pd.concat([dq.identical_series(hf, v, "timestamp", "city") for v in hf_vars])
               if not hf.empty else pd.DataFrame())
    cov = dq.source_coverage({"wb_pm25": (wb, "date"), "hf_aq": (hf, "timestamp"), "openmeteo_era5": (weather, "date")},
                             SOURCES)
    out.append(save(cov, "source_coverage"))
    scmp = dq.source_comparison(overlap)
    out.append(save(scmp, "source_comparison"))
    sens, ranks = sensitivity.scenario_metrics(wb, cities), sensitivity.ranking_under_scenarios(wb, cities)
    out.append(save(sens, "sensitivity_scenarios"))
    out.append(save(ranks, "sensitivity_ranks"))

    # --- Narrative findings ----------------------------------------------------------
    ov = descriptive.dataset_overview(wb)
    rank = descriptive.comparable_period_ranking(wb)
    clean_rank = descriptive.comparable_period_ranking(
        wb[~wb["city_id"].astype(str).isin(set(art["city_id"].astype(str)))])
    smax, smin = season_all.loc[season_all["median"].idxmax()], season_all.loc[season_all["median"].idxmin()]
    vc = tr["direction"].value_counts()
    tr_clean = tr[~tr["artifact_flag"]]
    vc_clean = tr_clean["direction"].value_counts()
    t_by = {t.name: t for t in tests}
    fried = tests[0]
    wk = tests[3]
    pc, pc_clean = tests[4], tests[5]
    corr_anom = corr[corr["deseasonalized"]].set_index("x")
    corr_raw = corr[~corr["deseasonalized"]].set_index("x")
    fixed = cities[cities["fixed_annual_run"] >= 3]
    shift_m = (pd.to_datetime(art.loc[art["artifact_reason"].str.contains("shift"), "break_date"])
               .dt.to_period("M").value_counts())
    top_artifacts = set(art["city_id"].astype(str))
    n_top10_flagged = len(set(rank.head(10)["city_id"].astype(str)) & top_artifacts)

    L = []
    L.append("# Findings report — Pakistan Environmental Analytics\n")
    L.append(f"_Generated {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC by `scripts/generate_reports.py` from data "
             f"prepared {manifest['generated_utc'][:10]}. Every number below is computed from the stored datasets._\n")
    L.append("> **All PM2.5 values are model estimates** (World Bank Global PM2.5 Watch), not monitor measurements. "
             "Weather is ERA5 reanalysis. Results describe the model output and are associations, not causal effects.\n")
    L.append("## 1. Coverage\n")
    L.append(f"- World Bank: **{ov['cities']} places**, **{ov['date_min']:%d %b %Y} – {ov['date_max']:%d %b %Y}**, "
             f"**{ov['n_values']:,} city-days**; {pat['n_missing']} calendar dates are missing for every place"
             + (", all of them the last day of a month" if pat["all_month_end"] else "") + ".")
    if not hf.empty:
        L.append(f"- Kaggle/HF hourly: **{hf['city_id'].nunique()} cities**, {hf['timestamp'].min():%d %b %Y} – "
                 f"{hf['timestamp'].max():%d %b %Y}, {len(hf):,} city-hours (licence unknown; treated as modelled).")
    L.append(f"- ERA5 weather: **{weather['city_id'].nunique()} places**, {len(ww):,} matched PM2.5–weather city-days.\n")
    L.append("## 2. Levels and rankings\n")
    L.append(f"- Median daily PM2.5 across all city-days: **{ov['median']:.1f} µg/m³** (mean {ov['mean']:.1f}).")
    L.append(f"- {(cs['median'] > WHO_PM25_24H).mean() * 100:.0f} % of places have a median above the WHO 24-h "
             f"guideline ({WHO_PM25_24H:g} µg/m³); the median place exceeds it on "
             f"{cs['pct_days_above_threshold'].median():.0f} % of days.")
    L.append("- Highest medians over the full common period:\n")
    L.append(md_table(rank.head(10)[["rank", "city_label", "median", "n"]].merge(
        cities[["city_label", "artifact_reason"]], on="city_label", how="left")) + "\n")
    L.append(f"- **{n_top10_flagged} of these top 10** are flagged for model artifacts. Excluding all flagged places, "
             f"the top three are: " + ", ".join(f"{r.city_label} ({r.median:.0f})" for r in clean_rank.head(3).itertuples())
             + " µg/m³.\n")
    L.append("## 3. Seasonality\n")
    L.append(f"- Median PM2.5 is highest in **{smax['season']} ({smax['median']:.1f} µg/m³)** and lowest in "
             f"**{smin['season']} ({smin['median']:.1f} µg/m³)**.")
    L.append(f"- {fried.interpretation}\n")
    L.append("## 4. Trends\n")
    L.append(f"- All places: {vc.get('decreasing', 0)} decreasing, {vc.get('increasing', 0)} increasing, "
             f"{vc.get('no clear trend', 0)} no clear trend (deseasonalised OLS with Newey–West CI, BH-FDR).")
    L.append(f"- Excluding the {int(tr['artifact_flag'].sum())} artifact-flagged places: {vc_clean.get('decreasing', 0)} "
             f"decreasing, {vc_clean.get('increasing', 0)} increasing, {vc_clean.get('no clear trend', 0)} no clear trend; "
             f"median slope {tr_clean['slope_per_year'].median():+.2f} µg/m³/yr.")
    L.append(f"- {pc.name}: {pc.interpretation}")
    L.append(f"- {pc_clean.name}: {pc_clean.interpretation}\n")
    L.append("## 5. Weather relationships (within-city Spearman, city = unit)\n")
    tbl = pd.DataFrame({"raw median ρ": corr_raw["median_r"], "anomaly median ρ": corr_anom["median_r"],
                        "cities": corr_anom["n_cities"], "anomaly significant (FDR)": corr_anom["n_significant_fdr"]})
    L.append(md_table(tbl.reset_index().rename(columns={"x": "variable"}), ".2f") + "\n")
    flips = [v for v in tbl.index if tbl.loc[v, "raw median ρ"] * tbl.loc[v, "anomaly median ρ"] < 0]
    if flips:
        L.append(f"- Sign changes between raw and deseasonalised correlations for **{', '.join(flips)}** — the raw "
                 "association reflects the shared seasonal cycle.")
    L.append("- Correlations use autocorrelation-adjusted effective sample sizes; they are associations, not causal "
             "effects, and the PM2.5 model itself uses ERA5 inputs.\n")
    L.append("## 6. Weekday vs weekend\n")
    L.append(f"- {wk.interpretation}\n")
    L.append("## 7. Data quality\n")
    L.append(f"- **Fixed annual means:** {len(fixed)} places repeat the same annual mean (within 0.5 %) for ≥ 3 "
             "consecutive complete years: " + ", ".join(f"{r.city_label} ({int(r.fixed_annual_run)} yrs)"
                                                         for r in fixed.sort_values('fixed_annual_run', ascending=False).itertuples()) + ".")
    if len(shift_m):
        L.append(f"- **Abrupt level shifts:** {int(art['artifact_reason'].str.contains('shift').sum())} places; most "
                 f"common month {shift_m.index[0].strftime('%B %Y')} ({int(shift_m.iloc[0])} places).")
    L.append(f"- **Identical model series:** {int((cities['series_group_size'] > 1).sum())} places share their exact "
             f"daily series with another place ({cities['series_group'].nunique()} distinct series in total).")
    L.append(f"- **Ambiguous names:** {int(cities['name_ambiguous'].sum())} places share a normalised name with "
             "another GeoNames ID.")
    if al is not None:
        L.append(f"- **Hourly timestamps (Kaggle/HF):** ozone peaks at hour label {al['pollutant_peak_hour']}, "
                 f"temperature at {al['weather_peak_hour']} (offset {al['offset_hours']:+d} h), suggesting pollutant "
                 "and weather columns use different time references.")
    if len(hf_same):
        pairs = sorted({f"{a} = {b}" for a, b in hf_same[["city_a", "city_b"]].itertuples(index=False)})
        L.append(f"- **Hourly identical series:** {'; '.join(pairs)} (variables: "
                 f"{', '.join(sorted(hf_same['variable'].unique()))}).")
    if len(scmp):
        L.append(f"- **Source agreement:** on {int(scmp['n_days'].sum())} paired city-days, daily Pearson r between "
                 f"the Kaggle/HF and World Bank PM2.5 ranges from {scmp['pearson_r'].min():+.2f} to "
                 f"{scmp['pearson_r'].max():+.2f} (median {scmp['pearson_r'].median():+.2f}); ratio of medians "
                 f"{scmp['ratio_of_medians'].min():.2f}–{scmp['ratio_of_medians'].max():.2f}.\n")
    L.append("## 8. Sensitivity\n")
    L.append(md_table(sens[["scenario", "rows_removed_pct", "cities", "overall_median", "top_city",
                            "top10_overlap_with_baseline", "rank_spearman_vs_baseline"]], ".2f") + "\n")
    L.append("## Output files\n")
    L.extend(f"- `reports/{p.name}`" for p in out)
    (REPORTS_DIR / "findings.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"Wrote {len(out)} CSV reports and reports/findings.md to {REPORTS_DIR}")


if __name__ == "__main__":
    main()
