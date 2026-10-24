"""Pakistan Environmental Analytics — Streamlit entry point.

Run with:
    streamlit run app.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.ui.common import render_global_filters  # noqa: E402

st.set_page_config(page_title="Pakistan Environmental Analytics", page_icon=":material/air:", layout="wide",
                   initial_sidebar_state="expanded")

P = "pages/"
pages = {
    "Overview": [
        st.Page(P + "1_Executive_Overview.py", title="Executive Overview", icon=":material/dashboard:", default=True),
        st.Page(P + "2_Pakistan_City_Explorer.py", title="Pakistan City Explorer", icon=":material/location_city:"),
        st.Page(P + "3_City_Comparison.py", title="City Comparison", icon=":material/compare_arrows:"),
    ],
    "Analysis": [
        st.Page(P + "4_Historical_Trends.py", title="Historical Trends", icon=":material/trending_down:"),
        st.Page(P + "5_Seasonal_Analysis.py", title="Seasonal Analysis", icon=":material/calendar_month:"),
        st.Page(P + "6_Weather_Relationships.py", title="Weather & Pollution", icon=":material/thermostat:"),
        st.Page(P + "7_Pollutant_Distributions.py", title="Pollutant Distributions", icon=":material/bar_chart:"),
        st.Page(P + "8_Statistical_Analysis.py", title="Statistical Analysis", icon=":material/functions:"),
    ],
    "Data": [
        st.Page(P + "9_Data_Quality.py", title="Data Quality & Coverage", icon=":material/fact_check:"),
        st.Page(P + "10_Methodology_and_Sources.py", title="Methodology & Sources", icon=":material/menu_book:"),
    ],
}

nav = st.navigation(pages)
with st.sidebar:
    st.markdown("**Pakistan Environmental Analytics**")
    st.caption("Historical air quality, weather & statistical insights")
render_global_filters()
nav.run()
