import streamlit as st

from src.analysis import descriptive, trends
from src.ui import cached
from src.ui.common import (chart, city_picker, current_filters, download, filter_summary, filtered_wb, note,
                           page_header, require_data)
from src.visualization import charts, maps
from src.visualization.themes import color_map

page_header("City Comparison", "Compare up to eight cities side by side on level, variability and timing. "
            "Rankings use a common window so cities are compared over the same days.")

f = current_filters()
wb = filtered_wb(f)
st.caption(f"Current selection: {filter_summary(f)}")
if not require_data(wb):
    st.stop()

sel = city_picker(wb, "cmp_cities", default_n=6)
if not sel:
    st.info("Select at least one city to compare.", icon=":material/location_city:")
    st.stop()
d = wb[wb["city_label"].astype(str).isin(sel)]
colors = color_map(sel)

stats = descriptive.summary_stats(d, "pm25", "city_label")
stats["city_label"] = stats["city_label"].astype(str)
chart(charts.city_interval_dots(stats, title="Median and 5th–95th percentile range"), key="cmp_dots")

agg = st.segmented_control("Time aggregation", ["Monthly mean", "Annual mean"], default="Monthly mean", key="cmp_agg") \
    or "Monthly mean"
if agg == "Monthly mean":
    m = trends.monthly_series(d, group_cols=("city_label",))
    chart(charts.multi_city_lines(m, "period", "mean", title="Monthly mean PM2.5", colors=colors,
                                  subtitle=charts.WB_SRC + " · months with ≥ 20 valid days",
                                  y_title="Monthly mean PM2.5 (µg/m³)"), key="cmp_lines")
else:
    a = trends.annual_series(d, group_cols=("city_label",))
    chart(charts.annual_lines(a, colors=colors), key="cmp_annual")

c1, c2 = st.columns(2)
with c1:
    kind = st.segmented_control("Distribution view", ["box", "violin"], default="box", key="cmp_kind") or "box"
    chart(charts.box_violin(d.assign(city_label=d["city_label"].astype(str)), kind=kind, colors=colors), key="cmp_box")
with c2:
    st.write("")
    st.write("")
    chart(charts.ecdf_chart(d.assign(city_label=d["city_label"].astype(str)), colors=colors), key="cmp_ecdf")

st.subheader("Comparable-period ranking (all cities)")
cov = st.slider("Minimum coverage of the selected window", 0.5, 1.0, 0.8, 0.05, key="cmp_cov",
                help="Cities with fewer observed days than this share of the window are excluded from the ranking.")
rank = descriptive.comparable_period_ranking(wb, f["start"], f["end"], min_coverage=cov)
note(f"{len(rank)} cities meet the coverage rule. Because every World Bank city covers the same dates, coverage only "
     "differs when filters cut the window; ranks are still descriptive and the World Bank values are model estimates.")
c1, c2 = st.columns([1, 1])
with c1:
    st.dataframe(rank.head(50).rename(columns={"city_label": "city", "median": "median (µg/m³)"}), hide_index=True,
                 height=420, column_config={"median (µg/m³)": st.column_config.NumberColumn(format="%.1f"),
                                            "coverage": st.column_config.NumberColumn(format="%.2f")})
    download(rank, "comparable_period_ranking")
with c2:
    summary = cached.city_summary(cached.key(f))
    chart(maps.city_metric_map(summary, metric="p95", metric_label="95th pct PM2.5 (µg/m³)",
                               title="95th-percentile PM2.5 by city"), key="cmp_map")

st.subheader("Summary statistics for the selected cities")
st.dataframe(stats.round(1), hide_index=True)
download(stats, "selected_city_statistics")
