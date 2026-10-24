import numpy as np
import pandas as pd
import streamlit as st
from statsmodels.stats.multitest import multipletests

from src.analysis.statistical_tests import results_table
from src.ui import cached
from src.ui.common import (chart, current_filters, download, filter_summary, filtered_wb, get, independent, note,
                           page_header, require_data)
from src.visualization import charts

page_header("Statistical Analysis", "Formal tests with the question, null hypothesis, unit of analysis, assumptions, "
            "test statistic, p-value, effect size and interpretation reported for each one.")

f = current_filters()
fk = cached.key(f)
wb = filtered_wb(f)
st.caption(f"Current selection: {filter_summary(f)}")
if not require_data(wb):
    st.stop()

cities = get("wb_cities")
iu = independent(wb)
note(f"<b>Independence.</b> Daily values from one city are serially correlated, so no test here treats days as "
     f"independent samples. Tests use one summary value per city (paired designs where the same cities are compared). "
     f"{wb['city_id'].nunique() - iu['city_id'].nunique()} places whose daily series is identical to another place's "
     f"(same model grid cell) are dropped, leaving <b>{iu['city_id'].nunique()}</b> distinct series. "
     "Nearby cities still share regional weather, so p-values remain somewhat optimistic.")

results = cached.test_battery(fk)
if not results:
    st.info("No tests could be run for this selection.")
    st.stop()
table = results_table(results)
ok = table["justified"] & table["p_value"].notna()
table["p_holm_family"] = np.nan
if ok.any():
    table.loc[ok, "p_holm_family"] = multipletests(table.loc[ok, "p_value"], method="holm")[1]

st.subheader("Results overview")
st.dataframe(table[["test", "unit", "n", "statistic", "p_value", "p_holm_family", "effect_size_name", "effect_size",
                    "effect_ci_low", "effect_ci_high", "justified"]],
             hide_index=True, column_config={
                 "p_value": st.column_config.NumberColumn("p", format="%.2e"),
                 "p_holm_family": st.column_config.NumberColumn("p (Holm, all tests)", format="%.2e",
                                                                help="Holm correction across this family of tests"),
                 "statistic": st.column_config.NumberColumn(format="%.3f"),
                 "effect_size": st.column_config.NumberColumn(format="%.3f"),
                 "effect_ci_low": st.column_config.NumberColumn("CI low", format="%.3f"),
                 "effect_ci_high": st.column_config.NumberColumn("CI high", format="%.3f")})
download(table, "statistical_test_results")
note("<b>Significance is not importance.</b> With hundreds of cities and years of data, very small differences can "
     "have tiny p-values. Judge each result by its effect size, its confidence interval and the µg/m³ difference "
     "it implies.", "caveat")

wx = table[table["test"].str.startswith("pm25 vs ")]
if len(wx):
    chart(charts.effect_size_chart(wx, title="Median within-city correlation with weather (deseasonalised)"),
          key="st_eff")

st.subheader("Test details")
for r in results:
    with st.expander(("✅ " if r.justified else "⚠️ ") + r.name, expanded=False):
        c1, c2 = st.columns([1.1, 1])
        with c1:
            st.markdown(f"**Question.** {r.question}")
            st.markdown(f"**Null hypothesis.** {r.null_hypothesis}")
            st.markdown(f"**Test.** {r.test} · **unit:** {r.unit_of_analysis} · **n = {r.n}**")
            st.markdown("**Assumptions.** " + "; ".join(r.assumptions))
            if r.assumption_checks:
                st.markdown("**Assumption checks / extra figures.**")
                st.json({k: (round(v, 4) if isinstance(v, float) else v) for k, v in r.assumption_checks.items()},
                        expanded=False)
        with c2:
            if r.justified:
                st.metric("Test statistic", f"{r.statistic:.3f}")
                st.metric("p-value", f"{r.p_value:.2e}")
                eff = f"{r.effect_size:.3f}" + (f" [{r.effect_ci[0]:.3f}, {r.effect_ci[1]:.3f}]" if r.effect_ci else "")
                st.metric(r.effect_size_name or "Effect size", eff)
        st.markdown(f"**Interpretation.** {r.interpretation}")
        for cav in r.caveats:
            st.caption("• " + cav)
        if r.details is not None and len(r.details):
            det = r.details.copy()
            if "city_id" in det.columns:
                det.insert(0, "city", det["city_id"].astype(str).map(dict(zip(cities["city_id"].astype(str),
                                                                               cities["city_label"].astype(str)))))
            st.dataframe(det.round(4), hide_index=True, height=260)

st.subheader("Sensitivity analysis")
note("Each scenario changes one data-handling rule and recomputes the same headline metrics, so differences are "
     "attributable to that rule.")
metrics, ranks = cached.sensitivity_tables(fk)
if len(metrics):
    st.dataframe(metrics.round(2), hide_index=True)
    download(metrics, "sensitivity_scenarios")
    chart(charts.sensitivity_ranks(ranks), key="st_sens")
