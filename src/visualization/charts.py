"""Plotly chart library. Every function takes already-computed analysis tables and
returns a figure with a title, unit-labelled axes, a source subtitle and hover details.
Charts show an explained empty state rather than a misleading blank plot."""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from src.utils.config import LABELS, MONTH_NAMES, SEASON_ORDER, UNITS, WHO_PM25_24H
from src.visualization.themes import (ACCENT, CATEGORICAL, DIVERGING_SCALE, INK_SECONDARY, MAX_CATEGORICAL,
                                      MUTED_MARK, PRIMARY, REFERENCE, SEASON_COLORS, SEQUENTIAL_SCALE, SURFACE,
                                      color_map, empty_figure, finalize)

WB_SRC = "Source: World Bank Global PM2.5 Watch — modelled daily estimates"
HF_SRC = "Source: Kaggle/HF hourly dataset — modelled (probable CAMS), licence unknown"
WX_SRC = "PM2.5: World Bank (modelled) · Weather: Open-Meteo ERA5 reanalysis"
PM = "PM2.5 (µg/m³)"


def _label(var: str) -> str:
    return f"{LABELS.get(var, var)} ({UNITS[var]})" if var in UNITS else LABELS.get(var, var)


def _who_line(fig: go.Figure, axis: str = "y", **kw) -> None:
    if axis == "y":
        fig.add_hline(y=WHO_PM25_24H, line=dict(color=REFERENCE, width=1, dash="dot"),
                      annotation_text=f"WHO 24-h guideline {WHO_PM25_24H:g} µg/m³", annotation_position="top left",
                      annotation_font=dict(size=11, color=INK_SECONDARY), **kw)
    else:
        # Label goes in the subtitle (WHO_NOTE) so it never collides with bars or dots.
        fig.add_vline(x=WHO_PM25_24H, line=dict(color=REFERENCE, width=1, dash="dot"), **kw)


WHO_NOTE = f" · dotted line = WHO 24-h guideline ({WHO_PM25_24H:g} µg/m³)"


def _box_stats(v: pd.Series) -> dict:
    """Tukey box statistics (whiskers at the most extreme points within 1.5×IQR)."""
    q1, med, q3 = v.quantile([0.25, 0.5, 0.75])
    iqr = q3 - q1
    lo, hi = v[v >= q1 - 1.5 * iqr].min(), v[v <= q3 + 1.5 * iqr].max()
    return {"q1": [q1], "median": [med], "q3": [q3], "lowerfence": [lo], "upperfence": [hi], "mean": [v.mean()]}


# ===========================================================================
# Rankings & comparisons
# ===========================================================================


def city_ranking_bar(summary: pd.DataFrame, metric: str = "median", n: int = 20, ascending: bool = False,
                     title: str | None = None, subtitle: str = WB_SRC) -> go.Figure:
    d = summary.dropna(subset=[metric]).sort_values(metric, ascending=ascending).head(n)
    title = title or f"{'Lowest' if ascending else 'Highest'} {len(d)} cities by {metric} PM2.5"
    if d.empty:
        return empty_figure("No cities match the current filters.", title)
    d = d.iloc[::-1]
    fig = go.Figure(go.Bar(
        x=d[metric], y=d["city_label"], orientation="h", marker=dict(color=PRIMARY, cornerradius=4),
        customdata=np.stack([d.get("n", d[metric] * np.nan), d.get("province", pd.Series([""] * len(d))).astype(str)], -1),
        hovertemplate="<b>%{y}</b> · %{customdata[1]}<br>" + metric.title() + ": %{x:.1f} µg/m³<br>"
                      "Days: %{customdata[0]:,}<extra></extra>"))
    _who_line(fig, "x")
    fig.update_xaxes(title=f"{metric.title()} {PM}", showgrid=True, gridcolor="#e1e0d9")
    fig.update_yaxes(title="", gridcolor="rgba(0,0,0,0)")
    return finalize(fig, title, subtitle + WHO_NOTE, height=max(360, 22 * len(d) + 140), legend=False)


def city_interval_dots(summary: pd.DataFrame, title: str = "Median and spread of daily PM2.5 by city",
                       subtitle: str = WB_SRC) -> go.Figure:
    """Dot = median, bar = p5–p95 range: compares level and variability at once."""
    need = {"median", "p5", "p95"}
    if summary.empty or not need <= set(summary.columns):
        return empty_figure("Select at least one city.", title)
    d = summary.sort_values("median")
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=d["p95"], y=d["city_label"], mode="markers", marker=dict(size=0.1, color=SURFACE),
                             error_x=dict(type="data", symmetric=False, array=np.zeros(len(d)),
                                          arrayminus=d["p95"] - d["p5"], color=MUTED_MARK, thickness=3, width=0),
                             hoverinfo="skip", showlegend=False))
    fig.add_trace(go.Scatter(x=d["median"], y=d["city_label"], mode="markers", name="Median",
                             marker=dict(size=11, color=PRIMARY, line=dict(width=2, color=SURFACE)),
                             customdata=np.stack([d["p5"], d["p95"], d["n"]], -1),
                             hovertemplate="<b>%{y}</b><br>Median %{x:.1f} µg/m³<br>5th–95th pct: %{customdata[0]:.1f}"
                                           "–%{customdata[1]:.1f}<br>n = %{customdata[2]:,} days<extra></extra>"))
    _who_line(fig, "x")
    fig.update_xaxes(title=PM, showgrid=True, gridcolor="#e1e0d9")
    return finalize(fig, title, subtitle + " · bar = 5th–95th percentile" + WHO_NOTE, height=max(320, 30 * len(d) + 140),
                    legend=False)


def province_box(city_level: pd.DataFrame, value: str = "median",
                 title: str = "City medians by province", subtitle: str = WB_SRC) -> go.Figure:
    if city_level.empty:
        return empty_figure("No data for the selected filters.", title)
    order = city_level.groupby("province", observed=True)[value].median().sort_values(ascending=False).index
    fig = go.Figure()
    for p in order:
        d = city_level[city_level["province"] == p]
        fig.add_trace(go.Box(y=d[value], name=f"{p.replace(' Capital Territory', ' CT')}<br>(n={len(d)})", boxpoints="all", jitter=0.4, pointpos=0,
                             marker=dict(size=5, color=PRIMARY, opacity=0.55), line=dict(color=INK_SECONDARY, width=1),
                             fillcolor="rgba(0,0,0,0)", text=d["city_label"],
                             hovertemplate="<b>%{text}</b><br>%{y:.1f} µg/m³<extra></extra>"))
    fig.update_yaxes(title=f"City median {PM}")
    return finalize(fig, title, subtitle + " · one point per city; province from source ADM1 codes", legend=False)


