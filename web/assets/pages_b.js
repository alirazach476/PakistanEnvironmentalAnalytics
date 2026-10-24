// Weather & Pollution, Distributions, Statistical Analysis, Data Quality, Methodology.

import { annual, citySummaries, cityList, cityValues, D, dayMask, F, pm, pooledValues, wx } from "./data.js";
import { fmt, fmtInt, fmtP, isNum, mean, quantileSorted, signed } from "./stats.js";
import { cat, colorMap, div, empty, geoLayout, MUTED, plot, seq, whoLine } from "./charts.js";
import { bindSeg, callout, card, esc, kpi, picker, section, seg, table } from "./ui.js";
import { byPop, histChart, S, scatterWithBins } from "./pages_a.js";

const PM = "PM2.5 (µg/m³)";
const WXV = ["temperature", "humidity", "wind_speed", "precipitation", "pressure", "dew_point"];
const lab = (v) => D.meta.labels[v] || v;

// ===================================================================================
export function weather(root) {
  const ids = new Set(cityList().map((i) => D.cities[i].city_id));
  const wxCities = D.meta.weather_city_ids.filter((id) => ids.has(id));
  if (!wxCities.length) { root.innerHTML = callout(`No places with ERA5 weather match the filters (weather exists for ${D.meta.weather_city_ids.length} places).`, "warn"); return; }
  S.wxMode = S.wxMode || "anom";
  root.innerHTML = `
  ${callout(`<b>Matching.</b> World Bank daily PM2.5 joined to Open-Meteo ERA5 daily weather for the same place (nearest 0.25° grid point) and calendar date — ${wxCities.length} places in the current selection. The World Bank day boundary is undocumented; weather uses the local (PKT) day, so ±1-day lags are shown. <b>Associations only — not causation.</b>`)}
  <div class="card mb" style="display:flex;gap:12px;flex-wrap:wrap;align-items:center">
    ${seg("wx-var", WXV, S.wxVar, D.meta.labels)} ${seg("wx-mode", ["raw", "anom"], S.wxMode, { raw: "Raw daily values", anom: "Seasonal cycle removed" })}
  </div>
  <div class="grid g4 mb" id="wx-kpis"></div>
  <div id="wx-interp"></div>
  <div class="mb">${card("wx-scatter", "", "")}</div>
  <div class="grid g2 mb">${card("wx-dots", "Per-place Spearman ρ", "95% CI from effective sample size · blue = FDR q < 0.05 · full period")}${card("wx-lag", "Lagged correlation", "PM2.5(t) vs weather(t − lag) · median and IQR across places · full period")}</div>
  <div class="mb">${card("wx-mat", "Spearman correlation matrix", "pairwise-complete · full period · p-values omitted (autocorrelated daily data)")}</div>
  ${section("All weather variables", "median within-place ρ; place = unit of analysis")}
  <div class="card mb"><div id="wx-table"></div></div>
  <div id="wx-flip"></div>`;

  const mask = dayMask();
  const draw = () => {
    const v = S.wxVar, anom = S.wxMode === "anom", key = `${v}|${anom ? "anom" : "raw"}`;
    const per = D.analysis.per_city_corr[key].filter((p) => ids.has(p.city_id));
    const pooled = D.analysis.pooled_corr.find((p) => p.x === v && p.deseasonalized === anom);
    const test = (anom ? D.analysis.tests_all : []).find((t) => t.name.startsWith(`pm25 vs ${v}`));
    const sig = per.filter((p) => p.q_value < 0.05).length;
    const medR = quantileSorted(Float64Array.from(per.map((p) => p.r)).sort(), 0.5);
    const medNeff = quantileSorted(Float64Array.from(per.map((p) => p.n_eff)).sort(), 0.5);
    document.getElementById("wx-kpis").innerHTML =
      kpi("city", "Places", fmtInt(per.length), "with ERA5 weather") +
      kpi("trends", "Median within-place ρ", signed(medR), anom ? "deseasonalised anomalies" : "raw daily values") +
      kpi("check", "Significant after FDR", `${sig} / ${per.length}`, "autocorrelation-adjusted p") +
      kpi("rows", "Median effective n", fmtInt(medNeff), `vs ${fmtInt(quantileSorted(Float64Array.from(per.map((p) => p.n)).sort(), 0.5))} raw days`);
    document.getElementById("wx-interp").innerHTML = test ? callout(esc(test.interpretation)) : pooled ? callout(`Across ${pooled.n_cities} places (full period): median ρ ${signed(pooled.median_r)}, range ${signed(pooled.min_r)} to ${signed(pooled.max_r)}; ${pooled.n_positive} positive / ${pooled.n_negative} negative. Raw correlations include the shared seasonal cycle — switch to “Seasonal cycle removed”.`) : "";

    // scatter from client data (respects filters)
    const xs = [], ys = [], dates = [], labs = [];
    for (const id of wxCities) {
      const c = D.byId.get(id);
      let mx = new Array(12).fill(0), my = new Array(12).fill(0), mn = new Array(12).fill(0);
      if (anom) for (let d = 0; d < D.nD; d++) { const a = wx(id, v, d), b = pm(c.idx, d); if (isNum(a)) { mx[D.month[d] - 1] += a; my[D.month[d] - 1] += b; mn[D.month[d] - 1]++; } }
      for (let d = 0; d < D.nD; d++) {
        if (!mask[d] || (F.noOutliers && D.out[c.idx * D.nD + d])) continue;
        let a = wx(id, v, d), b = pm(c.idx, d);
        if (anom) { const k = D.month[d] - 1; a -= mx[k] / mn[k]; b -= my[k] / mn[k]; }
        xs.push(a); ys.push(b); dates.push(D.meta.dates[d]); labs.push(c.city_label);
      }
    }
    document.querySelector("#wx-scatter").closest(".card").querySelector(".card-t").textContent =
      `PM2.5 vs ${lab(v).toLowerCase()}${anom ? " — anomalies (city × calendar-month mean removed)" : ""}`;
    document.querySelector("#wx-scatter").closest(".card").querySelector(".card-s") ?.remove();
    scatterWithBins("wx-scatter", xs, ys, v, dates, labs);
    if (anom) window.Plotly.relayout("wx-scatter", { "xaxis.title.text": `${lab(v)} anomaly (${D.meta.units[v]})`, "yaxis.title.text": "PM2.5 anomaly (µg/m³)", "yaxis.rangemode": "normal" });

    const labels = Object.fromEntries(D.cities.map((c) => [c.city_id, c.city_label]));
    const ord = [...per].sort((a, b) => a.r - b.r);
    plot("wx-dots", [{ x: ord.map((p) => p.r), y: ord.map((p) => labels[p.city_id]), mode: "markers",
      marker: { size: 10, color: ord.map((p) => (p.q_value < 0.05 ? cat()[0] : MUTED())), line: { width: 1.5, color: "#fff" } },
      error_x: { type: "data", symmetric: false, array: ord.map((p) => p.ci_high_adj - p.r), arrayminus: ord.map((p) => p.r - p.ci_low_adj), color: MUTED(), thickness: 1.5, width: 0 },
      customdata: ord.map((p) => [p.n, p.n_eff, p.q_value]), hovertemplate: "<b>%{y}</b><br>ρ = %{x:+.2f}<br>n = %{customdata[0]:,}, n_eff ≈ %{customdata[1]:.0f}<br>q = %{customdata[2]:.2g}<extra></extra>" }],
    { shapes: [{ type: "line", yref: "paper", y0: 0, y1: 1, x0: 0, x1: 0, line: { color: MUTED(), width: 1 } }], xaxis: { range: [-1, 1], title: { text: "Spearman ρ" }, showgrid: true } }, Math.max(360, 22 * ord.length + 80));
    const L = D.analysis.lags[key];
    plot("wx-lag", [
      { x: L.map((r) => r.lag), y: L.map((r) => r.q75_r), mode: "lines", line: { width: 0 }, hoverinfo: "skip", showlegend: false },
      { x: L.map((r) => r.lag), y: L.map((r) => r.q25_r), mode: "lines", line: { width: 0 }, fill: "tonexty", fillcolor: "rgba(42,120,214,0.2)", name: "IQR across places", hoverinfo: "skip" },
      { x: L.map((r) => r.lag), y: L.map((r) => r.median_r), mode: "lines+markers", name: "Median ρ", line: { color: cat()[0], width: 2.4 }, marker: { size: 9 },
        customdata: L.map((r) => [r.n_cities, r.n_pairs]), hovertemplate: "lag %{x} d: ρ %{y:+.2f}<br>%{customdata[0]} places, %{customdata[1]:,} pairs<extra></extra>" },
    ], { shapes: [{ type: "line", xref: "paper", x0: 0, x1: 1, y0: 0, y1: 0, line: { color: MUTED(), width: 1 } }], xaxis: { title: { text: "Lag (days; positive = weather leads)" }, dtick: 1 }, yaxis: { title: { text: "Spearman ρ" } } }, 360);
    const M = D.analysis.matrices[anom ? "anom" : "raw"], names = M.vars.map((x) => (x === "pm25" ? "PM2.5" : lab(x)) + (anom ? " (anom.)" : ""));
    plot("wx-mat", [{ type: "heatmap", z: M.r, x: names, y: names, colorscale: div(), zmin: -1, zmax: 1, xgap: 2, ygap: 2, customdata: M.n,
      text: M.r.map((r) => r.map((x) => signed(x))), texttemplate: "%{text}", colorbar: { title: { text: "ρ" }, thickness: 10 },
      hovertemplate: "%{y} × %{x}<br>ρ = %{z:.2f}<br>n = %{customdata:,}<extra></extra>" }], { yaxis: { autorange: "reversed", showgrid: false } }, 460);
  };
  draw();
  bindSeg("wx-var", (v) => { S.wxVar = v; draw(); });
  bindSeg("wx-mode", (v) => { S.wxMode = v; draw(); });

  const rows = WXV.flatMap((v) => ["raw", "anom"].map((m) => {
    const p = D.analysis.pooled_corr.find((x) => x.x === v && x.deseasonalized === (m === "anom"));
    return { variable: lab(v), unit: D.meta.units[v], series: m === "anom" ? "anomalies" : "raw", places: p.n_cities, median_r: p.median_r,
      min_r: p.min_r, max_r: p.max_r, sig: p.n_significant_fdr, pos: p.n_positive, neg: p.n_negative };
  }));
  table("wx-table", rows, [{ key: "variable", label: "Variable" }, { key: "unit", label: "Unit" }, { key: "series", label: "Series" }, { key: "places", label: "Places", num: true },
    { key: "median_r", label: "Median ρ", num: true, fmt: (v) => signed(v) }, { key: "min_r", label: "Min ρ", num: true, fmt: (v) => signed(v) },
    { key: "max_r", label: "Max ρ", num: true, fmt: (v) => signed(v) }, { key: "sig", label: "Sig. (FDR)", num: true }, { key: "pos", label: "+", num: true }, { key: "neg", label: "−", num: true }],
  { name: "weather_correlations", search: false });
  const flips = WXV.filter((v) => { const r = rows.find((x) => x.variable === lab(v) && x.series === "raw"), a = rows.find((x) => x.variable === lab(v) && x.series === "anomalies"); return r.median_r * a.median_r < 0; });
  document.getElementById("wx-flip").innerHTML = callout((flips.length ? `The sign changes between raw and anomaly correlations for <b>${flips.map(lab).join(", ")}</b>: their raw association is driven by the shared seasonal cycle, not day-to-day variation. ` : "")
    + "Meteorology, emissions (crop-residue burning, heating, traffic) and the PM2.5 model's own use of ERA5 inputs all confound these associations.", "warn");
}

