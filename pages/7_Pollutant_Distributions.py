import streamlit as st

from src.analysis import descriptive
from src.analysis.data_quality import identical_series, outlier_summary
from src.ui import cached
from src.ui.common import (chart, city_picker, current_filters, download, filter_summary, filtered_wb, get, note,
                           page_header, require_data)
from src.utils.config import LABELS, UNITS
from src.visualization import charts
from src.visualization.themes import color_map

page_header("Pollutant Distributions", "Shape, spread, tails and outliers of pollutant concentrations, by city and source.")

f = current_filters()
st.caption(f"Current selection: {filter_summary(f)}")
_wb_all, _hf_all = get("wb_daily"), get("hf_hourly")
_labels = {"wb": f"World Bank daily PM2.5 ({_wb_all['city_id'].nunique()} places, "
                 f"{_wb_all['date'].min():%Y}–{_wb_all['date'].max():%Y})"}
if not _hf_all.empty:
    _labels["hf"] = (f"Kaggle/HF hourly pollutants ({_hf_all['city_id'].nunique()} cities, "
                     f"{_hf_all['date'].min():%b %Y}–{_hf_all['date'].max():%b %Y})")
source = st.segmented_control("Source", list(_labels), default="wb", key="di_src",
                              format_func=lambda s: _labels[s]) or "wb"

if source == "wb":
    wb = filtered_wb(f)
    if not require_data(wb):
        st.stop()
    log_x = st.toggle("Log-scale histogram", key="di_log", help="PM2.5 is right-skewed; a log scale shows the shape better.")
    c1, c2 = st.columns(2)
    with c1:
        chart(charts.histogram(wb, log_x=log_x), key="di_hist")
    with c2:
        summary = cached.city_summary(cached.key(f))
        chart(charts.exceedance_bar(summary, n=20), key="di_exc")

    sel = city_picker(wb, "di_cities", default_n=6)
    if sel:
        d = wb[wb["city_label"].astype(str).isin(sel)].assign(city_label=lambda x: x["city_label"].astype(str))
        colors = color_map(sel)
        c1, c2 = st.columns(2)
        with c1:
            chart(charts.box_violin(d, kind="violin", colors=colors), key="di_violin")
        with c2:
            chart(charts.ecdf_chart(d, colors=colors), key="di_ecdf")
        pct = descriptive.percentile_table(d)
        chart(charts.percentile_chart(pct, title="Percentiles of daily PM2.5 (P10–P99)"), key="di_pct")
        download(pct, "percentiles_selected_cities")

    st.subheader("Outliers")
    note("Rule: a day is flagged when |0.6745·(log x − median)/MAD| > 3.5 within its city (robust z on log PM2.5). "
         "Flagged values are <b>kept</b> unless 'Exclude flagged outliers' is switched on in the sidebar. "
         "Tukey box-plot whiskers (1.5×IQR) are a separate, display-only rule.")
    os_ = outlier_summary(wb)
    c1, c2 = st.columns([1, 1.4])
    with c1:
        st.dataframe(os_.head(30).round(2), hide_index=True, height=380)
        download(os_, "outlier_summary")
    with c2:
        top = os_.iloc[0]["city_label"] if len(os_) else None
        if top is not None:
            chart(charts.outlier_timeline(wb[wb["city_label"] == top], str(top)), key="di_outl")
else:
    hf = get("hf_hourly")
    if not require_data(hf, "The Kaggle/HF hourly dataset is not available."):
        st.stop()
    hf = hf[(hf["date"] >= f["start"]) & (hf["date"] <= f["end"])]
    if not require_data(hf, "The selected date range does not overlap the hourly dataset "
                            f"({get('hf_hourly')['date'].min():%d %b %Y} – {get('hf_hourly')['date'].max():%d %b %Y})."):
        st.stop()
    pol = st.segmented_control("Pollutant", ["pm25", "pm10", "nitrogen_dioxide", "sulphur_dioxide", "carbon_monoxide",
                                             "ozone", "dust"], default="pm25", key="di_pol",
                               format_func=lambda v: LABELS[v]) or "pm25"
    same = identical_series(hf, pol, "timestamp", "city")
    same_txt = (" Identical series (same model grid cell): " + "; ".join(f"{r.city_a} = {r.city_b}" for r in same.itertuples())
                + "." if len(same) else "")
    note("Hourly values from an undocumented Kaggle upload; variable names match the Open-Meteo Air Quality API "
         "(CAMS model), so they are treated as <b>modelled</b>. Licence is unknown." + same_txt, "caveat")
    sub = charts.HF_SRC
    d = hf.assign(city_label=hf["city"].astype(str))
    c1, c2 = st.columns(2)
    with c1:
        fig = charts.histogram(d, pol, title=f"Distribution of hourly {LABELS[pol]}", subtitle=sub, unit_name="city-hours")
        chart(fig, key="di_hf_hist")
    with c2:
        fig = charts.box_violin(d, pol, kind="box", title=f"Hourly {LABELS[pol]} by city", subtitle=sub)
        fig.update_yaxes(title=f"Hourly {LABELS[pol]} ({UNITS[pol]})")
        fig.layout.shapes = ()
        fig.layout.annotations = ()
        chart(fig, key="di_hf_box")
    stats = descriptive.summary_stats(d, pol, "city")
    st.dataframe(stats.round(1), hide_index=True)
    download(stats, f"hf_{pol}_summary")