# ===========================================================================
# Time series
# ===========================================================================


def multi_city_lines(df: pd.DataFrame, x: str, y: str, city_col: str = "city_label", title: str = "",
                     subtitle: str = WB_SRC, y_title: str = PM, colors: dict | None = None,
                     who_line: bool = True, height: int = 440) -> go.Figure:
    if df.empty:
        return empty_figure("No data for the selected cities and dates.", title)
    cities = list(dict.fromkeys(df[city_col].astype(str)))
    colors = colors or color_map(cities)
    fig = go.Figure()
    for c in cities[:MAX_CATEGORICAL]:
        d = df[df[city_col].astype(str) == c].sort_values(x)
        fig.add_trace(go.Scatter(x=d[x], y=d[y], mode="lines", name=c, line=dict(width=2, color=colors.get(c)),
                                 connectgaps=False,
                                 hovertemplate=f"<b>{c}</b><br>%{{x|%d %b %Y}}<br>%{{y:.1f}}<extra></extra>"))
    if who_line:
        _who_line(fig)
    fig.update_layout(hovermode="x unified")
    fig.update_yaxes(title=y_title, rangemode="tozero")
    fig.update_xaxes(title="")
    return finalize(fig, title, subtitle, height=height)


def national_band(monthly: pd.DataFrame, title: str = "Monthly PM2.5 across all cities",
                  subtitle: str = WB_SRC) -> go.Figure:
    """Median of city monthly means with inter-quartile and 5–95 % bands."""
    if monthly.empty:
        return empty_figure("No monthly data.", title)
    g = monthly.groupby("period")["mean"].quantile([0.05, 0.25, 0.5, 0.75, 0.95]).unstack()
    n = monthly.groupby("period")["mean"].size()
    fig = go.Figure()
    for lo, hi, alpha, name in ((0.05, 0.95, 0.15, "5–95 % of cities"), (0.25, 0.75, 0.3, "Middle 50 % of cities")):
        fig.add_trace(go.Scatter(x=g.index, y=g[hi], mode="lines", line=dict(width=0), showlegend=False, hoverinfo="skip"))
        fig.add_trace(go.Scatter(x=g.index, y=g[lo], mode="lines", line=dict(width=0), fill="tonexty",
                                 fillcolor=f"rgba(42,120,214,{alpha})", name=name, hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=g.index, y=g[0.5], mode="lines", name="Median city", line=dict(color=PRIMARY, width=2),
                             customdata=np.stack([g[0.25], g[0.75], n.reindex(g.index)], -1),
                             hovertemplate="%{x|%b %Y}<br>Median %{y:.1f} µg/m³<br>IQR %{customdata[0]:.1f}–"
                                           "%{customdata[1]:.1f}<br>%{customdata[2]} cities<extra></extra>"))
    _who_line(fig)
    fig.update_yaxes(title=f"Monthly mean {PM}", rangemode="tozero")
    fig.update_layout(hovermode="x unified")
    return finalize(fig, title, subtitle + " · months with ≥ 20 valid days only")


def annual_lines(annual: pd.DataFrame, city_col: str = "city_label", title: str = "Annual mean PM2.5 (complete years)",
                 subtitle: str = WB_SRC, colors: dict | None = None) -> go.Figure:
    if annual.empty:
        return empty_figure("No complete calendar years for this selection.", title)
    fig = multi_city_lines(annual.assign(year_dt=pd.to_datetime(annual["year"].astype(str))), "year_dt", "mean",
                           city_col, title, subtitle + " · years with ≥ 11 complete months", y_title=f"Annual mean {PM}",
                           colors=colors)
    fig.update_traces(mode="lines+markers", marker=dict(size=8, line=dict(width=2, color=SURFACE)),
                      hovertemplate="%{x|%Y}: %{y:.1f} µg/m³")
    fig.update_xaxes(dtick="M12", tickformat="%Y")
    return fig


def yoy_heatmap(yoy: pd.DataFrame, city_col: str = "city_label", title: str = "Year-over-year change in annual mean",
                subtitle: str = WB_SRC) -> go.Figure:
    d = yoy.dropna(subset=["pct_change"])
    if d.empty:
        return empty_figure("Year-over-year change needs two consecutive complete years.", title)
    m = d.pivot_table(index=city_col, columns="year", values="pct_change", observed=True)
    lim = float(np.nanmax(np.abs(m.to_numpy()))) or 1
    fig = go.Figure(go.Heatmap(z=m.to_numpy(), x=[str(c) for c in m.columns], y=m.index, colorscale=DIVERGING_SCALE,
                               zmin=-lim, zmax=lim, xgap=2, ygap=2, colorbar=dict(title="% change"),
                               hovertemplate="<b>%{y}</b> %{x} vs previous year<br>%{z:+.1f} %<extra></extra>"))
    fig.update_yaxes(autorange="reversed", showgrid=False)
    return finalize(fig, title, subtitle + " · blue = decrease, red = increase", height=max(320, 26 * len(m) + 140),
                    legend=False)


def trend_chart(monthly_anom: pd.DataFrame, fit: pd.DataFrame, trend: dict, label: str,
                subtitle: str = WB_SRC) -> go.Figure:
    title = f"Deseasonalised monthly PM2.5 anomaly — {label}"
    if monthly_anom.empty:
        return empty_figure("Not enough complete months for a trend.", title)
    fig = go.Figure()
    fig.add_trace(go.Bar(x=monthly_anom["period"], y=monthly_anom["anomaly"], name="Monthly anomaly",
                         marker=dict(color=np.where(monthly_anom["anomaly"] >= 0, "#ec8a89", "#6da7ec")),
                         hovertemplate="%{x|%b %Y}: %{y:+.1f} µg/m³ vs typical month<extra></extra>"))
    if not fit.empty:
        fig.add_trace(go.Scatter(x=fit["period"], y=fit["upper"], mode="lines", line=dict(width=0), showlegend=False,
                                 hoverinfo="skip"))
        fig.add_trace(go.Scatter(x=fit["period"], y=fit["lower"], mode="lines", line=dict(width=0), fill="tonexty",
                                 fillcolor="rgba(11,11,11,0.10)", name="95 % CI (Newey–West)", hoverinfo="skip"))
        fig.add_trace(go.Scatter(x=fit["period"], y=fit["fit"], mode="lines", name="Linear trend",
                                 line=dict(color="#0b0b0b", width=2), hovertemplate="Trend %{y:+.1f}<extra></extra>"))
    s = trend
    sub = (f"{subtitle} · slope {s['slope_per_year']:+.2f} µg/m³/yr (95 % CI {s['ci_low']:+.2f} to {s['ci_high']:+.2f}); "
           f"Theil–Sen {s['theil_sen_slope']:+.2f}; n = {s['n']} months") if np.isfinite(s.get("slope_per_year", np.nan)) else subtitle
    fig.update_yaxes(title="Anomaly (µg/m³)", zeroline=True, zerolinecolor="#c3c2b7")
    fig.update_layout(bargap=0.1)
    return finalize(fig, title, sub)


