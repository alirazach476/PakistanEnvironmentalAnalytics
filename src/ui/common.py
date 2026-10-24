"""Shared Streamlit helpers: cached data access, global filters, KPI cards, downloads.

Normal operation reads only local processed files; no network calls are made.
"""

from __future__ import annotations

import datetime as dt

import pandas as pd
import streamlit as st

from src.analysis.descriptive import real_only
from src.data import load
from src.data.transform import independent_units
from src.utils.config import SEASON_ORDER, SOURCES

CSS = """
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
  html, body, [class*="css"], .stMarkdown, .stDataFrame, button, input, select {font-family: Inter, system-ui, sans-serif;}
  .block-container {padding-top: 1.6rem; padding-bottom: 3rem; max-width: 1360px;}
  h1 {font-weight: 800; letter-spacing: -0.025em;}
  h2, h3 {font-weight: 700; letter-spacing: -0.015em;}
  .pea-header {border-radius: 20px; padding: 26px 30px 22px; margin-bottom: 18px; color: #fff; position: relative; overflow: hidden;
    background: radial-gradient(900px 300px at 90% -30%, rgba(31,179,138,.55), transparent 60%),
                linear-gradient(120deg, #0d3b78 0%, #1565c0 55%, #0f8b8d 100%);
    box-shadow: 0 10px 30px rgba(15,23,42,.12);}
  .pea-header h1 {color: #fff !important; font-size: 1.9rem; margin: 0 0 6px; padding: 0;}
  .pea-header .sub {color: rgba(255,255,255,.86); font-size: 1rem; max-width: 900px;}
  .pea-header .badges {margin-top: 12px;}
  .pea-header .pea-badge {background: rgba(255,255,255,.14); border-color: rgba(255,255,255,.25); color: #fff;}
  .pea-stats {display: flex; gap: 34px; flex-wrap: wrap; margin-top: 16px;}
  .pea-stats .v {font-size: 1.6rem; font-weight: 800; letter-spacing: -0.02em;}
  .pea-stats .l {font-size: .74rem; text-transform: uppercase; letter-spacing: .07em; color: rgba(255,255,255,.75);}
  .pea-badge {display:inline-block; padding:3px 11px; border-radius:999px; font-size:0.76rem; font-weight:600;
              margin-right:6px; border:1px solid rgba(15,23,42,0.12); background:#fff; color:#475569;}
  .pea-kpi {border:1px solid #e3e7ee; border-radius:16px; padding:16px 18px; background:#fff; height:100%;
            box-shadow: 0 1px 2px rgba(15,23,42,.04), 0 4px 16px rgba(15,23,42,.05); border-top: 3px solid #2a78d6;}
  .pea-kpi .label {font-size:0.76rem; color:#475569; text-transform:uppercase; letter-spacing:0.06em; font-weight:600;}
  .pea-kpi .value {font-size:1.6rem; font-weight:800; color:#0f172a; line-height:1.2; margin-top:6px; letter-spacing:-0.02em;}
  .pea-kpi .note {font-size:0.78rem; color:#8a94a6; margin-top:4px;}
  .pea-note {background:#e8f1fc; padding:12px 16px; border-radius:12px; color:#0f172a; font-size:0.92rem; margin:0.4rem 0 1rem 0;}
  .pea-caveat {background:#fff6e6; padding:12px 16px; border-radius:12px; color:#0f172a; font-size:0.92rem; margin:0.4rem 0 1rem 0;
               border-left: 4px solid #eda100;}
  div[data-testid="stPlotlyChart"] {background:#fff; border:1px solid #e3e7ee; border-radius:16px; padding:10px 10px 2px;
    box-shadow: 0 1px 2px rgba(15,23,42,.04), 0 4px 16px rgba(15,23,42,.05);}
  div[data-testid="stMetric"] {background:#fff; border-radius:16px; padding:14px 16px;}
  div[data-testid="stMetricValue"] {font-size: 1.55rem; font-weight: 800;}
  div[data-testid="stExpander"] {background:#fff; border-radius:14px;}
  section[data-testid="stSidebar"] .stCaption, section[data-testid="stSidebar"] small {color:#7f8ba3 !important;}
</style>
"""

MAX_CITY_SELECTION = 8


# ---------------------------------------------------------------------------
# Page scaffolding
# ---------------------------------------------------------------------------


