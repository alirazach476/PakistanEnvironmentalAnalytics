import pandas as pd
import streamlit as st

from src.analysis import descriptive, seasonality
from src.analysis.data_quality import completeness_by_city
from src.ui import cached
from src.ui.common import (chart, current_filters, download, filter_summary, filtered_wb, fmt, get, kpi, manifest,
                           note, page_header, require_data)
from src.utils.config import WHO_PM25_24H
from src.visualization import charts, maps

TITLE = "Pakistan Environmental Analytics"
SUB = ("Historical PM2.5, weather and statistical insights for Pakistani cities, computed live from stored "
       "datasets. Every number on this page reflects the filters in the sidebar.")

f = current_filters()
fk = cached.key(f)
wb = filtered_wb(f)
if wb.empty:
    page_header(TITLE, SUB)
    require_data(wb)
    st.stop()

ov = descriptive.dataset_overview(wb)
summary = cached.city_summary(fk)
page_header(TITLE, SUB, stats=[
    (f"{ov['cities']:,}", "places"), (f"{ov['n_values']:,}", "city-days"), (f"{ov['median']:.1f} µg/m³", "median PM2.5"),
    (f"{(summary['median'] > WHO_PM25_24H).mean() * 100:.0f}%", "places with median above WHO 24-h")])
st.caption(f"Current selection: {filter_summary(f)}")
ranking = descriptive.comparable_period_ranking(wb, f["start"], f["end"], min_coverage=0.8)
comp = completeness_by_city(wb, start=f["start"], end=f["end"])
completeness = 100 * comp["n_observed"].sum() / comp["n_expected"].sum() if len(comp) else float("nan")
n_sources = len(manifest().get("inputs", {}))

c = st.columns(4)
with c[0]:
    kpi("Cities represented", f"{ov['cities']:,}", "World Bank places (GeoNames)")
with c[1]:
    kpi("Date range", f"{ov['date_min']:%b %Y} – {ov['date_max']:%b %Y}", f"{ov['n_dates']:,} distinct days")
with c[2]:
    kpi("City-day observations", f"{ov['n_values']:,}", "daily modelled estimates")
with c[3]:
    kpi("Median PM2.5", fmt(ov["median"], 1, "µg/m³"), f"all city-days · WHO 24-h guideline {WHO_PM25_24H:g}")
st.write("")
c = st.columns(3)
with c[0]:
    if len(ranking):
        top = ranking.iloc[0]
        kpi("Highest comparable-period median", str(top["city_label"]), f"{top['median']:.1f} µg/m³ · cities with ≥ 80 % "
            "coverage of the selected window")
    else:
        kpi("Highest comparable-period median", "—", "no city has ≥ 80 % coverage of the window")
with c[1]:
    kpi("Data completeness", fmt(completeness, 1, "%"), "city-days present ÷ calendar city-days in window")
with c[2]:
    kpi("Source datasets", str(n_sources), "WB PM2.5 · Kaggle/HF hourly · ERA5 weather")

st.write("")
note("<b>What these numbers are.</b> PM2.5 values on this page are <b>machine-learning model estimates</b> "
     "(World Bank Global PM2.5 Watch), not readings from monitors. They are concentrations in µg/m³ and are never "
     "converted to AQI. The WHO 2021 24-hour guideline (15 µg/m³) is drawn only as a reference line.")

# --- Key findings (all computed) --------------------------------------------
st.subheader("Key findings for this selection")
monthly = cached.monthly_all(fk)
season = seasonality.seasonal_summary(wb)
trends = cached.city_trends(fk)
lines = []
if len(summary):
    above = (summary["median"] > WHO_PM25_24H).mean() * 100
    lines.append(f"**{above:.0f} %** of the {len(summary)} cities have a median daily PM2.5 above the WHO 24-hour "
                 f"guideline of {WHO_PM25_24H:g} µg/m³; the median city spends "
                 f"**{summary['pct_days_above_threshold'].median():.0f} %** of days above it.")