def trend_forest(trends: pd.DataFrame, n: int = 15, label_col: str = "city_label",
                 title: str = "Cities with the largest estimated trends", subtitle: str = WB_SRC) -> go.Figure:
    d = trends.dropna(subset=["slope_per_year"])
    if d.empty:
        return empty_figure("No trend estimates for this selection.", title)
    d = pd.concat([d.nsmallest(n, "slope_per_year"), d.nlargest(n, "slope_per_year")]).drop_duplicates("city_id")
    d = d.sort_values("slope_per_year")
    col = np.where(d["direction"] == "decreasing", CATEGORICAL[0], np.where(d["direction"] == "increasing",
                                                                           CATEGORICAL[7], MUTED_MARK))
    fig = go.Figure(go.Scatter(
        x=d["slope_per_year"], y=d[label_col], mode="markers",
        marker=dict(size=9, color=col, line=dict(width=2, color=SURFACE)),
        error_x=dict(type="data", symmetric=False, array=d["ci_high"] - d["slope_per_year"],
                     arrayminus=d["slope_per_year"] - d["ci_low"], color="#a9a8a0", thickness=1.5, width=0),
        customdata=np.stack([d["ci_low"], d["ci_high"], d["q_value"], d["direction"], d["pct_change_per_year"]], -1),
        hovertemplate="<b>%{y}</b><br>%{x:+.2f} µg/m³/yr (%{customdata[4]:+.1f} %/yr)<br>95% CI %{customdata[0]:+.2f} "
                      "to %{customdata[1]:+.2f}<br>q = %{customdata[2]:.3g} · %{customdata[3]}<extra></extra>"))
    fig.add_vline(x=0, line=dict(color="#c3c2b7", width=1))
    fig.update_xaxes(title="Trend (µg/m³ per year), 95 % Newey–West CI", showgrid=True, gridcolor="#e1e0d9")
    return finalize(fig, title, subtitle + " · blue = decreasing, red = increasing, grey = no clear trend (BH-FDR)",
                    height=max(380, 20 * len(d) + 140), legend=False)


def calendar_heatmap(daily_city: pd.DataFrame, label: str, subtitle: str = WB_SRC) -> go.Figure:
    """Year × month monthly-mean grid for one city."""
    title = f"Monthly mean PM2.5 by year — {label}"
    if daily_city.empty:
        return empty_figure("No data for this city.", title)
    m = daily_city.groupby(["year", "month"])["pm25"].mean().unstack("month").reindex(columns=range(1, 13))
    n = daily_city.groupby(["year", "month"])["pm25"].count().unstack("month").reindex(columns=range(1, 13))
    fig = go.Figure(go.Heatmap(z=m.to_numpy(), x=MONTH_NAMES, y=[str(y) for y in m.index], colorscale=SEQUENTIAL_SCALE,
                               customdata=n.to_numpy(), xgap=2, ygap=2, colorbar=dict(title="µg/m³"),
                               hovertemplate="%{x} %{y}: %{z:.1f} µg/m³<br>%{customdata} days<extra></extra>"))
    fig.update_yaxes(autorange="reversed", type="category", showgrid=False)
    return finalize(fig, title, subtitle + " · blank = month outside data range", legend=False)


# ===========================================================================
# Seasonal
# ===========================================================================


def month_city_heatmap(matrix: pd.DataFrame, title: str = "Median PM2.5 by month and city",
                       subtitle: str = WB_SRC) -> go.Figure:
    if matrix.empty:
        return empty_figure("No cities selected.", title)
    fig = go.Figure(go.Heatmap(z=matrix.to_numpy(), x=list(matrix.columns), y=list(matrix.index),
                               colorscale=SEQUENTIAL_SCALE, xgap=2, ygap=2, colorbar=dict(title="µg/m³"),
                               hovertemplate="<b>%{y}</b> · %{x}<br>Median %{z:.1f} µg/m³<extra></extra>"))
    fig.update_yaxes(autorange="reversed", showgrid=False)
    return finalize(fig, title, subtitle + " · median of all daily values in that calendar month",
                    height=max(340, 22 * len(matrix) + 150), legend=False)


def season_box(df: pd.DataFrame, value: str = "pm25", title: str = "Distribution of daily PM2.5 by season",
               subtitle: str = WB_SRC, max_points: int = 60000) -> go.Figure:
    if df.empty:
        return empty_figure("No data for the selected filters.", title)
    fig = go.Figure()
    for s in SEASON_ORDER:
        d = df.loc[df["season"].astype(str) == s, value].dropna()
        if d.empty:
            continue
        fig.add_trace(go.Box(x=[f"{s}<br>(n={len(d):,})"], **_box_stats(d), name=s, marker_color=SEASON_COLORS[s],
                             line=dict(width=1.5), fillcolor="rgba(0,0,0,0)", boxmean=True))
    _who_line(fig)
    fig.update_yaxes(title=f"Daily {PM}", rangemode="tozero")
    return finalize(fig, title, subtitle + " · box = IQR, line = median, dashed = mean, whiskers = most extreme "
                    "values within 1.5×IQR (more extreme days not drawn)", legend=False)


