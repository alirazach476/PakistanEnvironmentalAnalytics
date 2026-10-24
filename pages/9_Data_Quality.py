import pandas as pd
import streamlit as st

from src.analysis import data_quality as dq
from src.analysis.descriptive import observations_per_month
from src.ui.common import (chart, current_filters, download, exclusions, filter_summary, filtered_wb, get, manifest,
                           note, page_header, require_data)
from src.utils.config import SOURCES
from src.visualization import charts, maps

page_header("Data Quality & Coverage", "How complete, consistent and trustworthy each source is — and every rule "
            "the pipeline applied.", badges=())

f = current_filters()
st.caption(f"Current selection: {filter_summary(f)}")
wb_all, cities = get("wb_daily"), get("wb_cities")
hf, weather, overlap = get("hf_hourly"), get("weather_daily"), get("source_overlap")

# --- Sources ---------------------------------------------------------------------
st.subheader("Sources and coverage")
cov = dq.source_coverage({"wb_pm25": (wb_all, "date"), "hf_aq": (hf, "timestamp"),
                          "openmeteo_era5": (weather, "date")}, SOURCES)
st.dataframe(cov, hide_index=True)
c1, c2 = st.columns([1, 1.2])
with c1:
    chart(charts.source_timeline(cov), key="dq_tl")
with c2:
    pts = hf.groupby("city", as_index=False)[["latitude", "longitude"]].first() if not hf.empty else None
    chart(maps.coverage_map(cities, set(weather["city_id"].astype(str)) if not weather.empty else set(), pts), key="dq_map")

# --- Completeness & gaps -----------------------------------------------------------
st.subheader("Completeness and gaps (World Bank)")
wb = filtered_wb(f)
if require_data(wb):
    gaps = dq.find_gaps(wb["date"])
    pat = dq.missing_dates_pattern(gaps)
    comp = dq.completeness_by_city(wb, start=f["start"], end=f["end"]).merge(
        cities[["city_id", "city_label"]].astype(str), on="city_id", how="left")
    c = st.columns(4)
    c[0].metric("Calendar days in window", f"{comp['n_expected'].iloc[0]:,}" if len(comp) else "—", border=True)
    c[1].metric("Dates missing for all cities", f"{pat['n_missing']:,}", border=True)
    c[2].metric("Longest gap (days)", pat.get("max_run", 0), border=True)
    c[3].metric("Median city completeness", f"{comp['completeness_pct'].median():.2f} %" if len(comp) else "—", border=True)
    if pat["n_missing"]:
        share = pat["share_month_end"] * 100
        note(f"<b>{share:.0f} %</b> of the missing dates are the <b>last day of a calendar month</b>"
             + (" — a systematic pattern in the source files, not random loss." if pat["all_month_end"] else ".")
             + " Monthly means therefore use n−1 days; the ≥ 20-day rule is unaffected.", "caveat")
    c1, c2 = st.columns(2)
    with c1:
        chart(charts.gap_strip(gaps, f["start"], f["end"]), key="dq_gap")
    with c2:
        chart(charts.observations_by_month(observations_per_month(wb), title="City-day observations per month"),
              key="dq_obs")
    chart(charts.completeness_bar(comp), key="dq_comp")
    download(comp, "completeness_by_city")

# --- Pipeline log -------------------------------------------------------------------
st.subheader("Validation, exclusions and flags")
log = exclusions()
chart(charts.exclusion_chart(log), key="dq_excl")
st.dataframe(log, hide_index=True)
download(log, "pipeline_exclusions_log")
dup = dq.duplicate_summary(wb_all, ["city_id", "date"])
val = dq.validation_summary(wb_all, ["pm25", "latitude", "longitude"])
c1, c2 = st.columns(2)
with c1:
    st.markdown("**Duplicate check (processed World Bank table)**")
    st.json(dup)
with c2:
    st.markdown("**Plausible-range check (processed World Bank table)**")
    st.dataframe(val, hide_index=True)

# --- Model artifacts --------------------------------------------------------------
st.subheader("Model-artifact screening (World Bank series)")
art = cities[cities["artifact_flag"]]
fixed = cities[cities["fixed_annual_run"] >= 3]
shift = art[art["artifact_reason"].str.contains("shift")]
top_month = (pd.to_datetime(shift["break_date"]).dt.to_period("M").value_counts() if len(shift) else pd.Series(dtype=int))
c = st.columns(3)
c[0].metric("Places flagged", f"{len(art)} / {len(cities)}", border=True)
c[1].metric("Fixed annual mean (≥ 3 years)", len(fixed), border=True)
c[2].metric("Abrupt level shift", len(shift), border=True)
txt = (f"<b>{len(fixed)}</b> places repeat the same annual mean (within 0.5 %) for three or more consecutive complete "
       f"years — real annual concentrations do not do this, so the model appears to scale daily values to a fixed "
       f"annual level. <b>{len(shift)}</b> places show an abrupt step in their deseasonalised series")