def page_header(title: str, subtitle: str, badges: tuple[str, ...] = ("modelled",),
                stats: list[tuple[str, str]] | None = None) -> None:
    """Gradient page header with optional badges and headline stats [(value, label), ...]."""
    st.markdown(CSS, unsafe_allow_html=True)
    tags = "".join('<span class="pea-badge">Modelled estimates — not monitor measurements</span>' if b == "modelled"
                   else f'<span class="pea-badge">{b}</span>' for b in badges)
    stat_html = ("<div class='pea-stats'>" + "".join(f"<div><div class='v'>{v}</div><div class='l'>{l}</div></div>"
                                                     for v, l in stats) + "</div>") if stats else ""
    st.markdown(f'<div class="pea-header"><h1>{title}</h1><div class="sub">{subtitle}</div>'
                f'{"<div class=badges>" + tags + "</div>" if tags else ""}{stat_html}</div>', unsafe_allow_html=True)


def note(text: str, kind: str = "note") -> None:
    st.markdown(f'<div class="pea-{kind}">{text}</div>', unsafe_allow_html=True)


def kpi(label: str, value: str, note_text: str = "", help_text: str | None = None) -> None:
    st.markdown(f'<div class="pea-kpi" title="{help_text or ""}"><div class="label">{label}</div>'
                f'<div class="value">{value}</div><div class="note">{note_text}</div></div>', unsafe_allow_html=True)


def chart(fig, key: str | None = None) -> None:
    st.plotly_chart(fig, theme=None, key=key, config={"displaylogo": False, "toImageButtonOptions": {"scale": 2}})


def download(df: pd.DataFrame, name: str, label: str = "Download CSV", key: str | None = None) -> None:
    if df is None or df.empty:
        return
    st.download_button(label, df.to_csv(index=False).encode("utf-8"), file_name=f"{name}.csv", mime="text/csv",
                       key=key or f"dl_{name}", icon=":material/download:")


def table_with_download(df: pd.DataFrame, name: str, height: int | str = "auto", **kw) -> None:
    st.dataframe(df, hide_index=True, height=height, **kw)
    download(df, name)


def empty_state(message: str) -> None:
    st.info(message, icon=":material/filter_alt_off:")


def fmt(v, digits: int = 1, unit: str = "") -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "—"
    return f"{v:,.{digits}f}{(' ' + unit) if unit else ''}"


# ---------------------------------------------------------------------------
# Cached data access
# ---------------------------------------------------------------------------


@st.cache_data(show_spinner="Loading prepared datasets…")
def _load(name: str) -> pd.DataFrame:
    try:
        return real_only(load.load_processed(name))
    except load.DataNotPreparedError:
        if name in ("wb_daily", "wb_cities"):
            raise
        return pd.DataFrame()


def get(name: str) -> pd.DataFrame:
    try:
        return _load(name)
    except load.DataNotPreparedError as e:
        st.error(f"**Prepared data not found.** {e}\n\nFrom the project folder run:\n\n"
                 "```\npython scripts/prepare_data.py\n```", icon=":material/database:")
        st.stop()


@st.cache_data
def manifest() -> dict:
    try:
        return load.load_manifest()
    except load.DataNotPreparedError:
        return {}


@st.cache_data
def exclusions() -> pd.DataFrame:
    return load.load_exclusions()


def city_labels() -> dict[str, str]:
    c = get("wb_cities")
    return dict(zip(c["city_id"].astype(str), c["city_label"].astype(str)))


# ---------------------------------------------------------------------------
# Global filters (rendered once in app.py; persisted in session_state)
# ---------------------------------------------------------------------------


def data_bounds() -> tuple[dt.date, dt.date]:
    wb = get("wb_daily")
    return wb["date"].min().date(), wb["date"].max().date()


def render_global_filters() -> None:
    lo, hi = data_bounds()
    cities = get("wb_cities")
    with st.sidebar:
        st.markdown("### Filters")
        st.caption("Apply to every page (World Bank PM2.5 data).")
        st.date_input("Date range", value=(lo, hi), min_value=lo, max_value=hi, key="f_dates",
                      help="Inclusive. The World Bank series runs from the first to last date shown.")
        provinces = sorted(cities["province"].astype(str).unique())
        st.multiselect("Province", provinces, key="f_provinces", placeholder="All provinces",
                       help="Province labels are derived from the source's ADM1 codes (see Methodology).")
        st.multiselect("Season", SEASON_ORDER, key="f_seasons", placeholder="All seasons",
                       help="Winter Dec–Feb · Spring Mar–Apr · Pre-monsoon May–Jun · Monsoon Jul–Sep · Post-monsoon Oct–Nov")
        st.toggle("Exclude flagged outliers", key="f_no_outliers",
                  help="Robust z-score > 3.5 on log PM2.5 within each city. Flagged values are kept by default.")
        n_art = int(cities["artifact_flag"].sum()) if "artifact_flag" in cities.columns else 0
        st.toggle(f"Exclude model-artifact cities ({n_art})", key="f_no_artifacts",
                  help="Places whose modelled series shows a fixed annual mean across ≥ 3 years or an abrupt level "
                       "shift (see Data Quality). Kept by default.")
        st.divider()
        m = manifest()
        if m:
            st.caption(f"Data prepared {m.get('generated_utc', '?')[:10]} · sources: "
                       f"{', '.join(SOURCES[s]['short'].split(' (')[0] for s in m.get('inputs', {}))}")