def month_profile_chart(profile: pd.DataFrame, by: str | None = "city_label", title: str = "Month-of-year profile",
                        subtitle: str = WB_SRC, colors: dict | None = None) -> go.Figure:
    if profile.empty:
        return empty_figure("No data for the selected filters.", title)
    fig = go.Figure()
    groups = [(None, profile)] if by is None else list(profile.groupby(by, observed=True, sort=False))
    colors = colors or color_map([g for g, _ in groups if g is not None])
    for i, (g, d) in enumerate(groups[:MAX_CATEGORICAL]):
        d = d.sort_values("month")
        c = PRIMARY if g is None else colors.get(str(g), CATEGORICAL[i])
        name = "All selected cities" if g is None else str(g)
        if len(groups) == 1:
            fig.add_trace(go.Scatter(x=d["month_name"], y=d["p75"], mode="lines", line=dict(width=0),
                                     showlegend=False, hoverinfo="skip"))
            fig.add_trace(go.Scatter(x=d["month_name"], y=d["p25"], mode="lines", line=dict(width=0), fill="tonexty",
                                     fillcolor="rgba(42,120,214,0.18)", name="Inter-quartile range", hoverinfo="skip"))
        fig.add_trace(go.Scatter(x=d["month_name"], y=d["median"], mode="lines+markers", name=name,
                                 line=dict(width=2, color=c), marker=dict(size=8, line=dict(width=2, color=SURFACE)),
                                 customdata=np.stack([d["p25"], d["p75"], d["n"]], -1),
                                 hovertemplate=f"<b>{name}</b> %{{x}}<br>Median %{{y:.1f}} µg/m³<br>IQR %{{customdata[0]:.1f}}–"
                                               "%{customdata[1]:.1f}<br>n = %{customdata[2]:,}<extra></extra>"))
    _who_line(fig)
    fig.update_yaxes(title=f"Median daily {PM}", rangemode="tozero")
    fig.update_xaxes(categoryorder="array", categoryarray=MONTH_NAMES)
    return finalize(fig, title, subtitle)


def weekday_chart(profile: pd.DataFrame, title: str = "Mean PM2.5 by day of week", subtitle: str = WB_SRC) -> go.Figure:
    if profile.empty:
        return empty_figure("No data for the selected filters.", title)
    d = profile.sort_values("day_of_week")
    weekend = d["day_of_week"].astype(str).isin(["Saturday", "Sunday"])
    fig = go.Figure(go.Bar(x=d["day_of_week"].astype(str), y=d["mean"],
                           marker=dict(color=np.where(weekend, ACCENT, PRIMARY), cornerradius=4),
                           customdata=d["n"], hovertemplate="%{x}: %{y:.2f} µg/m³<br>n = %{customdata:,}<extra></extra>"))
    lo = float(d["mean"].min())
    fig.update_yaxes(title=f"Mean {PM}", range=[0, float(d["mean"].max()) * 1.08])
    return finalize(fig, title, subtitle + f" · orange = weekend (Sat/Sun) · range of means {lo:.1f}–"
                    f"{float(d['mean'].max()):.1f} µg/m³", legend=False)


def hour_profile_chart(profile: pd.DataFrame, by: str | None = "city", title: str = "Hour-of-day PM2.5 profile",
                       subtitle: str = HF_SRC, colors: dict | None = None) -> go.Figure:
    if profile.empty:
        return empty_figure("Hour-of-day profiles need genuinely hourly data.", title)
    groups = [(None, profile)] if by is None else list(profile.groupby(by, observed=True))
    colors = colors or color_map([g for g, _ in groups if g is not None])
    fig = go.Figure()
    for i, (g, d) in enumerate(groups[:MAX_CATEGORICAL]):
        name = "All cities" if g is None else str(g)
        fig.add_trace(go.Scatter(x=d["hour"], y=d["mean"], mode="lines", name=name,
                                 line=dict(width=2, color=PRIMARY if g is None else colors.get(str(g))),
                                 hovertemplate=f"<b>{name}</b> hour %{{x}}<br>Mean %{{y:.1f}}<extra></extra>"))
    fig.update_xaxes(title="Hour label in source file (pollutants appear to be UTC; PKT = UTC+5)", dtick=3)
    fig.update_yaxes(title=f"Mean {PM}", rangemode="tozero")
    fig.update_layout(hovermode="x unified")
    return finalize(fig, title, subtitle)


# ===========================================================================
# Distributions
# ===========================================================================


def histogram(df: pd.DataFrame, value: str = "pm25", log_x: bool = False, title: str = "Distribution of daily PM2.5",
              subtitle: str = WB_SRC, nbins: int = 80, unit_name: str = "city-days") -> go.Figure:
    """Histogram binned in NumPy (only bin counts reach the browser, not every value).

    With ``log_x`` the bins are equal-width in log10 space and ticks are labelled in µg/m³.
    """
    v = df[value].dropna().to_numpy(dtype=float)
    if v.size == 0:
        return empty_figure("No values to plot.", title)
    x = np.log10(v[v > 0]) if log_x else v
    counts, edges = np.histogram(x, bins=nbins)
    lo, hi = (10 ** edges[:-1], 10 ** edges[1:]) if log_x else (edges[:-1], edges[1:])
    fig = go.Figure(go.Bar(x=(edges[:-1] + edges[1:]) / 2, y=counts, width=np.diff(edges) * 0.92,
                           marker=dict(color=PRIMARY), customdata=np.stack([lo, hi], -1),
                           hovertemplate="%{customdata[0]:.1f}–%{customdata[1]:.1f}<br>%{y:,} " + unit_name +
                                         "<extra></extra>"))
    med = float(np.median(v))
    fig.add_vline(x=np.log10(med) if log_x else med, line=dict(color="#0b0b0b", width=1.5),
                  annotation_text=f"median {med:.1f}", annotation_position="top right")
    if log_x:
        ticks = [t for t in (1, 2, 5, 10, 20, 50, 100, 200, 500, 1000, 2000, 5000) if lo[0] <= t <= hi[-1]]
        fig.update_xaxes(tickvals=np.log10(ticks), ticktext=[str(t) for t in ticks])
    fig.update_xaxes(title=_label(value) + (" — log scale" if log_x else ""))
    fig.update_yaxes(title=f"Number of {unit_name}")
    fig.update_layout(bargap=0)
    return finalize(fig, title, subtitle + f" · n = {v.size:,}", legend=False)


def ecdf_chart(df: pd.DataFrame, value: str = "pm25", by: str = "city_label", title: str = "Cumulative distribution by city",
               subtitle: str = WB_SRC, colors: dict | None = None) -> go.Figure:
    if df.empty:
        return empty_figure("No data for the selected filters.", title)
    groups = list(df.groupby(by, observed=True))
    colors = colors or color_map([g for g, _ in groups])
    fig = go.Figure()
    for g, d in groups[:MAX_CATEGORICAL]:
        v = np.sort(d[value].dropna().to_numpy())
        if v.size == 0:
            continue
        idx = np.unique(np.linspace(0, v.size - 1, min(v.size, 400)).astype(int))
        fig.add_trace(go.Scatter(x=v[idx], y=(idx + 1) / v.size * 100, mode="lines", name=str(g),
                                 line=dict(width=2, color=colors.get(str(g))),
                                 hovertemplate=f"<b>{g}</b><br>%{{y:.0f}} % of days ≤ %{{x:.1f}} µg/m³<extra></extra>"))
    _who_line(fig, "x")
    fig.update_xaxes(title=_label(value))
    fig.update_yaxes(title="Share of days at or below (%)", range=[0, 100])
    return finalize(fig, title, subtitle + WHO_NOTE)


