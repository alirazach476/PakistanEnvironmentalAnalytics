import json

import pandas as pd
import streamlit as st

from src.ui.common import manifest, note, page_header
from src.utils.config import SOURCES
from src.utils.paths import DOCS_DIR

page_header("Methodology & Data Sources", "Where the data come from, how they were prepared, and the rules behind "
            "every statistic in this dashboard.", badges=())

st.subheader("Sources")
rows = [{"source": v["name"], "value type": v["value_type"], "resolution": v["resolution"], "licence": v["license"],
         "link": v["url"]} for v in SOURCES.values()]
st.dataframe(pd.DataFrame(rows), hide_index=True, column_config={"link": st.column_config.LinkColumn()})
note("<b>No measured (monitor) data are included.</b> All three sources are model or reanalysis products. The "
     "World Bank and Kaggle/HF PM2.5 series are analysed separately and compared only on overlapping city-days; "
     "they are never averaged together. No synthetic data are used in any result.")

tabs = st.tabs(["Methodology", "Data sources & licences", "Data dictionary", "Pipeline manifest"])
for tab, fname in zip(tabs[:3], ["methodology.md", "data_sources.md", "data_dictionary.md"]):
    with tab:
        p = DOCS_DIR / fname
        if p.exists():
            st.markdown(p.read_text(encoding="utf-8"))
        else:
            st.warning(f"{fname} not found in docs/.")
with tabs[3]:
    m = manifest()
    if m:
        st.caption("Written by `python scripts/prepare_data.py`; input hashes identify the exact raw files used.")
        st.code(json.dumps(m, indent=2), language="json")
    else:
        st.warning("No manifest found — run the data preparation pipeline.")