// ===================================================================================
export function distributions(root) {
  S.distSrc = S.distSrc || "wb"; S.logx = S.logx || false; S.dist = S.dist?.length ? S.dist : [];
  const H = D.hourly;
  root.innerHTML = `<div class="card mb" style="display:flex;gap:12px;align-items:center;flex-wrap:wrap">${seg("di-src", H?.profiles ? ["wb", "hf"] : ["wb"], S.distSrc,
    { wb: `World Bank daily PM2.5 (${D.nC} places)`, hf: `Kaggle/HF hourly pollutants (${H?.cities?.length || 0} cities)` })}</div><div id="di-body"></div>`;
  const draw = () => (S.distSrc === "wb" ? distWB() : distHF());
  bindSeg("di-src", (v) => { S.distSrc = v; draw(); });
  draw();
}

function distWB() {
  const body = document.getElementById("di-body"), sums = citySummaries();
  if (!sums.length) { body.innerHTML = callout("No data match the current filters.", "warn"); return; }
  if (!S.dist.length) S.dist = byPop(sums).slice(0, 6).map((s) => s.label);
  body.innerHTML = `
    <div class="grid g2 mb">${card("di-hist", "Distribution of daily PM2.5", "all filtered city-days", { tools: seg("di-log", ["lin", "log"], S.logx ? "log" : "lin", { lin: "Linear", log: "Log scale" }) })}
      ${card("di-exc", "Share of days above the WHO 24-h guideline", "top 20 places · reference only, not AQI")}</div>
    <div class="card mb"><div class="card-t" style="margin-bottom:8px">Places</div><div id="di-pick"></div></div>
    <div class="grid g2 mb">${card("di-violin", "Violin plots", "box inside = IQR; line = mean")}${card("di-pct", "Percentiles (P10–P99)", "◆ = median")}</div>
    ${section("Outliers", `robust |z| > ${D.meta.rules.outlier_z} on log PM2.5 within city — flagged, kept unless excluded above`)}
    <div class="grid g-1-2 mb"><div class="card"><div id="di-out"></div></div>${card("di-out-c", "", "")}</div>`;
  const drawHist = () => histChart("di-hist", pooledValues(), S.logx, "city-days");
  drawHist(); bindSeg("di-log", (v) => { S.logx = v === "log"; drawHist(); });
  const ex = [...sums].sort((a, b) => b.pctAbove - a.pctAbove || b.median - a.median).slice(0, 20).reverse();
  plot("di-exc", [{ type: "bar", orientation: "h", x: ex.map((s) => s.pctAbove), y: ex.map((s) => s.label), marker: { color: cat()[0], cornerradius: 4 },
    hovertemplate: "<b>%{y}</b><br>%{x:.1f}% of days > 15 µg/m³<extra></extra>" }], { xaxis: { title: { text: "Days above 15 µg/m³ (%)" }, range: [0, 100], showgrid: true } }, 460);
  const drawSel = () => {
    const sel = S.dist.map((l) => sums.find((s) => s.label === l)).filter(Boolean), colors = colorMap(S.dist);
    plot("di-violin", sel.map((s) => ({ type: "violin", y: cityValues(s.idx), name: s.label, line: { color: colors[s.label], width: 1.5 }, fillcolor: "rgba(0,0,0,0)",
      box: { visible: true }, meanline: { visible: true }, points: false, spanmode: "hard" })), { showlegend: false, shapes: [whoLine()], yaxis: { title: { text: `Daily ${PM}` }, rangemode: "tozero" } }, 400);
    const P = [10, 25, 50, 75, 90, 99], ord = sel.map((s) => { const v = Float64Array.from(cityValues(s.idx)).sort(); return { s, q: P.map((p) => quantileSorted(v, p / 100)) }; }).sort((a, b) => a.q[2] - b.q[2]);
    const ramp = ["#9ec5f4", "#6da7ec", null, "#256abf", "#184f95", "#0d366b"];
    plot("di-pct", P.map((p, i) => ({ x: ord.map((o) => o.q[i]), y: ord.map((o) => o.s.label), mode: "markers", name: `P${p}`,
      marker: { size: p === 50 ? 13 : 9, symbol: p === 50 ? "diamond" : "circle", color: p === 50 ? getComputedStyle(document.documentElement).getPropertyValue("--ink") : ramp[i], line: { width: 1.5, color: "#fff" } },
      hovertemplate: `<b>%{y}</b><br>P${p}: %{x:.1f}<extra></extra>` })), { shapes: [whoLine("x")], xaxis: { title: { text: PM }, showgrid: true } }, 400);
  };
  picker("di-pick", byPop(sums).map((s) => s.label), S.dist, 8, drawSel);
  drawSel();
  const mask = dayMask();
  const outRows = sums.map((s) => { let n = 0, k = 0; for (let d = 0; d < D.nD; d++) if (mask[d]) { k++; if (D.out[s.idx * D.nD + d]) n++; } return { label: s.label, province: s.province, n_out: n, n: k, pct: (100 * n) / k }; })
    .sort((a, b) => b.n_out - a.n_out);
  table("di-out", outRows, [{ key: "label", label: "Place" }, { key: "n_out", label: "Flagged", num: true }, { key: "pct", label: "%", num: true, fmt: (v) => fmt(v, 2) }],
    { name: "outlier_summary", sortKey: "n_out" });
  const top = sums.find((s) => s.label === outRows[0]?.label);
  if (top) {
    const xs = [], ys = [], ox = [], oy = [];
    for (let d = 0; d < D.nD; d++) if (mask[d]) { const v = pm(top.idx, d); xs.push(D.meta.dates[d]); ys.push(v); if (D.out[top.idx * D.nD + d]) { ox.push(D.meta.dates[d]); oy.push(v); } }
    document.querySelector("#di-out-c").closest(".card").querySelector(".card-t").textContent = `Daily PM2.5 with flagged outliers — ${top.label}`;
    plot("di-out-c", [{ x: xs, y: ys, mode: "lines", name: "Daily", line: { color: cat()[0], width: 1 } },
      { x: ox, y: oy, mode: "markers", name: `Flagged (n=${ox.length})`, marker: { size: 9, color: cat()[7], symbol: "circle-open", line: { width: 2 } } }],
    { yaxis: { title: { text: PM }, rangemode: "tozero" } }, 400);
  }
}