def box_violin(df: pd.DataFrame, value: str = "pm25", by: str = "city_label", kind: str = "box",
               title: str | None = None, subtitle: str = WB_SRC, colors: dict | None = None) -> go.Figure:
    title = title or f"Daily PM2.5 distribution by city ({kind} plot)"
    if df.empty:
        return empty_figure("No data for the selected filters.", title)
    order = df.groupby(by, observed=True)[value].median().sort_values(ascending=False).index
    colors = colors or color_map(order)
    fig = go.Figure()
    for g in list(order)[:MAX_CATEGORICAL * 2]:
        v = df.loc[df[by] == g, value].dropna()
        c = colors.get(str(g), PRIMARY)
        if kind == "violin":
            fig.add_trace(go.Violin(y=v, name=str(g), line=dict(color=c, width=1.5), fillcolor="rgba(0,0,0,0)",
                                    meanline_visible=True, box_visible=True, points=False, spanmode="hard",
                                    hoverinfo="y"))
        else:
            fig.add_trace(go.Box(y=v, name=str(g), marker=dict(color=c, size=3, opacity=0.35), line=dict(color=c, width=1.5),
                                 fillcolor="rgba(0,0,0,0)", boxpoints="outliers", hoverinfo="y"))
    _who_line(fig)
    fig.update_yaxes(title=f"Daily {PM}", rangemode="tozero")
    return finalize(fig, title, subtitle + (" · outlier points beyond 1.5×IQR" if kind == "box" else ""), legend=False)


def percentile_chart(pct: pd.DataFrame, by: str = "city_label", title: str = "Percentile comparison",
                     subtitle: str = WB_SRC) -> go.Figure:
    cols = [c for c in pct.columns if c.startswith("p") and c[1:].isdigit()]
    if pct.empty or not cols:
        return empty_figure("No data for the selected filters.", title)
    d = pct.sort_values("p50")
    ramp = ["#9ec5f4", "#6da7ec", "#256abf", "#0d366b", "#6da7ec", "#9ec5f4"]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=pd.concat([d[cols[0]], d[cols[-1]]]), y=pd.concat([d[by], d[by]]), mode="markers",
                             marker=dict(size=0.1), hoverinfo="skip", showlegend=False))
    for i, c in enumerate(cols):
        sym = "diamond" if c == "p50" else "circle"
        fig.add_trace(go.Scatter(x=d[c], y=d[by], mode="markers", name=c.replace("p", "P"),
                                 marker=dict(size=11 if c == "p50" else 8, symbol=sym,
                                             color="#0b0b0b" if c == "p50" else ramp[min(i, len(ramp) - 1)],
                                             line=dict(width=1.5, color=SURFACE)),
                                 hovertemplate="<b>%{y}</b><br>" + c.upper() + ": %{x:.1f} µg/m³<extra></extra>"))
    _who_line(fig, "x")
    fig.update_xaxes(title=PM, showgrid=True, gridcolor="#e1e0d9")
    return finalize(fig, title, subtitle + WHO_NOTE, height=max(340, 28 * len(d) + 150))


def outlier_timeline(df: pd.DataFrame, label: str, title: str | None = None, subtitle: str = WB_SRC) -> go.Figure:
    title = title or f"Daily PM2.5 with flagged outliers — {label}"
    if df.empty:
        return empty_figure("No data for this city.", title)
    d = df.sort_values("date")
    o = d[d["is_outlier"]]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=d["date"], y=d["pm25"], mode="lines", name="Daily PM2.5",
                             line=dict(color=PRIMARY, width=1), hovertemplate="%{x|%d %b %Y}: %{y:.1f}<extra></extra>"))
    fig.add_trace(go.Scatter(x=o["date"], y=o["pm25"], mode="markers", name=f"Flagged outlier (n={len(o)})",
                             marker=dict(size=9, color=CATEGORICAL[7], symbol="circle-open", line=dict(width=2)),
                             hovertemplate="%{x|%d %b %Y}: %{y:.1f} µg/m³ (flagged)<extra></extra>"))
    fig.update_yaxes(title=f"Daily {PM}", rangemode="tozero")
    return finalize(fig, title, subtitle + " · rule: |robust z| > 3.5 on log PM2.5 within city; flagged, not removed")


def exceedance_bar(summary: pd.DataFrame, n: int = 25, title: str = "Share of days above the WHO 24-h guideline",
                   subtitle: str = WB_SRC) -> go.Figure:
    d = summary.dropna(subset=["pct_days_above_threshold"]).sort_values("pct_days_above_threshold").tail(n)
    if d.empty:
        return empty_figure("No data.", title)
    fig = go.Figure(go.Bar(x=d["pct_days_above_threshold"], y=d["city_label"], orientation="h",
                           marker=dict(color=PRIMARY, cornerradius=4),
                           hovertemplate="<b>%{y}</b><br>%{x:.1f} % of days > 15 µg/m³<extra></extra>"))
    fig.update_xaxes(title="Days above 15 µg/m³ (%)", range=[0, 100], showgrid=True, gridcolor="#e1e0d9")
    return finalize(fig, title, subtitle + " · guideline used as a reference line, not converted to AQI",
                    height=max(360, 22 * len(d) + 140), legend=False)


# ===========================================================================
# Weather relationships
# ===========================================================================


