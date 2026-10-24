// Plotly wrappers. Colours follow the validated categorical palette (fixed order, never cycled)
// with separate light/dark steps; sequential = one blue hue; diverging = blue ↔ grey ↔ red.

import { D } from "./data.js";

const CAT_LIGHT = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"];
const CAT_DARK = ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300", "#9085e9", "#e66767"];
export const SEQ = [[0, "#cde2fb"], [0.17, "#9ec5f4"], [0.33, "#6da7ec"], [0.5, "#3987e5"], [0.67, "#256abf"], [0.83, "#184f95"], [1, "#0d366b"]];
export const SEQ_DARK = [[0, "#1d2a40"], [0.2, "#184f95"], [0.4, "#256abf"], [0.6, "#3987e5"], [0.8, "#86b6ef"], [1, "#cde2fb"]];
export const DIV = [[0, "#184f95"], [0.25, "#6da7ec"], [0.5, "#e9eaee"], [0.75, "#ec8a89"], [1, "#b42828"]];
export const DIV_DARK = [[0, "#3987e5"], [0.25, "#24466f"], [0.5, "#2b3446"], [0.75, "#7a3434"], [1, "#e66767"]];

export const isDark = () => document.documentElement.dataset.theme === "dark" ||
  (!document.documentElement.dataset.theme && matchMedia("(prefers-color-scheme: dark)").matches);
const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
export const cat = () => (isDark() ? CAT_DARK : CAT_LIGHT);
export const seq = () => (isDark() ? SEQ_DARK : SEQ);
export const div = () => (isDark() ? DIV_DARK : DIV);
export const MUTED = () => (isDark() ? "#3a4459" : "#c3c8d2");

export function colorMap(keys) {
  const c = cat(), m = {};
  keys.forEach((k, i) => { m[k] = i < c.length ? c[i] : MUTED(); });
  return m;
}

export function layout(extra = {}) {
  const ink = css("--ink"), ink2 = css("--ink-2"), grid = css("--grid"), axis = css("--axis"), bg = css("--plot-bg");
  const base = {
    font: { family: css("--font"), size: 12, color: ink2 },
    paper_bgcolor: bg, plot_bgcolor: bg, colorway: cat(),
    margin: { l: 56, r: 18, t: 12, b: 48 }, hovermode: "closest",
    hoverlabel: { bgcolor: css("--surface"), bordercolor: css("--border-strong"), font: { color: ink, family: css("--font"), size: 12 } },
    legend: { orientation: "h", y: -0.18, x: 0, font: { size: 11.5, color: ink2 }, bgcolor: "rgba(0,0,0,0)" },
    xaxis: { gridcolor: grid, linecolor: axis, zeroline: false, showgrid: false, automargin: true, tickfont: { color: ink2 }, title: { font: { size: 12 } } },
    yaxis: { gridcolor: grid, linecolor: axis, zeroline: false, automargin: true, tickfont: { color: ink2 }, title: { font: { size: 12 } } },
    bargap: 0.22,
  };
  return deepMerge(base, extra);
}

function deepMerge(a, b) {
  const out = { ...a };
  for (const [k, v] of Object.entries(b)) {
    out[k] = v && typeof v === "object" && !Array.isArray(v) && a[k] && typeof a[k] === "object" ? deepMerge(a[k], v) : v;
  }
  return out;
}

export function plot(id, traces, lay = {}, height = 380) {
  const el = typeof id === "string" ? document.getElementById(id) : id;
  if (!el) return;
  el.style.minHeight = `${height}px`;
  return window.Plotly.react(el, traces, layout({ height, ...lay }), {
    responsive: true, displaylogo: false, modeBarButtonsToRemove: ["lasso2d", "select2d", "autoScale2d"],
    toImageButtonOptions: { format: "png", scale: 2, filename: "pakistan-environmental-analytics" },
  });
}

export function empty(id, msg) {
  const el = document.getElementById(id);
  if (el) { window.Plotly.purge(el); el.style.minHeight = "0"; el.innerHTML = `<div class="empty">${msg}</div>`; }
}

export function whoLine(axis = "y") {
  const v = D.meta.rules.who_24h, c = css("--ink-3");
  return axis === "y"
    ? { type: "line", xref: "paper", x0: 0, x1: 1, y0: v, y1: v, line: { color: c, width: 1, dash: "dot" } }
    : { type: "line", yref: "paper", y0: 0, y1: 1, x0: v, x1: v, line: { color: c, width: 1, dash: "dot" } };
}
export function whoNote(axis = "y") {
  const v = D.meta.rules.who_24h;
  return axis === "y"
    ? { xref: "paper", x: 0.005, y: v, yanchor: "bottom", xanchor: "left", text: `WHO 24-h ${v} µg/m³`, showarrow: false, font: { size: 10.5, color: css("--ink-3") } }
    : null;
}

// ----- geo ------------------------------------------------------------------------------
export function geoLayout(extra = {}) {
  const dark = isDark();
  return layout({
    margin: { l: 0, r: 0, t: 0, b: 0 },
    geo: {
      projection: { type: "mercator" }, lataxis: { range: [23.4, 37.4] }, lonaxis: { range: [60.6, 77.8] },
      showcountries: true, countrycolor: dark ? "#3c475c" : "#b8bdc7", showcoastlines: true, coastlinecolor: dark ? "#3c475c" : "#c3c8d2",
      showland: true, landcolor: dark ? "#182033" : "#eef0f3", showocean: true, oceancolor: dark ? "#0f1a2c" : "#e3eef9",
      bgcolor: "rgba(0,0,0,0)", resolution: 50, showlakes: false, showframe: false,
    },
    ...extra,
  });
}

export function sizeFromPop(pops) {
  const lp = pops.map((p) => Math.log10(Math.max(p, 1e4)));
  const mx = Math.max(...lp);
  return lp.map((v) => 6 + (20 * (v - 4)) / (mx - 4 + 1e-9));
}

export function sparkline(el, values, color) {
  if (!el) return;
  const v = values.filter(Number.isFinite);
  if (v.length < 2) return;
  const w = 110, h = 34, mn = Math.min(...v), mx = Math.max(...v);
  const pts = v.map((y, i) => `${(i / (v.length - 1)) * w},${h - 3 - ((y - mn) / (mx - mn || 1)) * (h - 6)}`).join(" ");
  el.innerHTML = `<svg viewBox="0 0 ${w} ${h}" width="${w}" height="${h}" preserveAspectRatio="none">
    <polyline fill="none" stroke="${color}" stroke-width="1.6" stroke-linejoin="round" points="${pts}"/></svg>`;
}