function distHF() {
  const H = D.hourly, body = document.getElementById("di-body");
  S.hfPol = S.hfPol || "pm25";
  body.innerHTML = `${callout(`Hourly values from an undocumented Kaggle upload (licence <b>unknown</b>). Variable names match the Open-Meteo Air Quality API (CAMS model), so they are treated as <b>modelled</b>. Covers ${H.start} → ${H.end}.`
    + (H.identical.length ? ` Identical series between cities: ${[...new Set(H.identical.map((r) => `${r.city_a} = ${r.city_b}`))].join("; ")} (${[...new Set(H.identical.map((r) => lab(r.variable)))].join(", ")}).` : ""), "warn")}
    <div class="card mb">${seg("di-pol", H.pollutants, S.hfPol, D.meta.labels)}</div>
    <div class="grid g2 mb">${card("di-hf-hist", "", "all cities pooled")}${card("di-hf-box", "", "box = IQR, whiskers = P5–P95 (precomputed)")}</div>
    <div class="card"><div id="di-hf-table"></div></div>`;
  const draw = (p) => {
    const h = H.hist[p], ctr = h.edges.slice(0, -1).map((e, i) => (e + h.edges[i + 1]) / 2);
    document.querySelector("#di-hf-hist").closest(".card").querySelector(".card-t").textContent = `Distribution of hourly ${lab(p)}`;
    document.querySelector("#di-hf-box").closest(".card").querySelector(".card-t").textContent = `Hourly ${lab(p)} by city`;
    plot("di-hf-hist", [{ type: "bar", x: ctr, y: h.counts, width: (h.edges[1] - h.edges[0]) * 0.92, marker: { color: cat()[0] }, hovertemplate: "%{x:.1f}: %{y:,} city-hours<extra></extra>" }],
      { bargap: 0, xaxis: { title: { text: `${lab(p)} (µg/m³)` } }, yaxis: { title: { text: "City-hours" } },
        shapes: [{ type: "line", yref: "paper", y0: 0, y1: 1, x0: h.median, x1: h.median, line: { width: 1.5 } }] }, 380);
    const sm = H.summary[p], colors = colorMap(sm.map((r) => r.city));
    plot("di-hf-box", sm.map((r) => ({ type: "box", name: r.city, x: [r.city], q1: [r.p25], median: [r.p50], q3: [r.p75], lowerfence: [r.p5], upperfence: [r.p95], mean: [r.mean], boxmean: true,
      marker: { color: colors[r.city] }, line: { width: 1.5 }, fillcolor: "rgba(0,0,0,0)" })), { showlegend: false, yaxis: { title: { text: `${lab(p)} (µg/m³)` }, rangemode: "tozero" } }, 380);
    table("di-hf-table", sm, [{ key: "city", label: "City" }, { key: "n", label: "Hours", num: true, fmt: fmtInt }, ...["mean", "std", "min", "p5", "p25", "median", "p75", "p95", "max"].map((k) => ({ key: k, label: k, num: true, fmt: (v) => fmt(v) }))],
      { name: `hourly_${p}_summary`, search: false });
  };
  draw(S.hfPol); bindSeg("di-pol", (v) => { S.hfPol = v; draw(v); });
}