def weather_scatter(df: pd.DataFrame, x: str, y: str = "pm25", stats_text: str = "", max_points: int = 8000,
                    title: str | None = None, subtitle: str = WX_SRC, seed: int = 0) -> go.Figure:
    """Scatter (down-sampled for display; statistics use all points) with binned-median line."""
    title = title or f"PM2.5 vs {LABELS.get(x, x).lower()}"
    d = df[[x, y, "city_label", "date"]].dropna()
    if d.empty:
        return empty_figure("No matched PM2.5–weather days for this selection.", title)
    show = d.sample(max_points, random_state=seed) if len(d) > max_points else d
    fig = go.Figure()
    fig.add_trace(go.Scattergl(x=show[x], y=show[y], mode="markers", name="City-day",
                               marker=dict(size=4, color=PRIMARY, opacity=0.18),
                               customdata=np.stack([show["city_label"].astype(str), show["date"].dt.strftime("%d %b %Y")], -1),
                               hovertemplate="<b>%{customdata[0]}</b> %{customdata[1]}<br>" + LABELS.get(x, x) +
                                             ": %{x:.1f}<br>PM2.5: %{y:.1f}<extra></extra>"))
    b = binned_relationship(d, x, y)
    if not b.empty:
        fig.add_trace(go.Scatter(x=b["x_mid"], y=b["median"], mode="lines+markers", name="Median per decile of x",
                                 line=dict(color="#0b0b0b", width=2), marker=dict(size=8, line=dict(width=2, color=SURFACE)),
                                 customdata=np.stack([b["p25"], b["p75"], b["n"]], -1),
                                 hovertemplate="x ≈ %{x:.1f}<br>Median PM2.5 %{y:.1f}<br>IQR %{customdata[0]:.1f}–"
                                               "%{customdata[1]:.1f}<br>n = %{customdata[2]:,}<extra></extra>"))
    fig.update_xaxes(title=_label(x))
    fig.update_yaxes(title=f"Daily {PM}", rangemode="tozero")
    note = f" · n = {len(d):,} city-days" + (f" (display sample {max_points:,})" if len(d) > max_points else "")
    return finalize(fig, title, subtitle + note + (f"<br>{stats_text}" if stats_text else ""), height=470)


def binned_relationship(df: pd.DataFrame, x: str, y: str = "pm25", q: int = 10) -> pd.DataFrame:
    d = df[[x, y]].dropna()
    if d[x].nunique() < q:
        bins = d[x].round(1)
    else:
        bins = pd.qcut(d[x], q, duplicates="drop")
    g = d.groupby(bins, observed=True)
    return pd.DataFrame({"x_mid": g[x].median(), "median": g[y].median(), "p25": g[y].quantile(0.25),
                         "p75": g[y].quantile(0.75), "n": g[y].size()}).reset_index(drop=True)


def correlation_heatmap(corr: pd.DataFrame, n: pd.DataFrame, title: str = "Spearman correlation matrix",
                        subtitle: str = WX_SRC) -> go.Figure:
    if corr.empty:
        return empty_figure("Not enough variables.", title)
    labels = [LABELS.get(c.replace("_anom", ""), c) + (" (anom.)" if c.endswith("_anom") else "") for c in corr.columns]
    z = corr.to_numpy()
    text = np.vectorize(lambda v: f"{v:+.2f}")(z)
    fig = go.Figure(go.Heatmap(z=z, x=labels, y=labels, colorscale=DIVERGING_SCALE, zmin=-1, zmax=1, xgap=2, ygap=2,
                               text=text, texttemplate="%{text}", customdata=n.to_numpy(),
                               colorbar=dict(title="ρ"),
                               hovertemplate="%{y} × %{x}<br>ρ = %{z:.2f}<br>n = %{customdata:,}<extra></extra>"))
    fig.update_yaxes(autorange="reversed", showgrid=False)
    return finalize(fig, title, subtitle + " · pairwise-complete; p-values not shown because daily values are autocorrelated",
                    height=520, legend=False)


def lag_chart(lags: pd.DataFrame, x: str, title: str | None = None, subtitle: str = WX_SRC) -> go.Figure:
    title = title or f"Lagged correlation: PM2.5(t) vs {LABELS.get(x, x).lower()}(t − lag)"
    if lags.empty:
        return empty_figure("Not enough continuous data for lags.", title)
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=lags["lag"], y=lags["q75_r"], mode="lines", line=dict(width=0), showlegend=False,
                             hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=lags["lag"], y=lags["q25_r"], mode="lines", line=dict(width=0), fill="tonexty",
                             fillcolor="rgba(42,120,214,0.2)", name="IQR across cities", hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=lags["lag"], y=lags["median_r"], mode="lines+markers", name="Median city ρ",
                             line=dict(color=PRIMARY, width=2), marker=dict(size=9, line=dict(width=2, color=SURFACE)),
                             customdata=np.stack([lags["n_cities"], lags["n_pairs"]], -1),
                             hovertemplate="lag %{x} days<br>median ρ %{y:+.2f}<br>%{customdata[0]} cities, "
                                           "%{customdata[1]:,} pairs<extra></extra>"))
    fig.add_hline(y=0, line=dict(color="#c3c2b7", width=1))
    fig.update_xaxes(title="Lag in days (positive = weather leads PM2.5)", dtick=1)
    fig.update_yaxes(title="Spearman ρ")
    return finalize(fig, title, subtitle + " · deseasonalised anomalies; lags on calendar index")


def city_correlation_dots(per_city: pd.DataFrame, labels: dict, title: str, subtitle: str = WX_SRC) -> go.Figure:
    if per_city.empty:
        return empty_figure("No per-city correlations.", title)
    d = per_city.assign(city_label=per_city["city_id"].map(labels)).sort_values("r")
    sig = d["q_value"] < 0.05
    fig = go.Figure(go.Scatter(
        x=d["r"], y=d["city_label"], mode="markers",
        marker=dict(size=10, color=np.where(sig, PRIMARY, MUTED_MARK), line=dict(width=2, color=SURFACE)),
        error_x=dict(type="data", symmetric=False, array=d["ci_high_adj"] - d["r"], arrayminus=d["r"] - d["ci_low_adj"],
                     color="#a9a8a0", thickness=1.5, width=0),
        customdata=np.stack([d["n"], d["n_eff"], d["q_value"]], -1),
        hovertemplate="<b>%{y}</b><br>ρ = %{x:+.2f}<br>n = %{customdata[0]:,} days, n_eff ≈ %{customdata[1]:.0f}"
                      "<br>q = %{customdata[2]:.3g}<extra></extra>"))
    fig.add_vline(x=0, line=dict(color="#c3c2b7", width=1))
    fig.update_xaxes(title="Spearman ρ with 95 % CI based on effective n", range=[-1, 1], showgrid=True, gridcolor="#e1e0d9")
    return finalize(fig, title, subtitle + " · blue = FDR q < 0.05 (autocorrelation-adjusted)",
                    height=max(360, 24 * len(d) + 140), legend=False)


# ===========================================================================
# Data quality
# ===========================================================================