def current_filters() -> dict:
    lo, hi = data_bounds()
    d = st.session_state.get("f_dates", (lo, hi))
    if not isinstance(d, (tuple, list)) or len(d) != 2:
        d = (d[0], d[0]) if isinstance(d, (tuple, list)) and d else (lo, hi)
    return {"start": pd.Timestamp(d[0]), "end": pd.Timestamp(d[1]),
            "provinces": tuple(st.session_state.get("f_provinces", []) or []),
            "seasons": tuple(st.session_state.get("f_seasons", []) or []),
            "no_outliers": bool(st.session_state.get("f_no_outliers", False)),
            "no_artifacts": bool(st.session_state.get("f_no_artifacts", False))}


def filter_summary(f: dict) -> str:
    parts = [f"{f['start']:%d %b %Y} – {f['end']:%d %b %Y}"]
    parts.append(", ".join(f["provinces"]) if f["provinces"] else "all provinces")
    parts.append(", ".join(f["seasons"]) if f["seasons"] else "all seasons")
    if f["no_outliers"]:
        parts.append("outliers excluded")
    if f.get("no_artifacts"):
        parts.append("model-artifact cities excluded")
    return " · ".join(parts)


@st.cache_data(show_spinner=False, max_entries=16)
def _filtered(table: str, start, end, provinces: tuple, seasons: tuple, no_outliers: bool,
              no_artifacts: bool = False) -> pd.DataFrame:
    df = _load(table)
    if df.empty:
        return df
    m = (df["date"] >= start) & (df["date"] <= end)
    if provinces and "province" in df.columns:
        m &= df["province"].astype(str).isin(provinces)
    if seasons and "season" in df.columns:
        m &= df["season"].astype(str).isin(seasons)
    if no_outliers and "is_outlier" in df.columns:
        m &= ~df["is_outlier"].astype(bool)
    if no_artifacts:
        c = _load("wb_cities")
        if "artifact_flag" in c.columns:
            m &= ~df["city_id"].astype(str).isin(set(c.loc[c["artifact_flag"], "city_id"].astype(str)))
    out = df.loc[m]
    for c in ("city_id", "city_label", "province"):
        if c in out.columns and isinstance(out[c].dtype, pd.CategoricalDtype):
            out = out.assign(**{c: out[c].cat.remove_unused_categories()})
    return out


def filtered_wb(f: dict | None = None) -> pd.DataFrame:
    f = f or current_filters()
    get("wb_daily")
    return _filtered("wb_daily", f["start"], f["end"], f["provinces"], f["seasons"], f["no_outliers"],
                     f.get("no_artifacts", False))


def filtered_wb_weather(f: dict | None = None) -> pd.DataFrame:
    f = f or current_filters()
    return _filtered("wb_weather_daily", f["start"], f["end"], f["provinces"], f["seasons"], False,
                     f.get("no_artifacts", False))


def independent(df: pd.DataFrame) -> pd.DataFrame:
    return independent_units(df, get("wb_cities"))


def city_picker(df: pd.DataFrame, key: str, default_n: int = 4, label: str = "Cities",
                max_n: int = MAX_CITY_SELECTION, defaults: list[str] | None = None) -> list[str]:
    """Multiselect of city labels present in ``df`` (default: the most populous)."""
    options = (df.drop_duplicates("city_label").sort_values("population", ascending=False)["city_label"].astype(str).tolist()
               if "population" in df.columns else sorted(df["city_label"].astype(str).unique()))
    if not options:
        return []
    default = [c for c in (defaults or options[:default_n]) if c in options][:max_n]
    sel = st.multiselect(label, options, default=default, key=key, max_selections=max_n,
                         help=f"Up to {max_n} cities (one colour each). Ordered by population.")
    return sel


def require_data(df: pd.DataFrame, message: str = "No data match the current filters. Widen the date range or "
                                                   "clear the province/season filters in the sidebar.") -> bool:
    if df is None or df.empty:
        empty_state(message)
        return False
    return True