// ===================================================================================
function holm(ps) {
  const idx = ps.map((p, i) => [p, i]).filter(([p]) => isNum(p)).sort((a, b) => a[0] - b[0]), m = idx.length, out = ps.map(() => null);
  let prev = 0;
  idx.forEach(([p, i], k) => { prev = Math.max(prev, Math.min(1, (m - k) * p)); out[i] = prev; });
  return out;
}

export function statistics(root) {
  S.statSet = S.statSet || "all";
  root.innerHTML = `
  ${callout(`<b>Independence.</b> Daily values within a place are serially correlated, so no test treats days as independent samples. Each test uses one summary value per place (paired designs where the same places are compared), and places sharing an identical model series are reduced to one representative. Nearby places still share regional weather, so p-values remain somewhat optimistic. Tests are precomputed on the <b>full period</b>.`)}
  <div class="card mb" style="display:flex;gap:12px;align-items:center;flex-wrap:wrap"><b>Test set</b>${seg("st-set", ["all", "clean"], S.statSet, { all: "All places", clean: "Artifact-flagged places excluded" })}</div>
  <div id="st-body"></div>
  ${section("Sensitivity analysis", "one data-handling rule changed per scenario; full period")}
  <div class="card mb"><div id="st-sens"></div></div>
  <div class="mb">${card("st-ranks", "Rank stability of the baseline top places", "rank by median (1 = highest) under each scenario")}</div>`;
  const draw = () => {
    const T = D.analysis[S.statSet === "all" ? "tests_all" : "tests_clean"];
    const adj = holm(T.map((t) => (t.justified ? t.p_value : null)));
    const rows = T.map((t, i) => ({ name: t.name, unit: t.unit_of_analysis, n: t.n, stat: t.statistic, p: t.p_value, ph: adj[i], es_name: t.effect_size_name, es: t.effect_size,
      lo: t.effect_ci?.[0], hi: t.effect_ci?.[1], ok: t.justified ? "yes" : "not justified" }));
    const wx = T.filter((t) => t.name.startsWith("pm25 vs "));
    document.getElementById("st-body").innerHTML = `<div class="card mb"><div id="st-table"></div></div>
      ${callout("<b>Significance is not importance.</b> With hundreds of places and years of data, tiny differences reach small p-values. Judge each result by its effect size, confidence interval and the µg/m³ difference it implies.", "warn")}
      <div class="mb">${card("st-eff", "Median within-place correlation with weather (deseasonalised)", "95% bootstrap CI across places")}</div>
      ${section("Test details")}
      ${T.map((t, i) => `<details class="test${t.justified ? "" : " not-run"}" ${i === 0 ? "open" : ""}><summary><span class="pill ${t.justified ? "blue" : "warn"}">${t.justified ? "✓ run" : "⚠ not justified"}</span><span class="st">${esc(t.name)}</span>
        <span class="muted small">n = ${t.n}</span><span class="chev">›</span></summary><div class="test-body">
        <dl><dt>Question</dt><dd>${esc(t.question)}</dd><dt>Null hypothesis</dt><dd>${esc(t.null_hypothesis)}</dd><dt>Method</dt><dd>${esc(t.test)}</dd>
          <dt>Unit</dt><dd>${esc(t.unit_of_analysis)}</dd><dt>Assumptions</dt><dd>${t.assumptions.map(esc).join("; ")}</dd></dl>
        <div class="stat-boxes">${t.justified ? `<div class="stat-box"><div class="l">Statistic</div><div class="v">${fmt(t.statistic, 3)}</div></div>
          <div class="stat-box"><div class="l">p-value</div><div class="v">${fmtP(t.p_value)}</div></div>
          <div class="stat-box"><div class="l">${esc(t.effect_size_name || "Effect")}</div><div class="v">${fmt(t.effect_size, 3)}</div></div>` : ""}
          ${t.effect_ci ? `<div class="stat-box" style="grid-column:1/-1"><div class="l">95% CI of effect</div><div class="v">${fmt(t.effect_ci[0], 3)} to ${fmt(t.effect_ci[1], 3)}</div></div>` : ""}</div>
        <div class="interp">${esc(t.interpretation)}</div>
        <ul class="caveats">${t.caveats.map((c) => `<li>${esc(c)}</li>`).join("")}</ul>
        ${t.details && t.details.length ? `<div style="grid-column:1/-1" id="st-det-${i}"></div>` : ""}</div></details>`).join("")}`;
    table("st-table", rows, [{ key: "name", label: "Test" }, { key: "n", label: "n", num: true }, { key: "stat", label: "Statistic", num: true, fmt: (v) => fmt(v, 3) },
      { key: "p", label: "p", num: true, fmt: fmtP }, { key: "ph", label: "p (Holm, family)", num: true, fmt: fmtP }, { key: "es_name", label: "Effect size" },
      { key: "es", label: "Value", num: true, fmt: (v) => fmt(v, 3) }, { key: "lo", label: "CI low", num: true, fmt: (v) => fmt(v, 3) }, { key: "hi", label: "CI high", num: true, fmt: (v) => fmt(v, 3) },
      { key: "ok", label: "Assumptions" }], { name: `statistical_tests_${S.statSet}`, search: false });
    const lbl = Object.fromEntries(D.cities.map((c) => [c.city_id, c.city_label]));
    T.forEach((t, i) => {
      if (!t.details || !t.details.length) return;
      const keys = Object.keys(t.details[0]).filter((k) => !["city_id"].includes(k)).slice(0, 10);
      const rowsD = t.details.map((r) => ({ ...(r.city_id ? { place: lbl[r.city_id] || r.city_id } : {}), ...r }));
      const cols = [...(rowsD[0].place ? [{ key: "place", label: "Place" }] : []), ...keys.map((k) => ({ key: k, label: k, num: typeof t.details[0][k] === "number",
        fmt: /^[pq](_|$)/.test(k) ? fmtP : (v) => (typeof v === "number" ? (Math.abs(v) < 1e-3 && v !== 0 ? v.toExponential(2) : fmt(v, 3)) : esc(v ?? "—")) }))];
      table(`st-det-${i}`, rowsD, cols, { name: `test_${i}_details`, search: rowsD.length > 12 });
    });
    const order = [...wx].reverse();
    plot("st-eff", [{ x: order.map((t) => t.effect_size), y: order.map((t) => lab(t.name.replace("pm25 vs ", "").split(" (")[0])), mode: "markers",
      marker: { size: 12, color: cat()[0], line: { width: 2, color: "#fff" } },
      error_x: { type: "data", symmetric: false, array: order.map((t) => (t.effect_ci?.[1] ?? t.effect_size) - t.effect_size), arrayminus: order.map((t) => t.effect_size - (t.effect_ci?.[0] ?? t.effect_size)), color: MUTED(), thickness: 2, width: 0 },
      hovertemplate: "<b>%{y}</b><br>median ρ %{x:+.3f}<extra></extra>" }],
    { shapes: [{ type: "line", yref: "paper", y0: 0, y1: 1, x0: 0, x1: 0, line: { color: MUTED(), width: 1 } }], xaxis: { title: { text: "Median within-place Spearman ρ" }, showgrid: true } }, 260);
  };
  draw(); bindSeg("st-set", (v) => { S.statSet = v; draw(); });
  const sens = D.analysis.sensitivity;
  table("st-sens", sens, [{ key: "scenario", label: "Scenario" }, { key: "rows_removed_pct", label: "Rows removed %", num: true, fmt: (v) => fmt(v, 2) },
    { key: "cities", label: "Places", num: true }, { key: "overall_median", label: "Overall median", num: true, fmt: (v) => fmt(v, 2) },
    { key: "median_of_city_medians", label: "Median of place medians", num: true, fmt: (v) => fmt(v, 2) }, { key: "top_city", label: "Top place" },
    { key: "top10_overlap_with_baseline", label: "Top-10 overlap", num: true }, { key: "rank_spearman_vs_baseline", label: "Rank ρ vs baseline", num: true, fmt: (v) => fmt(v, 3) }],
  { name: "sensitivity_scenarios", search: false });
  const R = D.analysis.sensitivity_ranks, scen = [...new Set(R.map((r) => r.scenario))], cities = [...new Set(R.map((r) => r.city_label))], colors = colorMap(cities);
  plot("st-ranks", cities.map((c) => ({ x: scen.map((s) => s.replace(/(.{1,18})(\s|$)/g, "$1<br>")), y: scen.map((s) => R.find((r) => r.city_label === c && r.scenario === s)?.rank ?? null),
    mode: "lines+markers", name: c, line: { color: colors[c], width: 2 }, marker: { size: 8 }, hovertemplate: `<b>${esc(c)}</b> rank %{y}<extra></extra>` })),
  { yaxis: { autorange: "reversed", title: { text: "Rank (1 = highest median)" }, dtick: 2 }, xaxis: { tickfont: { size: 10 } }, margin: { b: 90 } }, 440);
}