def missingness_heatmap(matrix: pd.DataFrame, title: str = "Missing values by city and variable",
                        subtitle: str = "") -> go.Figure:
    if matrix.empty:
        return empty_figure("No data.", title)
    cols = [LABELS.get(c, c) for c in matrix.columns]
    fig = go.Figure(go.Heatmap(z=matrix.to_numpy(), x=cols, y=list(matrix.index), colorscale=SEQUENTIAL_SCALE, zmin=0,
                               zmax=max(1.0, float(np.nanmax(matrix.to_numpy()))), xgap=2, ygap=2,
                               text=np.vectorize(lambda v: f"{v:.1f}")(matrix.to_numpy()), texttemplate="%{text}",
                               colorbar=dict(title="% missing"),
                               hovertemplate="<b>%{y}</b> · %{x}<br>%{z:.2f} % missing<extra></extra>"))
    fig.update_yaxes(autorange="reversed", showgrid=False)
    return finalize(fig, title, subtitle, height=max(320, 26 * len(matrix) + 150), legend=False)


def completeness_bar(comp: pd.DataFrame, label_col: str = "city_label", title: str = "Completeness by city",
                     subtitle: str = WB_SRC, n: int = 30) -> go.Figure:
    if comp.empty:
        return empty_figure("No data.", title)
    d = comp.sort_values("completeness_pct").head(n).iloc[::-1]
    fig = go.Figure(go.Bar(x=d["completeness_pct"], y=d[label_col], orientation="h",
                           marker=dict(color=PRIMARY, cornerradius=4), customdata=np.stack([d["n_observed"], d["n_expected"]], -1),
                           hovertemplate="<b>%{y}</b><br>%{x:.2f} % (%{customdata[0]:,} of %{customdata[1]:,} days)<extra></extra>"))
    fig.update_xaxes(title="Calendar days with a value (%)", range=[0, 100], showgrid=True, gridcolor="#e1e0d9")
    return finalize(fig, title, subtitle + f" · {min(n, len(comp))} least complete shown",
                    height=max(320, 20 * len(d) + 140), legend=False)


def observations_by_month(obs: pd.DataFrame, title: str = "Observations per month", subtitle: str = WB_SRC) -> go.Figure:
    if obs.empty:
        return empty_figure("No data.", title)
    fig = go.Figure(go.Bar(x=obs["period"], y=obs["n_observations"], marker=dict(color=PRIMARY),
                           hovertemplate="%{x|%b %Y}: %{y:,} city-days<extra></extra>"))
    fig.update_yaxes(title="City-day observations")
    fig.update_layout(bargap=0.1)
    return finalize(fig, title, subtitle, legend=False)


def gap_strip(gaps: pd.DataFrame, start, end, title: str = "Dates missing from the source", subtitle: str = WB_SRC) -> go.Figure:
    if gaps.empty:
        return empty_figure("No missing dates in the selected range.", title)
    days = pd.concat([pd.Series(pd.date_range(r.gap_start, r.gap_end)) for r in gaps.itertuples()])
    fig = go.Figure(go.Scatter(x=days, y=days.dt.day, mode="markers", name="Missing date",
                               marker=dict(size=8, color=CATEGORICAL[7], symbol="line-ns-open", line=dict(width=2)),
                               hovertemplate="%{x|%a %d %b %Y} missing<extra></extra>"))
    fig.update_xaxes(title="", range=[pd.Timestamp(start), pd.Timestamp(end)])
    fig.update_yaxes(title="Day of month", range=[0, 32], dtick=5)
    return finalize(fig, title, subtitle + f" · {len(days)} missing calendar dates", height=320, legend=False)


def exclusion_chart(log: pd.DataFrame, title: str = "Pipeline exclusions and flags") -> go.Figure:
    d = log[~log["step"].isin(["summary", "transformation"])].copy()
    if d.empty:
        return empty_figure("No rows were excluded or flagged by any validation rule.", title)
    d["label"] = d["source_id"] + " · " + d["rule"].str.slice(0, 60)
    d = d.sort_values("n_rows")
    excluded = d["action"].str.contains("excluded|NaN")
    fig = go.Figure(go.Bar(x=d["n_rows"], y=d["label"], orientation="h",
                           marker=dict(color=np.where(excluded, CATEGORICAL[7], PRIMARY), cornerradius=4),
                           customdata=d["action"], hovertemplate="%{y}<br>%{x:,} rows · %{customdata}<extra></extra>"))
    fig.update_xaxes(title="Rows affected", type="log")
    return finalize(fig, title, "red = excluded / nulled, blue = flagged but kept · log scale",
                    height=max(300, 34 * len(d) + 140), legend=False)


def source_timeline(coverage: pd.DataFrame, title: str = "Temporal coverage of each source") -> go.Figure:
    if coverage.empty:
        return empty_figure("No sources loaded.", title)
    fig = go.Figure()
    for i, r in enumerate(coverage.itertuples()):
        fig.add_trace(go.Scatter(x=[r.start, r.end], y=[r.source, r.source], mode="lines+markers",
                                 line=dict(width=10, color=CATEGORICAL[i % 3]), marker=dict(size=12, color=CATEGORICAL[i % 3]),
                                 name=r.source, hovertemplate=f"<b>{r.source}</b><br>{r.start} → {r.end}<br>"
                                 f"{r.cities} cities · {r.resolution} · {r.value_type}<extra></extra>"))
    fig.update_yaxes(title="", showgrid=False)
    return finalize(fig, title, "Each source is analysed separately; overlap is used only for comparison",
                    height=300, legend=False)


def source_comparison_scatter(overlap: pd.DataFrame, title: str = "Same city, same day: two modelled PM2.5 sources") -> go.Figure:
    if overlap.empty:
        return empty_figure("No overlapping city-days between sources.", title)
    fig = go.Figure()
    m = float(max(overlap["pm25_hf"].max(), overlap["pm25_wb"].max())) * 1.05
    fig.add_trace(go.Scatter(x=[0, m], y=[0, m], mode="lines", line=dict(color="#a9a8a0", width=1, dash="dot"),
                             name="1:1 line", hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=overlap["pm25_wb"], y=overlap["pm25_hf"], mode="markers", name="City-day",
                             marker=dict(size=7, color=PRIMARY, opacity=0.55, line=dict(width=1, color=SURFACE)),
                             customdata=np.stack([overlap["city"], overlap["date"].dt.strftime("%d %b %Y")], -1),
                             hovertemplate="<b>%{customdata[0]}</b> %{customdata[1]}<br>World Bank %{x:.1f}<br>"
                                           "Kaggle/HF %{y:.1f}<extra></extra>"))
    fig.update_xaxes(title=f"World Bank daily {PM}", range=[0, m])
    fig.update_yaxes(title=f"Kaggle/HF daily mean {PM}", range=[0, m])
    return finalize(fig, title, f"n = {len(overlap):,} paired city-days, {overlap['city'].nunique()} cities · "
                    "HF day boundary follows the source's hour labels", height=520)


