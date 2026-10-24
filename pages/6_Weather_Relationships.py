import pandas as pd
import streamlit as st

from src.analysis.correlations import correlation
from src.analysis.statistical_tests import weather_correlation_test
from src.ui import cached
from src.ui.common import (chart, city_labels, current_filters, download, filter_summary, filtered_wb_weather, get,
                           note, page_header, require_data)
from src.utils.config import LABELS, UNITS
from src.visualization import charts

page_header("Weather & Pollution Relationships",
            "How daily PM2.5 co-varies with temperature, humidity, wind and precipitation. Associations only — "
            "none of these results establish causation.", badges=("modelled", "ERA5 reanalysis weather"))

f = current_filters()
fk = cached.key(f)
ww = filtered_wb_weather(f)
st.caption(f"Current selection: {filter_summary(f)}")
if not require_data(ww, "No matched PM2.5–weather days for the current filters. ERA5 weather was acquired for "
                        f"{get('weather_daily')['city_id'].nunique()} cities only; widen the filters or clear the "
                        "province filter."):
    st.stop()

note(f"<b>Matching:</b> World Bank daily PM2.5 joined to Open-Meteo ERA5 daily weather for the same place "
     f"(nearest 0.25° grid point) and calendar date — {len(ww):,} city-days across {ww['city_id'].nunique()} cities. "
     "The World Bank does not state its day boundary; weather uses the local (PKT) day, so lags of ±1 day are shown.")

c1, c2 = st.columns([2, 1])
with c1:
    x = st.segmented_control("Weather variable", ["temperature", "humidity", "wind_speed", "precipitation",
                                                  "pressure", "dew_point"], default="wind_speed", key="wx_var",
                             format_func=lambda v: LABELS[v]) or "wind_speed"
with c2:
    deseason = st.toggle("Remove seasonal cycle (anomalies)", value=True, key="wx_des",
                         help="Subtract each city's calendar-month mean from both variables. Without this, correlations "
                              "mostly reflect the shared annual cycle.")

r_raw = correlation(ww.sort_values(["city_id", "date"])[x], ww.sort_values(["city_id", "date"])["pm25"], "spearman")
test = weather_correlation_test(ww, x, deseasonalize=deseason)
stats_text = (f"Pooled raw Spearman ρ = {r_raw['r']:+.2f} (n = {r_raw['n']:,}); within-city "
              f"{'anomaly ' if deseason else ''}median ρ = {test.effect_size:+.2f}")
chart(charts.weather_scatter(ww, x, stats_text=stats_text), key="wx_scatter")

c = st.columns(4)
c[0].metric("Cities", test.n, border=True)
c[1].metric("Median within-city ρ", f"{test.effect_size:+.2f}", border=True,
            help="One Spearman coefficient per city; the city is the unit of analysis.")
c[2].metric("Cities significant (FDR)", f"{test.assumption_checks.get('n_significant_fdr', 0)} / {test.n}", border=True,
            help="Benjamini–Hochberg on p-values recomputed with an effective sample size for autocorrelation.")
c[3].metric("Median effective n", f"{test.assumption_checks.get('median_n_eff', float('nan')):.0f}", border=True,
            help="Bretherton et al. (1999) adjustment; much smaller than the raw day count.")
st.markdown(test.interpretation)

c1, c2 = st.columns(2)
with c1:
    per = cached.weather_corr(fk, x, deseason)
    chart(charts.city_correlation_dots(per, city_labels(), f"Per-city ρ: PM2.5 vs {LABELS[x].lower()}"
                                       + (" (anomalies)" if deseason else "")), key="wx_dots")
with c2:
    chart(charts.lag_chart(cached.weather_lags(fk, x, deseason), x), key="wx_lag")

st.subheader("Correlation matrix")
corr, n = cached.weather_matrix(fk, deseason)
chart(charts.correlation_heatmap(corr, n, title="Spearman correlation matrix" + (" — deseasonalised anomalies"
                                                                                    if deseason else " — raw daily values")),
      key="wx_corr")

st.subheader("All weather variables")
rows = []
for v in ["temperature", "humidity", "wind_speed", "precipitation"]:
    for des in (False, True):
        t = weather_correlation_test(ww, v, deseasonalize=des)
        rows.append({"variable": LABELS[v], "unit": UNITS[v], "series": "anomalies" if des else "raw",
                     "cities": t.n, "median_rho": t.effect_size,
                     "rho_ci_low": t.effect_ci[0] if t.effect_ci else None,
                     "rho_ci_high": t.effect_ci[1] if t.effect_ci else None,
                     "cities_significant_fdr": t.assumption_checks.get("n_significant_fdr"),
                     "positive": t.assumption_checks.get("n_positive"), "negative": t.assumption_checks.get("n_negative")})
tab = pd.DataFrame(rows)
st.dataframe(tab.round(3), hide_index=True)
download(tab, "weather_correlation_summary")
w = tab.pivot(index="variable", columns="series", values="median_rho")
flips = [v for v in w.index if w.loc[v, "raw"] * w.loc[v, "anomalies"] < 0]
flip_text = (f"In this selection the sign changes for <b>{', '.join(flips)}</b>: the raw association is driven by the "
             "shared seasonal cycle rather than by day-to-day variation. " if flips else
             "No variable changes sign between raw and anomaly correlations in this selection. ")
note(flip_text + "Meteorology, emissions (e.g. crop-residue burning, heating, traffic) and the PM2.5 model's own use "
     "of ERA5 inputs all confound these associations.", "caveat")