// ===================================================================================
export function quality(root) {
  const M = D.meta, H = D.hourly, cities = D.cities;
  const art = cities.filter((c) => c.artifact_flag), fixed = cities.filter((c) => c.fixed_annual_run >= 3), shift = art.filter((c) => c.artifact_reason.includes("shift"));
  const monthsCount = {}; shift.forEach((c) => { const k = (c.break_date || "").slice(0, 7); monthsCount[k] = (monthsCount[k] || 0) + 1; });
  const topMonth = Object.entries(monthsCount).sort((a, b) => b[1] - a[1])[0];
  const provTop = Object.entries(shift.reduce((a, c) => ((a[c.province] = (a[c.province] || 0) + 1), a), {})).sort((a, b) => b[1] - a[1])[0];
  root.innerHTML = `
  ${section("Sources and coverage")}
  <div class="card mb"><div id="dq-cov"></div></div>
  <div class="grid g2 mb">${card("dq-tl", "Temporal coverage", "each source analysed separately; overlap used only for comparison")}${card("dq-map", "Where each source has coverage", "")}</div>
  ${section("Model-artifact screening", "World Bank series")}
  <div class="grid g3 mb">${kpi("quality", "Places flagged", `${art.length}<small>/ ${cities.length}</small>`, "kept by default; toggle above to exclude")}
    ${kpi("calendar", "Fixed annual mean (≥ 3 yrs)", fmtInt(fixed.length), "consecutive annual means within 0.5%")}
    ${kpi("trends", "Abrupt level shift", fmtInt(shift.length), topMonth ? `most common: ${topMonth[0]} (${topMonth[1]} places)` : "")}</div>
  ${callout(`<b>${fixed.length}</b> places repeat the same annual mean for three or more consecutive complete years — real annual concentrations do not do this, so the model appears to scale daily values to a fixed annual level. <b>${shift.length}</b> places show an abrupt step in their deseasonalised series${topMonth ? `, most often in <b>${topMonth[0]}</b>${provTop ? ` (${provTop[0]} most affected)` : ""}` : ""}. These patterns point to changes in model inputs or versions rather than air quality.`, "warn")}
  <div class="grid g2 mb">${card("dq-fixed", "Annual means of places with a fixed annual level", "flat runs = identical annual means")}${card("dq-break", "When abrupt level shifts occur", "screening scan (|t| ≥ 10 and shift ≥ 30% of level)")}</div>
  <div class="card mb"><div id="dq-art"></div></div>
  ${section("Completeness and gaps")}
  ${M.gap_pattern.n_missing ? callout(`<b>${M.gap_pattern.n_missing}</b> calendar dates are missing for every place${M.gap_pattern.all_month_end ? " — <b>all of them the last day of a month</b>, a systematic pattern in the source files" : ""}. Monthly means therefore use n−1 days; the ≥ 20-day rule is unaffected.`, "warn") : ""}
  <div class="grid g2 mb">${card("dq-gap", "Missing dates", "")}${card("dq-obs", "City-day observations per month", "current filters")}</div>
  ${section("Validation, exclusions and flags", "every pipeline action is logged")}
  <div class="grid g-1-2 mb">${card("dq-excl", "Rows affected by rule", "red = excluded / nulled · blue = flagged but kept · log scale")}<div class="card"><div id="dq-excl-t"></div></div></div>
  ${section("Place identity checks")}
  <div class="grid g2 mb"><div class="card"><div class="card-t">Shared or near-identical names</div><div class="card-s">compared after removing spaces/punctuation</div><div id="dq-amb" style="margin-top:8px"></div></div>
    <div class="card"><div class="card-t">Places sharing an identical PM2.5 series</div><div class="card-s">same model grid cell; one representative kept for inference</div><div id="dq-grp" style="margin-top:8px"></div></div></div>
  <div class="card mb"><div class="card-t">Province-code review list</div><div class="card-s">5 nearest neighbours are mostly in another ADM1 code — expected near borders; a review list, not errors</div><div id="dq-prov" style="margin-top:8px"></div></div>
  ${H?.profiles ? `${section("Kaggle/HF hourly checks")}
  <div class="grid g2 mb">${card("dq-miss", "Missing values by city and variable", "% missing")}${card("dq-align", "Timestamp diagnostic: ozone vs temperature", "standardised hourly means on one axis")}</div>
  ${section("Source-to-source comparison", "Kaggle/HF vs nearest World Bank place, same calendar date")}
  ${callout("Both series are model outputs; disagreement shows model uncertainty, not which is right. The two sources are never pooled.")}
  <div class="grid g2 mb">${card("dq-src", "Same city, same day", "")}<div class="card"><div id="dq-src-t"></div></div></div>` : ""}`;

  table("dq-cov", M.coverage, [{ key: "source", label: "Source" }, { key: "value_type", label: "Values" }, { key: "resolution", label: "Resolution" }, { key: "license", label: "Licence" },
    { key: "cities", label: "Places", num: true }, { key: "start", label: "Start" }, { key: "end", label: "End" }, { key: "rows", label: "Rows", num: true, fmt: fmtInt }], { name: "source_coverage", search: false });
  plot("dq-tl", M.coverage.map((r, i) => ({ x: [r.start, r.end], y: [r.source, r.source], mode: "lines+markers", line: { width: 12, color: cat()[i] }, marker: { size: 13, color: cat()[i] }, name: r.source,
    hovertemplate: `<b>${esc(r.source)}</b><br>${r.start} → ${r.end}<br>${r.cities} places · ${r.resolution}<extra></extra>` })), { showlegend: false, margin: { l: 10 } }, 260);
  const hasW = new Set(M.weather_city_ids);
  const grpTr = (list, name, color, size) => ({ type: "scattergeo", lat: list.map((c) => c.latitude), lon: list.map((c) => c.longitude), mode: "markers", name, text: list.map((c) => c.city_label),
    marker: { size, color, line: { width: 0.6, color: "rgba(255,255,255,.8)" } }, hovertemplate: "<b>%{text}</b><extra>" + name + "</extra>" });
  const hfPts = H?.comparison || [];
  plot("dq-map", [grpTr(cities.filter((c) => !hasW.has(c.city_id)), "World Bank only", MUTED(), 6), grpTr(cities.filter((c) => hasW.has(c.city_id)), "World Bank + ERA5", cat()[0], 10),
    ...(hfPts.length ? [{ type: "scattergeo", lat: hfPts.map((r) => D.cities.find((c) => c.city_label === r.wb_match)?.latitude), lon: hfPts.map((r) => D.cities.find((c) => c.city_label === r.wb_match)?.longitude),
      mode: "markers", name: "Kaggle/HF city", text: hfPts.map((r) => r.city), marker: { size: 15, symbol: "diamond-open", color: cat()[1], line: { width: 2 } }, hovertemplate: "<b>%{text}</b><extra>Kaggle/HF</extra>" }] : [])],
  geoLayout({ legend: { orientation: "v", x: 0.01, y: 0.02 } }), 420);

  const allMask = new Uint8Array(D.nD).fill(1);
  const fx = [...fixed].sort((a, b) => b.fixed_annual_run - a.fixed_annual_run).slice(0, 8), fcol = colorMap(fx.map((c) => c.city_label));
  if (fx.length) plot("dq-fixed", fx.map((c) => { const a = annual(c.idx, allMask); return { x: a.map((r) => String(r.year)), y: a.map((r) => r.mean), mode: "lines+markers", name: c.city_label,
    line: { color: fcol[c.city_label], width: 2 }, marker: { size: 7 }, hovertemplate: `<b>${esc(c.city_label)}</b> %{x}: %{y:.2f}<extra></extra>` }; }),
  { xaxis: { type: "category" }, yaxis: { title: { text: `Annual mean ${PM}` } } }, 380); else empty("dq-fixed", "No place shows a fixed annual mean.");
  const months = Object.keys(monthsCount).filter(Boolean).sort();
  plot("dq-break", [{ type: "bar", x: months.map((m) => m + "-01"), y: months.map((m) => monthsCount[m]), marker: { color: cat()[7], cornerradius: 3 }, hovertemplate: "%{x|%b %Y}: %{y} places<extra></extra>" }],
    { yaxis: { title: { text: "Places with their largest shift here" } } }, 380);
  table("dq-art", art.map((c) => ({ ...c })), [{ key: "city_label", label: "Place" }, { key: "province", label: "Province" }, { key: "artifact_reason", label: "Reason" },
    { key: "fixed_annual_run", label: "Fixed yrs", num: true }, { key: "break_date", label: "Break" }, { key: "break_shift", label: "Shift µg/m³", num: true, fmt: (v) => signed(v, 1) },
    { key: "break_shift_rel", label: "Shift % level", num: true, fmt: (v) => signed(100 * v, 0) }, { key: "break_t", label: "t", num: true, fmt: (v) => fmt(v, 1) }], { name: "model_artifact_flags", sortKey: "break_t" });

  const gapDays = M.gaps.flatMap((g) => { const out = []; for (let t = Date.parse(g.gap_start); t <= Date.parse(g.gap_end); t += 864e5) out.push(new Date(t).toISOString().slice(0, 10)); return out; });
  plot("dq-gap", [{ x: gapDays, y: gapDays.map((d) => +d.slice(8, 10)), mode: "markers", marker: { size: 9, color: cat()[7], symbol: "line-ns-open", line: { width: 2 } }, hovertemplate: "%{x} missing<extra></extra>" }],
    { yaxis: { title: { text: "Day of month" }, range: [0, 32] } }, 300);
  const mask = dayMask(), per = new Array(D.nP).fill(0), cl = cityList();
  for (const ci of cl) for (let d = 0; d < D.nD; d++) if (mask[d] && !(F.noOutliers && D.out[ci * D.nD + d])) per[D.period[d]]++;
  plot("dq-obs", [{ type: "bar", x: D.periods, y: per, marker: { color: cat()[0] }, hovertemplate: "%{x|%b %Y}: %{y:,} city-days<extra></extra>" }], { bargap: 0.1, yaxis: { title: { text: "City-days" } } }, 300);

  const ex = M.exclusions.filter((r) => !["summary", "transformation"].includes(r.step)).sort((a, b) => a.n_rows - b.n_rows);
  plot("dq-excl", [{ type: "bar", orientation: "h", x: ex.map((r) => r.n_rows), y: ex.map((r) => `${r.source_id} · ${r.rule.slice(0, 48)}`),
    marker: { color: ex.map((r) => (/excluded|NaN/.test(r.action) ? cat()[7] : cat()[0])), cornerradius: 4 }, customdata: ex.map((r) => r.action), hovertemplate: "%{y}<br>%{x:,} rows · %{customdata}<extra></extra>" }],
  { xaxis: { type: "log", title: { text: "Rows affected" } }, margin: { l: 8 } }, Math.max(300, 34 * ex.length + 60));
  table("dq-excl-t", M.exclusions, [{ key: "source_id", label: "Source" }, { key: "step", label: "Step" }, { key: "rule", label: "Rule" }, { key: "n_rows", label: "Rows", num: true, fmt: fmtInt },
    { key: "action", label: "Action" }, { key: "example", label: "Examples" }], { name: "pipeline_exclusions" });
  table("dq-amb", cities.filter((c) => c.name_ambiguous), [{ key: "city_label", label: "Label" }, { key: "province", label: "Province" }, { key: "latitude", label: "Lat", num: true, fmt: (v) => fmt(v, 3) },
    { key: "longitude", label: "Lon", num: true, fmt: (v) => fmt(v, 3) }, { key: "population", label: "Population", num: true, fmt: fmtInt }], { name: "ambiguous_names", search: false });
  table("dq-grp", cities.filter((c) => c.series_group_size > 1).sort((a, b) => a.series_group - b.series_group), [{ key: "series_group", label: "Group", num: true }, { key: "city_label", label: "Place" },
    { key: "population", label: "Population", num: true, fmt: fmtInt }, { key: "is_series_representative", label: "Representative", fmt: (v) => (v ? "yes" : "") }], { name: "identical_series_groups", search: false });
  table("dq-prov", M.province_review, [{ key: "city_label", label: "Place" }, { key: "province", label: "Province (source code)" }, { key: "neighbour_majority_adm1", label: "Neighbours' code" },
    { key: "nearest_km", label: "Nearest km", num: true, fmt: (v) => fmt(v, 1) }], { name: "province_review", search: false });

  if (!H?.profiles) return;
  const mt = H.missingness, vars = Object.keys(mt[0]).filter((k) => k !== "city");
  plot("dq-miss", [{ type: "heatmap", z: mt.map((r) => vars.map((v) => r[v])), x: vars.map(lab), y: mt.map((r) => r.city), colorscale: seq(), zmin: 0, zmax: Math.max(1, ...mt.flatMap((r) => vars.map((v) => r[v]))),
    xgap: 2, ygap: 2, texttemplate: "%{z:.1f}", colorbar: { title: { text: "%" }, thickness: 10 }, hovertemplate: "<b>%{y}</b> · %{x}: %{z:.2f}% missing<extra></extra>" }],
  { yaxis: { autorange: "reversed", showgrid: false }, xaxis: { tickangle: -35 } }, 380);
  const ap = H.alignment_profile, z = (k) => { const v = ap.map((r) => r[k]), m = mean(v), sd = Math.sqrt(mean(v.map((x) => (x - m) ** 2))); return v.map((x) => (x - m) / sd); };
  plot("dq-align", ["ozone", "temperature"].map((k, i) => ({ x: ap.map((r) => r.hour), y: z(k), mode: "lines+markers", name: `${lab(k)} (peak hour ${k === "ozone" ? H.alignment.pollutant_peak_hour : H.alignment.weather_peak_hour})`,
    line: { color: cat()[i], width: 2.2 }, marker: { size: 6 } })), { xaxis: { title: { text: "Hour label in source file" }, dtick: 2 }, yaxis: { title: { text: "Standardised mean (z)" }, zeroline: true } }, 380);
  const ov = H.overlap, mx = Math.max(...ov.map((r) => Math.max(r.pm25_hf, r.pm25_wb))) * 1.05;
  plot("dq-src", [{ x: [0, mx], y: [0, mx], mode: "lines", name: "1:1", line: { color: MUTED(), dash: "dot", width: 1 }, hoverinfo: "skip" },
    { x: ov.map((r) => r.pm25_wb), y: ov.map((r) => r.pm25_hf), mode: "markers", name: "City-day", marker: { size: 7, color: cat()[0], opacity: 0.5 }, text: ov.map((r) => `${r.city} ${r.date}`),
      hovertemplate: "<b>%{text}</b><br>World Bank %{x:.1f}<br>Kaggle/HF %{y:.1f}<extra></extra>" }],
  { xaxis: { title: { text: "World Bank daily PM2.5 (µg/m³)" }, range: [0, mx] }, yaxis: { title: { text: "Kaggle/HF daily mean PM2.5 (µg/m³)" }, range: [0, mx] }, showlegend: false }, 440);
  table("dq-src-t", H.comparison, [{ key: "city", label: "City" }, { key: "wb_match", label: "WB place" }, { key: "distance_km", label: "km", num: true, fmt: (v) => fmt(v, 1) }, { key: "n_days", label: "Days", num: true },
    { key: "median_hf", label: "Median HF", num: true, fmt: (v) => fmt(v) }, { key: "median_wb", label: "Median WB", num: true, fmt: (v) => fmt(v) },
    { key: "mean_bias_hf_minus_wb", label: "Bias", num: true, fmt: (v) => signed(v, 1) }, { key: "pearson_r", label: "r", num: true, fmt: (v) => signed(v) }], { name: "source_comparison", search: false });
}

