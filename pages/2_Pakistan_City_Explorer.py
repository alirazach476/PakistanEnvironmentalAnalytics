import numpy as np
import pandas as pd
import streamlit as st

from src.analysis import descriptive, seasonality, trends
from src.analysis.correlations import correlation
from src.ui.common import (chart, current_filters, download, filter_summary, filtered_wb, filtered_wb_weather, fmt,
                           kpi, note, page_header, require_data)
from src.utils.config import LABELS, UNITS, WHO_PM25_24H
from src.visualization import charts

page_header("Pakistan City Explorer", "Explore one city in depth: daily history, seasonality, distribution, "
            "outliers and — where ERA5 weather was acquired — its weather context.")

f = current_filters()
wb = filtered_wb(f)
st.caption(f"Current selection: {filter_summary(f)}")
if not require_data(wb):
    st.stop()

options = wb.drop_duplicates("city_label").sort_values("population", ascending=False)["city_label"].astype(str).tolist()
city = st.selectbox("City", options, index=0, key="ex_city",
                    help="Ordered by population. Labels with a province or coordinates in brackets disambiguate places "
                         "sharing a name.")
d = wb[wb["city_label"].astype(str) == city].sort_values("date")
if not require_data(d, "No data for this city with the current filters."):
    st.stop()
meta = d.iloc[0]

st.markdown(f"**{city}** · {meta['province']} · {meta['latitude']:.3f}°N, {meta['longitude']:.3f}°E · "
            f"population (GeoNames) {int(meta['population']):,}")

anom = trends.deseasonalize(trends.monthly_series(d))
tr = trends.linear_trend(anom["period"], anom["anomaly"])
c = st.columns(4)
with c[0]:
    kpi("Median PM2.5", fmt(d["pm25"].median(), 1, "µg/m³"), f"{len(d):,} days")
with c[1]:
    kpi("95th percentile", fmt(d["pm25"].quantile(0.95), 1, "µg/m³"), "1 day in 20 exceeds this")
with c[2]:
    kpi("Days above WHO 24-h", fmt((d["pm25"] > WHO_PM25_24H).mean() * 100, 0, "%"), f"> {WHO_PM25_24H:g} µg/m³")
with c[3]:
    if np.isfinite(tr.get("slope_per_year", np.nan)):
        kpi("Deseasonalised trend", f"{tr['slope_per_year']:+.2f} µg/m³/yr",
            f"95 % CI {tr['ci_low']:+.2f} to {tr['ci_high']:+.2f} (Newey–West)")
    else:
        kpi("Deseasonalised trend", "—", tr.get("note", "insufficient months"))

st.write("")
window = st.select_slider("Rolling-average window (days)", options=[1, 7, 14, 30, 60, 90, 180, 365], value=30,
                          key="ex_window", help="Centred, calendar-aware; requires ≥ 70 % of days in the window.")
roll = trends.rolling_mean(d, window=window)
series = d[["date", "pm25"]].merge(roll[["date", "pm25_rolling"]], on="date", how="left")
fig = charts.multi_city_lines(series.assign(city_label="Daily value"), "date", "pm25", title=f"Daily PM2.5 — {city}")
fig.data[0].line.color = "#b7d3f6"
fig.data[0].line.width = 1
fig.add_scatter(x=series["date"], y=series["pm25_rolling"], mode="lines", name=f"{window}-day rolling mean",
                line=dict(color="#184f95", width=2), hovertemplate="%{x|%d %b %Y}<br>rolling %{y:.1f}<extra></extra>")
chart(fig, key="ex_daily")

c1, c2 = st.columns(2)
with c1:
    chart(charts.calendar_heatmap(d, city), key="ex_cal")
with c2:
    chart(charts.month_profile_chart(seasonality.month_profile(d), by=None, title=f"Month-of-year profile — {city}"),
          key="ex_month")
c1, c2 = st.columns(2)
with c1:
    chart(charts.histogram(d, title=f"Distribution of daily PM2.5 — {city}", nbins=60), key="ex_hist")
with c2:
    chart(charts.outlier_timeline(d, city), key="ex_out")

# --- Weather context ---------------------------------------------------------
st.subheader("Weather context")
ww = filtered_wb_weather(f)
wc = ww[ww["city_label"].astype(str) == city] if not ww.empty else ww
if wc is None or wc.empty:
    with_wx = sorted(ww["city_label"].astype(str).unique()) if not ww.empty else []
    note("ERA5 weather was acquired only for the most populous World Bank cities and those matching the Kaggle/HF "
         "cities, so no weather relationship is shown for this city."
         + (f" Cities with weather: {', '.join(with_wx)}." if with_wx else ""), "caveat")
else:
    var = st.segmented_control("Weather variable", ["temperature", "humidity", "wind_speed", "precipitation"],
                               default="wind_speed", format_func=lambda v: LABELS[v], key="ex_wvar") or "wind_speed"
    r = correlation(wc[var], wc["pm25"], "spearman")
    stats_text = (f"Spearman ρ = {r['r']:+.2f}, n = {r['n']:,} days, effective n ≈ {r['n_eff']:.0f}, "
                  f"autocorrelation-adjusted p = {r['p_value_adjusted_n']:.2g} · raw daily values (seasonal cycle not removed)")
    chart(charts.weather_scatter(wc, var, stats_text=stats_text, title=f"PM2.5 vs {LABELS[var].lower()} — {city}"),
          key="ex_wx")

st.subheader("Data")
cols = ["date", "pm25", "season", "is_outlier", "source_id", "value_type"]
download(d[["city_label", "province"] + cols], f"pm25_{city.replace(' ', '_')}", "Download this city's daily data (CSV)")
st.dataframe(descriptive.summary_stats(d, "pm25", "year").round(1), hide_index=True)