if len(ranking) >= 3:
    lines.append("Highest medians over the comparable window: " + ", ".join(
        f"**{r.city_label}** ({r.median:.0f})" for r in ranking.head(3).itertuples()) + " µg/m³.")
if len(season) > 1:
    hi_s, lo_s = season.loc[season["median"].idxmax()], season.loc[season["median"].idxmin()]
    lines.append(f"Seasonality is strong: median PM2.5 is **{hi_s['median']:.0f} µg/m³ in {hi_s['season']}** versus "
                 f"**{lo_s['median']:.0f} µg/m³ in {lo_s['season']}** (ratio {hi_s['median'] / lo_s['median']:.1f}×).")
if len(trends):
    vc = trends["direction"].value_counts()
    lines.append(f"Deseasonalised trends (FDR-controlled): **{vc.get('decreasing', 0)}** cities decreasing, "
                 f"**{vc.get('increasing', 0)}** increasing, **{vc.get('no clear trend', 0)}** without a clear trend; "
                 f"median slope {trends['slope_per_year'].median():+.2f} µg/m³ per year.")
cities_all = get("wb_cities")
present = cities_all[cities_all["city_id"].astype(str).isin(set(wb["city_id"].astype(str)))]
if "artifact_flag" in present.columns and present["artifact_flag"].any():
    flagged = present[present["artifact_flag"]]
    top3 = set(ranking.head(3)["city_id"].astype(str)) if len(ranking) else set()
    n_top = len(top3 & set(flagged["city_id"].astype(str)))
    lines.append(f"**Data caveat:** {len(flagged)} of {len(present)} places show model artifacts (a fixed annual mean "
                 f"across years or an abrupt level shift){f', including {n_top} of the top 3 above' if n_top else ''}. "
                 "Rankings and trends for these places reflect model behaviour as much as air quality — see "
                 "Data Quality, or exclude them with the sidebar toggle.")
for line in lines:
    st.markdown(f"- {line}")
st.caption("Associations and model-based estimates only — see Statistical Analysis for tests, effect sizes and caveats.")

# --- Charts -----------------------------------------------------------------
left, right = st.columns([1.25, 1])
with left:
    chart(maps.city_metric_map(summary, title="Median PM2.5 by city"), key="ov_map")
with right:
    chart(charts.city_ranking_bar(summary, n=15, title="15 highest city medians"), key="ov_rank")

chart(charts.national_band(monthly), key="ov_band")

c1, c2 = st.columns(2)
with c1:
    chart(charts.season_box(wb), key="ov_season")
with c2:
    chart(charts.province_box(summary), key="ov_prov")

st.subheader("City summary table")
show = summary[["rank_by_median", "city_label", "province", "n", "median", "mean", "p95", "max",
                "pct_days_above_threshold", "first_date", "last_date"]].rename(
    columns={"rank_by_median": "rank", "n": "days", "pct_days_above_threshold": "% days > WHO 24h"})
st.dataframe(show, hide_index=True, height=360, column_config={
    "median": st.column_config.NumberColumn("median (µg/m³)", format="%.1f"),
    "mean": st.column_config.NumberColumn("mean (µg/m³)", format="%.1f"),
    "p95": st.column_config.NumberColumn("p95 (µg/m³)", format="%.1f"),
    "max": st.column_config.NumberColumn("max (µg/m³)", format="%.1f"),
    "% days > WHO 24h": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%.0f%%"),
    "first_date": st.column_config.DateColumn("first date", format="YYYY-MM-DD"),
    "last_date": st.column_config.DateColumn("last date", format="YYYY-MM-DD"),
})
c1, c2 = st.columns(2)
with c1:
    download(show, "city_summary", "Download city summary (CSV)")
with c2:
    download(wb[["city_label", "province", "date", "pm25", "season", "is_outlier", "source_id", "value_type"]]
             .head(250_000), "filtered_daily_pm25", "Download filtered daily data (CSV, first 250k rows)", key="dl_ov_raw")