// ===================================================================================
export function methodology(root) {
  S.doc = S.doc || "methodology";
  const src = D.meta.sources;
  root.innerHTML = `
  ${callout("<b>No measured (monitor) data are included.</b> All three sources are model or reanalysis products. The World Bank and Kaggle/HF PM2.5 series are analysed separately and compared only on overlapping city-days. No synthetic data are used in any result.")}
  <div class="grid g3 mb">${Object.entries(src).map(([k, s]) => `<div class="card"><div class="card-h"><div class="card-t">${esc(s.short)}</div><span class="pill ${s.license.startsWith("Unknown") ? "warn" : "blue"}">${esc(s.license)}</span></div>
    <p class="small" style="color:var(--ink-2);margin:8px 0">${esc(s.description)}</p><div class="small"><span class="pill">${esc(s.value_type)}</span> <span class="pill">${esc(s.resolution)}</span></div>
    <p class="small" style="margin:10px 0 4px"><a href="${esc(s.url)}" target="_blank" rel="noopener">Source page ↗</a></p></div>`).join("")}</div>
  <div class="card mb">${seg("me-doc", ["methodology", "data_sources", "data_dictionary"], S.doc, { methodology: "Methodology", data_sources: "Data sources & licences", data_dictionary: "Data dictionary" })}
    <div class="doc" id="me-body" style="margin-top:14px"></div></div>
  <div class="card"><div class="card-t">Pipeline manifest — inputs</div><div class="card-s">SHA-256 hashes identify the exact raw files used · data prepared ${esc(D.meta.prepared)}</div>
    <pre class="small" style="background:var(--surface-2);padding:12px;border-radius:10px;overflow:auto">${esc(JSON.stringify(D.meta.manifest_inputs, null, 2))}</pre></div>
  <div class="footer">Built with Python (pandas, SciPy, statsmodels) and Plotly · data exported ${esc(D.meta.generated)} · World Bank data CC BY-SA 4.0 · Open-Meteo data CC BY 4.0 · Kaggle/HF data licence unknown.</div>`;
  const show = (k) => { document.getElementById("me-body").innerHTML = D.docs[k]; };
  show(S.doc); bindSeg("me-doc", (v) => { S.doc = v; show(v); });
}
