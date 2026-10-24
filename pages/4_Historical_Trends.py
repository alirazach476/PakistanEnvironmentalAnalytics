import streamlit as st

from src.analysis import trends
from src.ui import cached
from src.ui.common import (chart, city_picker, current_filters, download, filter_summary, filtered_wb, get, note,
                           page_header, require_data)
from src.visualization import charts, maps
from src.visualization.themes import color_map

page_header("Historical Trends", "How PM2.5 has changed over time. Long-term trends are estimated on deseasonalised "
            "monthly anomalies with autocorrelation-robust uncertainty, and controlled for multiple testing across cities.")

f = current_filters()
fk = cached.key(f)
wb = filtered_wb(f)
st.caption(f"Current selection: {filter_summary(f)}")
if not require_data(wb):
    st.stop()
if f["seasons"]:
    note("A season filter is active: monthly and annual aggregates include only the selected months, and the "
         "complete-year rule (≥ 11 complete months) will exclude every year. Clear the season filter for annual views.",
         "caveat")

chart(charts.national_band(cached.monthly_all(fk), title="Monthly PM2.5 across all filtered cities"), key="tr_band")

sel = city_picker(wb, "tr_cities", default_n=5)
colors = color_map(sel)
d = wb[wb["city_label"].astype(str).isin(sel)]
if sel:
    window = st.select_slider("Rolling window (days)", [7, 30, 90, 180, 365], value=90, key="tr_win")
    roll = trends.rolling_mean(d, window=window, group_col="city_label")
    chart(charts.multi_city_lines(roll, "date", "pm25_rolling", title=f"{window}-day rolling mean PM2.5",
                                  colors=colors, y_title="Rolling mean PM2.5 (µg/m³)"), key="tr_roll")
    c1, c2 = st.columns(2)
    with c1:
        chart(charts.annual_lines(trends.annual_series(d, group_cols=("city_label",)), colors=colors), key="tr_ann")
    with c2:
        yoy = trends.year_over_year(d, group_col="city_label")
        chart(charts.yoy_heatmap(yoy), key="tr_yoy")

st.subheader("Long-term trend per city")
tr = cached.city_trends(fk)
if require_data(tr, "Trends need at least 24 complete months per city; widen the date range."):
    vc = tr["direction"].value_counts()
    c = st.columns(3)
    c[0].metric("Decreasing (FDR q < 0.05)", int(vc.get("decreasing", 0)), border=True)
    c[1].metric("Increasing (FDR q < 0.05)", int(vc.get("increasing", 0)), border=True)
    c[2].metric("No clear trend", int(vc.get("no clear trend", 0)), border=True)
    note("Method: monthly means (≥ 20 valid days) minus each city's average for that calendar month; OLS slope with "
         "Newey–West (HAC, 12 lags) 95 % CI; Theil–Sen slope as a robustness check; Benjamini–Hochberg FDR across "
         "cities. Places that share an identical model series are counted separately here — see Statistical Analysis "
         "for de-duplicated inference.")
    cities = get("wb_cities")
    ids = cities["city_id"].astype(str)
    tr = tr.assign(artifact_flag=tr["city_id"].astype(str).map(dict(zip(ids, cities["artifact_flag"]))).fillna(False),
                   artifact_reason=tr["city_id"].astype(str).map(dict(zip(ids, cities["artifact_reason"]))).fillna(""))
    fl = tr[tr["artifact_flag"].astype(bool)]
    if len(fl):
        dec_fl = int((fl["direction"] != "no clear trend").sum())
        n_sig = int((tr["direction"] != "no clear trend").sum())
        note(f"<b>Artifact caveat:</b> {len(fl)} of these {len(tr)} places are flagged for a fixed annual mean or an "
             f"abrupt level shift in the modelled series, and they account for {dec_fl} of the {n_sig} 'clear' trends. "
             "A linear trend fitted across a step change describes the step, not gradual change. Use the sidebar "
             "toggle to exclude them and compare.", "caveat")
    c1, c2 = st.columns([1, 1.1])
    with c1:
        chart(charts.trend_forest(tr, n=12), key="tr_forest")
    with c2:
        chart(maps.trend_map(tr, get("wb_cities")), key="tr_map")

    one = st.selectbox("Inspect one city's trend", tr.sort_values("mean_level", ascending=False)["city_label"].astype(str),
                       key="tr_one")
    cd = wb[wb["city_label"].astype(str) == one]
    m = trends.deseasonalize(trends.monthly_series(cd))
    fit = trends.trend_fit_line(m["period"], m["anomaly"])
    chart(charts.trend_chart(m, fit, trends.linear_trend(m["period"], m["anomaly"]), one), key="tr_one_chart")

    show = tr[["city_label", "n", "mean_level", "slope_per_year", "ci_low", "ci_high", "pct_change_per_year",
               "theil_sen_slope", "p_value", "q_value", "lag1_autocorr", "direction", "artifact_reason"]]
    st.dataframe(show.round(4), hide_index=True, height=360)
    download(show, "city_trends")