if len(top_month):
    txt += (f"; the most common month for the step is <b>{top_month.index[0].strftime('%B %Y')}</b> "
            f"({int(top_month.iloc[0])} places, {shift['province'].value_counts().index[0]} most affected)")
txt += (". These patterns are consistent with changes in model inputs or versions rather than in air quality. "
        "Flagged places are kept by default; the sidebar toggle removes them from every page. Trends and rankings "
        "involving them should be read with care.")
note(txt, "caveat")
c1, c2 = st.columns(2)
with c1:
    from src.analysis.trends import annual_series
    chart(charts.artifact_annual_chart(annual_series(wb_all), fixed), key="dq_art_ann")
with c2:
    chart(charts.break_date_chart(cities), key="dq_art_brk")
show_art = art[["city_label", "province", "artifact_reason", "fixed_annual_run", "fixed_annual_from", "fixed_annual_to",
                "break_date", "break_shift", "break_shift_rel", "break_t"]].sort_values("break_t", ascending=False)
st.dataframe(show_art.round(2), hide_index=True, height=300,
             column_config={"break_date": st.column_config.DateColumn(format="YYYY-MM")})
download(show_art, "model_artifact_flags")

# --- Identity checks -------------------------------------------------------------
st.subheader("Place identity checks")
c1, c2 = st.columns(2)
with c1:
    amb = cities[cities["name_ambiguous"]][["city_label", "province", "latitude", "longitude", "population", "geonameid"]]
    st.markdown(f"**Shared or near-identical place names** ({len(amb)})")
    st.dataframe(amb, hide_index=True, height=260)
    st.caption("Names are compared after removing spaces/punctuation (e.g. 'Arif Wala' vs 'Arifwala'). Labels are "
               "disambiguated; coordinates come from the source and are not corrected.")
with c2:
    grp = cities[cities["series_group_size"] > 1].sort_values("series_group")
    st.markdown(f"**Places sharing an identical PM2.5 series** ({len(grp)} places in "
                f"{grp['series_group'].nunique()} groups)")
    st.dataframe(grp[["series_group", "city_label", "province", "population", "is_series_representative"]],
                 hide_index=True, height=260)
    st.caption("The model assigns the same daily values to these places (same grid cell). Inferential tests keep one "
               "representative per group.")
pc = dq.province_consistency(cities)
odd = pc[~pc["consistent"]]
with st.expander(f"Province-code consistency candidates ({len(odd)} places whose 5 nearest neighbours are mostly in "
                 "another ADM1 code)"):
    st.caption("Places near a provincial boundary or in a small territory surrounded by another province are expected "
               "here; this is a review list, not a list of errors.")
    st.dataframe(odd, hide_index=True)

# --- Hourly source checks -------------------------------------------------------
if not hf.empty:
    st.subheader("Kaggle/HF hourly dataset checks")
    cols = [c for c in ["pm25", "pm10", "carbon_monoxide", "nitrogen_dioxide", "sulphur_dioxide", "ozone", "dust",
                        "temperature", "humidity", "precipitation", "wind_speed", "pressure"] if c in hf.columns]
    c1, c2 = st.columns(2)
    with c1:
        chart(charts.missingness_heatmap(dq.missingness_matrix(hf, cols, "city"),
                                         subtitle=charts.HF_SRC), key="dq_miss")
    with c2:
        al = dq.diurnal_peak_alignment(hf)
        chart(charts.diurnal_alignment_chart(al["profile"]), key="dq_diur")
    same = pd.concat([dq.identical_series(hf, v, "timestamp", "city") for v in cols], ignore_index=True)
    if len(same):
        st.markdown("**Identical series between cities in the hourly file**")
        st.dataframe(same, hide_index=True)

# --- Source comparison ------------------------------------------------------------
if not overlap.empty:
    st.subheader("Source-to-source comparison")
    comp_src = dq.source_comparison(overlap)
    note(f"Each Kaggle/HF city is paired with the nearest World Bank place (≤ {manifest().get('rules', {}).get('overlap_max_km', 25)} km) "
         "on the same calendar date. Both are model outputs; disagreement shows model uncertainty, not which is right. "
         "The two sources are never pooled.")
    c1, c2 = st.columns([1, 1.2])
    with c1:
        chart(charts.source_comparison_scatter(overlap), key="dq_src")
    with c2:
        st.dataframe(comp_src.round(2), hide_index=True, height=440)
        download(comp_src, "source_comparison")
