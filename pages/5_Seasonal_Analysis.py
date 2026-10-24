import streamlit as st

from src.analysis import seasonality
from src.analysis.data_quality import diurnal_peak_alignment
from src.analysis.statistical_tests import weekday_weekend_test
from src.ui import cached
from src.ui.common import (chart, city_picker, current_filters, download, filter_summary, filtered_wb, get, independent,
                           note, page_header, require_data)
from src.utils.config import LABELS, UNITS
from src.visualization import charts
from src.visualization.themes import color_map

page_header("Seasonal Analysis", "Month-of-year, seasonal, weekly and (for the hourly source only) diurnal patterns.")

f = current_filters()
wb = filtered_wb(f)
st.caption(f"Current selection: {filter_summary(f)}")
if not require_data(wb):
    st.stop()

# --- Month × city heatmap -----------------------------------------------------
summary = cached.city_summary(cached.key(f))
c1, c2 = st.columns([2, 1])
with c1:
    mode = st.segmented_control("Cities in heatmap", ["Most populous", "Highest median", "Lowest median"],
                                default="Most populous", key="se_mode") or "Most populous"
with c2:
    n = st.slider("Number of cities", 5, 40, 20, key="se_n")
order = {"Most populous": summary.sort_values("population", ascending=False),
         "Highest median": summary.sort_values("median", ascending=False),
         "Lowest median": summary.sort_values("median")}[mode]["city_label"].astype(str).head(n).tolist()
mat = seasonality.month_city_matrix(wb[wb["city_label"].astype(str).isin(order)]).reindex(order)
chart(charts.month_city_heatmap(mat, title=f"Median PM2.5 by month — {n} {mode.lower()} cities"), key="se_heat")
download(mat.reset_index(), "month_by_city_median")

c1, c2 = st.columns(2)
with c1:
    chart(charts.season_box(wb), key="se_box")
with c2:
    chart(charts.month_profile_chart(seasonality.month_profile(wb), by=None,
                                     title="Month-of-year profile, all filtered cities"), key="se_prof_all")

sel = city_picker(wb, "se_cities", default_n=5)
if sel:
    d = wb[wb["city_label"].astype(str).isin(sel)]
    prof = seasonality.month_profile(d.assign(city_label=d["city_label"].astype(str)), by="city_label")
    chart(charts.month_profile_chart(prof, colors=color_map(sel), title="Month-of-year profile by city"), key="se_prof")

ss = seasonality.seasonal_summary(wb, by="province")
st.subheader("Seasonal summary by province")
st.dataframe(ss.round(1), hide_index=True)
download(ss, "seasonal_summary_by_province")

# --- Weekday / weekend ---------------------------------------------------------
st.subheader("Weekday vs weekend")
c1, c2 = st.columns([1.3, 1])
with c1:
    chart(charts.weekday_chart(seasonality.weekday_profile(wb)), key="se_wd")
with c2:
    res = weekday_weekend_test(independent(wb))
    st.markdown(f"**{res.name}**")
    st.markdown(res.interpretation)
    for cav in res.caveats[2:]:
        st.caption(cav)

# --- Hour of day (hourly source only) -------------------------------------------
st.subheader("Hour-of-day profile (Kaggle/HF hourly source only)")
hf = get("hf_hourly")
if hf.empty or seasonality.temporal_resolution(hf) != "hourly":
    note("No genuinely hourly dataset is available, so no diurnal profile is shown. The World Bank data are daily.",
         "caveat")
else:
    al = diurnal_peak_alignment(hf)
    span = f"Covers {hf['date'].min():%d %b %Y}–{hf['date'].max():%d %b %Y} only, so it is not a year-round cycle."
    if abs(al["offset_hours"]) >= 3:
        note(f"Timestamp caveat: in this file ozone peaks at hour label {al['pollutant_peak_hour']} while temperature "
             f"peaks at hour label {al['weather_peak_hour']} ({al['offset_hours']:+d} h apart). Both normally peak in "
             f"the early-to-mid afternoon, so the two column groups appear to use different time references (hour "
             f"{al['pollutant_peak_hour']} UTC = {(al['pollutant_peak_hour'] + 5) % 24}:00 PKT). The x-axis shows the "
             f"source's hour label, unchanged. {span}", "caveat")
    else:
        note(f"Ozone and temperature peak within {abs(al['offset_hours'])} h of each other, consistent with a single "
             f"time reference. {span}")
    pol = st.segmented_control("Pollutant", ["pm25", "pm10", "nitrogen_dioxide", "carbon_monoxide", "ozone"],
                               default="pm25", key="se_pol",
                               format_func=lambda v: {"pm25": "PM2.5", "pm10": "PM10", "nitrogen_dioxide": "NO₂",
                                                      "carbon_monoxide": "CO", "ozone": "O₃"}[v]) or "pm25"
    cities = sorted(hf["city"].astype(str).unique())
    pick = st.multiselect("Cities (hourly source)", cities, default=cities[:5], max_selections=8, key="se_hfc")
    prof = seasonality.hour_profile(hf[hf["city"].isin(pick)], pol, by="city")
    fig = charts.hour_profile_chart(prof, title=f"Hour-of-day profile — {LABELS[pol]}")
    fig.update_yaxes(title=f"Mean {LABELS[pol]} ({UNITS[pol]})")
    chart(fig, key="se_hour")