def diurnal_alignment_chart(profile: pd.DataFrame, a: str = "ozone", b: str = "temperature",
                            title: str = "Timestamp diagnostic: ozone vs temperature daily cycle") -> go.Figure:
    """Both variables standardised (z-score) to one axis — no dual axis."""
    if profile.empty:
        return empty_figure("Needs hourly ozone and temperature.", title)
    fig = go.Figure()
    for col, c in ((a, CATEGORICAL[0]), (b, CATEGORICAL[1])):
        z = (profile[col] - profile[col].mean()) / profile[col].std()
        pk = int(profile.loc[profile[col].idxmax(), "hour"])
        fig.add_trace(go.Scatter(x=profile["hour"], y=z, mode="lines+markers", name=f"{LABELS.get(col, col)} (peak hour {pk})",
                                 line=dict(width=2, color=c), marker=dict(size=7),
                                 hovertemplate="hour %{x}: z = %{y:+.2f}<extra>" + LABELS.get(col, col) + "</extra>"))
    fig.update_xaxes(title="Hour label in source file", dtick=2)
    fig.update_yaxes(title="Standardised mean (z-score)", zeroline=True, zerolinecolor="#c3c2b7")
    return finalize(fig, title, HF_SRC + " · ozone normally peaks mid-afternoon local time, as does temperature")


# ===========================================================================
# Statistics
# ===========================================================================


def _wrap_label(text: str, width: int = 16) -> str:
    words, lines, line = text.split(), [], ""
    for w in words:
        if line and len(line) + 1 + len(w) > width:
            lines.append(line)
            line = w
        else:
            line = f"{line} {w}".strip()
    return "<br>".join(lines + [line])


def sensitivity_ranks(ranks: pd.DataFrame, title: str = "City rank stability under data-handling choices") -> go.Figure:
    if ranks.empty:
        return empty_figure("No sensitivity results.", title)
    scen = list(dict.fromkeys(ranks["scenario"]))
    cities = list(dict.fromkeys(ranks["city_label"]))
    colors = color_map(cities)
    fig = go.Figure()
    for c in cities[:MAX_CATEGORICAL]:
        d = ranks[ranks["city_label"] == c].set_index("scenario").reindex(scen)
        fig.add_trace(go.Scatter(x=[_wrap_label(s) for s in scen], y=d["rank"], mode="lines+markers", name=c,
                                 line=dict(width=2, color=colors[c]), marker=dict(size=8, line=dict(width=2, color=SURFACE)),
                                 hovertemplate=f"<b>{c}</b><br>%{{x}}<br>rank %{{y:.0f}}<extra></extra>"))
    fig.update_yaxes(title="Rank by median (1 = highest)", autorange="reversed", dtick=1)
    fig.update_xaxes(tickangle=0, tickfont=dict(size=10))
    return finalize(fig, title, WB_SRC + f" · baseline top {min(len(cities), MAX_CATEGORICAL)} cities", height=480)


def effect_size_chart(table: pd.DataFrame, title: str = "Effect sizes of the formal tests") -> go.Figure:
    d = table[table["justified"] & table["effect_size"].notna()].copy()
    if d.empty:
        return empty_figure("No tests with an effect size.", title)
    d = d.iloc[::-1]
    fig = go.Figure(go.Scatter(
        x=d["effect_size"], y=d["test"], mode="markers",
        marker=dict(size=11, color=PRIMARY, line=dict(width=2, color=SURFACE)),
        error_x=dict(type="data", symmetric=False, array=(d["effect_ci_high"] - d["effect_size"]).fillna(0),
                     arrayminus=(d["effect_size"] - d["effect_ci_low"]).fillna(0), color="#a9a8a0", thickness=1.5, width=0),
        customdata=np.stack([d["effect_size_name"], d["p_value"], d["n"]], -1),
        hovertemplate="<b>%{y}</b><br>%{customdata[0]} = %{x:.3f}<br>p = %{customdata[1]:.3g} · n = %{customdata[2]}<extra></extra>"))
    fig.add_vline(x=0, line=dict(color="#c3c2b7", width=1))
    fig.update_xaxes(title="Effect size (each test's own metric — see table)", showgrid=True, gridcolor="#e1e0d9")
    return finalize(fig, title, "Bars = 95 % bootstrap CI where computed", height=max(320, 40 * len(d) + 140), legend=False)


def artifact_annual_chart(annual: pd.DataFrame, flagged: pd.DataFrame, n: int = 6,
                          title: str = "Annual means of places with a fixed annual level") -> go.Figure:
    """Annual means for the places with the longest fixed-annual-mean runs (flat segments = artifact)."""
    if flagged.empty or annual.empty:
        return empty_figure("No place shows a fixed annual mean across years.", title)
    top = flagged.sort_values("fixed_annual_run", ascending=False).head(min(n, MAX_CATEGORICAL))
    d = annual[annual["city_id"].astype(str).isin(top["city_id"].astype(str))].merge(
        top[["city_id", "city_label"]].astype(str), on="city_id")
    fig = annual_lines(d, title=title, colors=color_map(top["city_label"].astype(str)),
                       subtitle=WB_SRC + " · flat runs = identical annual means across consecutive years")
    return fig


def break_date_chart(flags: pd.DataFrame, title: str = "When abrupt level shifts occur") -> go.Figure:
    d = flags[flags["artifact_reason"].str.contains("shift", na=False)].dropna(subset=["break_date"])
    if d.empty:
        return empty_figure("No abrupt level shifts met the flagging rule.", title)
    c = d.assign(month=pd.to_datetime(d["break_date"]).dt.to_period("M").dt.to_timestamp()).groupby("month").size()
    fig = go.Figure(go.Bar(x=c.index, y=c.values, marker=dict(color=CATEGORICAL[7], cornerradius=3), width=20 * 86400000,
                           hovertemplate="%{x|%b %Y}: %{y} places<extra></extra>"))
    fig.update_yaxes(title="Places with their largest shift in this month")
    return finalize(fig, title, WB_SRC + " · screening scan of deseasonalised monthly anomalies (|t| ≥ 10, shift ≥ 30 % "
                    "of level)", height=360, legend=False)
