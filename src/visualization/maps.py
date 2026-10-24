"""Geographic charts. Uses Plotly's built-in geo projection (no tile server), so maps
render without internet access."""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from src.visualization.themes import (CATEGORICAL, DIVERGING_SCALE, MUTED_MARK, SEQUENTIAL_SCALE, SURFACE,
                                      empty_figure, finalize)

WB_SRC = "Source: World Bank Global PM2.5 Watch (modelled daily estimates)"


def _geo(fig: go.Figure) -> go.Figure:
    fig.update_geos(
        scope="asia", projection_type="mercator", lataxis_range=[23.3, 37.5], lonaxis_range=[60.5, 77.8],
        showcountries=True, countrycolor="#a9a8a0", showcoastlines=True, coastlinecolor="#c3c2b7",
        showland=True, landcolor="#f2f1ec", showocean=True, oceancolor="#e8f0f8", showlakes=False,
        bgcolor=SURFACE, resolution=50, showsubunits=False,
    )
    fig.update_layout(margin=dict(l=0, r=0, t=84, b=0))
    return fig


def _size(pop: pd.Series) -> np.ndarray:
    p = np.clip(pop.astype(float).to_numpy(), 1e4, None)
    return 6 + 22 * (np.log10(p) - 4) / (np.log10(p.max()) - 4 + 1e-9)


def city_metric_map(summary: pd.DataFrame, metric: str = "median", metric_label: str = "Median PM2.5 (µg/m³)",
                    title: str = "PM2.5 across Pakistani cities", subtitle: str = WB_SRC) -> go.Figure:
    """Bubble map: colour = metric (sequential), size = population (log)."""
    d = summary.dropna(subset=[metric, "latitude", "longitude"])
    if d.empty:
        return empty_figure("No cities match the current filters.", title)
    size = _size(d["population"]) if "population" in d.columns else 9
    fig = go.Figure(go.Scattergeo(
        lat=d["latitude"], lon=d["longitude"], mode="markers",
        marker=dict(size=size, color=d[metric], colorscale=SEQUENTIAL_SCALE, cmin=d[metric].min(),
                    cmax=d[metric].max(), line=dict(width=1, color=SURFACE), opacity=0.9,
                    colorbar=dict(title=dict(text=metric_label, side="right"), thickness=12)),
        customdata=np.stack([d["city_label"], d.get("province", pd.Series([""] * len(d))).astype(str),
                             d.get("population", pd.Series([np.nan] * len(d)))], axis=-1),
        hovertemplate="<b>%{customdata[0]}</b><br>%{customdata[1]}<br>" + metric_label +
                      ": %{marker.color:.1f}<br>Population: %{customdata[2]:,.0f}<extra></extra>",
    ))
    fig = _geo(fig)
    return finalize(fig, title, subtitle + " · bubble size = population (log scale)", height=560, legend=False)


def trend_map(trends: pd.DataFrame, cities: pd.DataFrame,
              title: str = "Deseasonalised PM2.5 trend by city") -> go.Figure:
    """Diverging map of trend slope (µg/m³ per year); cities without a clear trend are muted."""
    d = trends.merge(cities[["city_id", "latitude", "longitude", "population", "province"]], on="city_id")
    if d.empty:
        return empty_figure("No trend estimates available.", title)
    lim = float(np.nanquantile(np.abs(d["slope_per_year"]), 0.95)) or 1.0
    clear = d[d["direction"] != "no clear trend"]
    unclear = d[d["direction"] == "no clear trend"]
    fig = go.Figure()
    fig.add_trace(go.Scattergeo(
        lat=unclear["latitude"], lon=unclear["longitude"], mode="markers", name="No clear trend (FDR q ≥ 0.05)",
        marker=dict(size=6, color=MUTED_MARK, line=dict(width=0.5, color=SURFACE)),
        text=unclear["city_label"], customdata=unclear["slope_per_year"],
        hovertemplate="<b>%{text}</b><br>Slope: %{customdata:+.2f} µg/m³/yr (not significant)<extra></extra>"))
    fig.add_trace(go.Scattergeo(
        lat=clear["latitude"], lon=clear["longitude"], mode="markers", name="Clear trend (FDR q < 0.05)",
        marker=dict(size=9, color=clear["slope_per_year"], colorscale=DIVERGING_SCALE, cmin=-lim, cmax=lim,
                    line=dict(width=1, color=SURFACE),
                    colorbar=dict(title=dict(text="µg/m³ per year", side="right"), thickness=12)),
        text=clear["city_label"],
        customdata=np.stack([clear["slope_per_year"], clear["ci_low"], clear["ci_high"], clear["q_value"]], axis=-1),
        hovertemplate="<b>%{text}</b><br>Slope: %{customdata[0]:+.2f} µg/m³/yr<br>95% CI (HAC): "
                      "%{customdata[1]:+.2f} to %{customdata[2]:+.2f}<br>q = %{customdata[3]:.3g}<extra></extra>"))
    fig = _geo(fig)
    return finalize(fig, title, WB_SRC + " · OLS on monthly anomalies, Newey–West CI, BH-FDR across cities",
                    height=560)


def coverage_map(cities: pd.DataFrame, weather_ids: set[str], hf_points: pd.DataFrame | None = None,
                 title: str = "Where each data source has coverage") -> go.Figure:
    """Up to three categories (CVD-safe all-pairs): WB only, WB + ERA5 weather, Kaggle/HF location."""
    fig = go.Figure()
    has_w = cities["city_id"].astype(str).isin(weather_ids)
    groups = [("World Bank PM2.5 only", cities[~has_w], MUTED_MARK, 6),
              ("World Bank PM2.5 + ERA5 weather", cities[has_w], CATEGORICAL[0], 10)]
    for name, d, col, size in groups:
        fig.add_trace(go.Scattergeo(lat=d["latitude"], lon=d["longitude"], mode="markers", name=name,
                                    marker=dict(size=size, color=col, line=dict(width=1, color=SURFACE)),
                                    text=d["city_label"], hovertemplate="<b>%{text}</b><extra>" + name + "</extra>"))
    if hf_points is not None and not hf_points.empty:
        fig.add_trace(go.Scattergeo(lat=hf_points["latitude"], lon=hf_points["longitude"], mode="markers",
                                    name="Kaggle/HF hourly city", text=hf_points["city"],
                                    marker=dict(size=13, symbol="diamond-open", color=CATEGORICAL[1],
                                                line=dict(width=2, color=CATEGORICAL[1])),
                                    hovertemplate="<b>%{text}</b><extra>Kaggle/HF</extra>"))
    fig = _geo(fig)
    return finalize(fig, title, f"Sources: World Bank ({len(cities)} places), Open-Meteo ERA5 "
                    f"({int(has_w.sum())} places), Kaggle/HF", height=560)
