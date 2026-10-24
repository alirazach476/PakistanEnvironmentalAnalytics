"""Visual theme: colour roles, Plotly template and shared layout helpers.

Colours follow a validated reference palette (categorical order is fixed and
CVD-checked for adjacent pairs; scatter-type charts use at most three hues).
"""

from __future__ import annotations

import plotly.graph_objects as go
import plotly.io as pio

FONT = 'system-ui, -apple-system, "Segoe UI", Roboto, sans-serif'

SURFACE = "#ffffff"
PAGE = "#f9f9f7"
INK = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#898781"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"

# Categorical slots in fixed order — never cycled past 8.
CATEGORICAL = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
MAX_CATEGORICAL = len(CATEGORICAL)
MAX_SCATTER_SERIES = 3  # all-pairs CVD-safe subset

# Sequential (one hue, light -> dark) and diverging (blue <-> grey <-> red)
SEQUENTIAL = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]
SEQUENTIAL_SCALE = [[i / (len(SEQUENTIAL) - 1), c] for i, c in enumerate(SEQUENTIAL)]
DIVERGING_SCALE = [[0.0, "#184f95"], [0.25, "#6da7ec"], [0.5, "#f0efec"], [0.75, "#ec8a89"], [1.0, "#b42828"]]

PRIMARY = CATEGORICAL[0]
ACCENT = CATEGORICAL[1]
REFERENCE = "#52514e"   # reference lines (e.g. WHO guideline) use ink, not a series colour
MUTED_MARK = "#c3c2b7"  # de-emphasised context marks

SEASON_COLORS = dict(zip(["Winter", "Spring", "Pre-monsoon", "Monsoon", "Post-monsoon"], CATEGORICAL[:5]))


def color_map(keys) -> dict:
    """Stable entity -> colour mapping in the given order (pass the full selection, not the
    filtered survivors, so filters never repaint). Hues are never cycled: entities past the
    eighth slot receive the muted context colour; callers cap selections at MAX_CATEGORICAL."""
    keys = list(dict.fromkeys(str(k) for k in keys))
    return {k: (CATEGORICAL[i] if i < MAX_CATEGORICAL else MUTED_MARK) for i, k in enumerate(keys)}


def _template() -> go.layout.Template:
    t = go.layout.Template()
    t.layout = go.Layout(
        font=dict(family=FONT, size=13, color=INK_SECONDARY),
        title=dict(font=dict(size=16, color=INK), x=0, xanchor="left", y=0.97, yanchor="top",
                   subtitle=dict(font=dict(size=12, color=INK_MUTED))),
        paper_bgcolor=SURFACE, plot_bgcolor=SURFACE,
        colorway=CATEGORICAL,
        margin=dict(l=60, r=24, t=84, b=56),
        hoverlabel=dict(bgcolor="white", bordercolor=GRID, font=dict(family=FONT, size=12, color=INK)),
        legend=dict(orientation="h", yanchor="top", y=-0.14, xanchor="left", x=0, font=dict(size=12),
                    bgcolor="rgba(0,0,0,0)", title=dict(text="")),
        xaxis=dict(automargin=True, showgrid=False, linecolor=AXIS, ticks="outside", tickcolor=AXIS, zeroline=False,
                   title=dict(font=dict(size=12, color=INK_SECONDARY))),
        yaxis=dict(automargin=True, gridcolor=GRID, gridwidth=1, linecolor=AXIS, zeroline=False,
                   title=dict(font=dict(size=12, color=INK_SECONDARY))),
        coloraxis=dict(colorbar=dict(outlinewidth=0, thickness=12)),
        bargap=0.25,
    )
    return t


pio.templates["pea"] = _template()
TEMPLATE = "pea"


def wrap_subtitle(text: str, width: int = 88) -> str:
    """Plotly subtitles do not wrap; break at ' · ' separators (and existing <br>) to ~width characters."""
    out = []
    for block in text.split("<br>"):
        line = ""
        for part in block.split(" · "):
            cand = f"{line} · {part}" if line else part
            if line and len(cand) > width:
                out.append(line)
                line = part
            else:
                line = cand
        out.append(line)
    return "<br>".join(out)


def finalize(fig: go.Figure, title: str, subtitle: str = "", height: int = 440, legend: bool = True) -> go.Figure:
    """Apply template, title and wrapped source subtitle consistently (top margin grows with the subtitle)."""
    sub = wrap_subtitle(subtitle) if subtitle else ""
    extra = 15 * sub.count("<br>")
    fig.update_layout(template=TEMPLATE, height=height + extra, showlegend=legend,
                      title=dict(text=title, subtitle=dict(text=sub)), margin=dict(t=84 + extra))
    return fig


def empty_figure(message: str, title: str = "") -> go.Figure:
    """A deliberate, explained empty state instead of a misleading blank chart."""
    fig = go.Figure()
    fig.add_annotation(text=message, x=0.5, y=0.5, xref="paper", yref="paper", showarrow=False,
                       font=dict(size=14, color=INK_SECONDARY))
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    return finalize(fig, title, height=260, legend=False)
