// Overview, City Explorer, City Comparison, Historical Trends, Seasonal Analysis.

import { annual, citySummaries, cityList, cityValues, D, dayMask, F, monthly, nationalMonthly, pooledBySeason, pooledValues, pm, wx } from "./data.js";
import { boxStats, fmt, fmtInt, fmtP, histogram, isNum, mean, pEq, quantileSorted, signed, spearman } from "./stats.js";
import { cat, colorMap, div, empty, geoLayout, MUTED, plot, seq, sizeFromPop, sparkline, whoLine, whoNote } from "./charts.js";
import { bindSeg, callout, card, citySelect, esc, kpi, picker, section, seg, table } from "./ui.js";

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const PM = "PM2.5 (µg/m³)";
const SRC = "World Bank Global PM2.5 Watch — modelled daily estimates";
export const S = { explorer: null, compare: [], trends: [], seasonal: [], window: 30, trendWin: 90, heatMode: "pop", heatN: 20,
  agg: "monthly", kind: "box", wxVar: "wind_speed", oneTrend: null };

export const byPop = (rows) => [...rows].sort((a, b) => b.pop - a.pop);
const defaultPick = (n) => byPop(citySummaries()).slice(0, n).map((s) => s.label);
const ensurePick = (key, n) => {
  const labels = new Set(citySummaries().map((s) => s.label));
  S[key] = S[key].filter((l) => labels.has(l));
  if (!S[key].length) S[key] = defaultPick(n);
};

export function comparableRanking(minCov = 0.8) {
  const mask = dayMask();
  let nd = 0; for (const m of mask) nd += m;
  return citySummaries().map((s) => ({ ...s, coverage: nd ? s.n / nd : 0 }))
    .filter((s) => s.coverage >= minCov).sort((a, b) => b.median - a.median).map((s, i) => ({ ...s, rank: i + 1 }));
}

function noData(root) {
  root.innerHTML = callout("No data match the current filters. Widen the date range or clear the province/season filters.", "warn");
}

// ===================================================================================
export function overview(root) {
  const sums = citySummaries();
  if (!sums.length) return noData(root);
  const pooled = Float64Array.from(pooledValues()).sort();
  const med = quantileSorted(pooled, 0.5);
  const nat = nationalMonthly();
  const rank = comparableRanking();
  const who = D.meta.rules.who_24h;
  const pctCitiesAbove = (100 * sums.filter((s) => s.median > who).length) / sums.length;
  const mask = dayMask(); let nd = 0; for (const m of mask) nd += m;
  // expected = every calendar day in the window (in the selected seasons), so missing source dates count as gaps
  let ncal = 0;
  for (let t = D.ts[F.start]; t <= D.ts[F.end]; t += 864e5) {
    const mo = new Date(t).getUTCMonth() + 1;
    if (!F.seasons.size || F.seasons.has(D.SEASONS[[0, 0, 0, 1, 1, 2, 2, 3, 3, 3, 4, 4, 0][mo]])) ncal++;
  }
  const completeness = (100 * sums.reduce((a, s) => a + s.n, 0)) / (sums.length * ncal);
  const seasons = pooledBySeason().filter((s) => s.n);
  const trends = D.analysis.trends.filter((t) => cityList().includes(D.byId.get(t.city_id)?.idx));
  const flagged = sums.filter((s) => s.artifact);
  const top3 = rank.slice(0, 3);

  root.innerHTML = `
  <div class="hero">
    <span class="pill dot">Modelled estimates · not monitor readings</span>
    <h1 style="margin-top:12px">Air quality across ${sums.length} places in Pakistan, ${D.meta.dates[F.start].slice(0, 4)}–${D.meta.dates[F.end].slice(0, 4)}</h1>
    <p>Daily PM2.5, weather and statistics computed live from World Bank, Open-Meteo ERA5 and Kaggle datasets. Every number reflects the filters above.</p>
    <div class="hero-stats">
      <div class="hero-stat"><div class="v">${fmtInt(pooled.length)}</div><div class="l">City-days</div></div>
      <div class="hero-stat"><div class="v">${fmt(med)} <span style="font-size:15px">µg/m³</span></div><div class="l">Median PM2.5</div></div>
      <div class="hero-stat"><div class="v">${fmt(pctCitiesAbove, 0)}%</div><div class="l">Places with median above WHO 24-h</div></div>
      <div class="hero-stat"><div class="v">${fmt(med / who, 1)}×</div><div class="l">Median ÷ WHO 24-h guideline</div></div>
    </div>
  </div>
  <div class="grid g4 mb">
    ${kpi("city", "Places represented", fmtInt(sums.length), `${new Set(sums.map((s) => s.province)).size} provinces / territories`)}
    ${kpi("calendar", "Date range", `${D.meta.dates[F.start].slice(0, 7)} → ${D.meta.dates[F.end].slice(0, 7)}`, `${fmtInt(nd)} days in selection`)}
    ${kpi("rows", "City-day observations", fmtInt(pooled.length), "daily modelled estimates")}
    ${kpi("gauge", "Median PM2.5", `${fmt(med)}<small>µg/m³</small>`, "monthly median city ↗", "spark-med")}
  </div>
  <div class="grid g3 mb">
    ${kpi("pin", "Highest comparable-window median", top3[0] ? esc(top3[0].label) : "—", top3[0] ? `${fmt(top3[0].median)} µg/m³ · ${top3[0].artifact ? "⚠ artifact-flagged" : "not flagged"}` : "no place with ≥80% coverage")}
    ${kpi("check", "Data completeness", `${fmt(completeness)}<small>%</small>`, "city-days present ÷ calendar city-days in selection")}
    ${kpi("layers", "Source datasets", "3", "World Bank PM2.5 · Kaggle/HF hourly · ERA5 weather")}
  </div>
  ${section("Key findings", "computed for the current selection")}
  <div class="findings mb">
    <div class="finding"><div class="ft">Exposure</div><div class="fv"><b>${fmt(pctCitiesAbove, 0)}%</b> of places have a median above the WHO 24-h guideline (${who} µg/m³); the median place exceeds it on <b>${fmt(quantileSorted(Float64Array.from(sums.map((s) => s.pctAbove)).sort(), 0.5), 0)}%</b> of days.</div></div>
    <div class="finding"><div class="ft">Highest medians</div><div class="fv">${top3.map((r) => `<b>${esc(r.label)}</b> (${fmt(r.median, 0)})`).join(", ") || "—"} µg/m³ over the comparable window.</div></div>
    ${seasons.length > 1 ? (() => { const hi = seasons.reduce((a, b) => (b.median > a.median ? b : a)); const lo = seasons.reduce((a, b) => (b.median < a.median ? b : a));
      return `<div class="finding"><div class="ft">Seasonality</div><div class="fv">Median PM2.5 is <b>${fmt(hi.median, 0)} µg/m³ in ${hi.season}</b> vs <b>${fmt(lo.median, 0)} in ${lo.season}</b> — ${fmt(hi.median / lo.median, 1)}× higher.</div></div>`; })() : ""}
    ${trends.length ? `<div class="finding"><div class="ft">Long-term trends (full period)</div><div class="fv"><b>${trends.filter((t) => t.direction === "decreasing").length}</b> decreasing, <b>${trends.filter((t) => t.direction === "increasing").length}</b> increasing, <b>${trends.filter((t) => t.direction === "no clear trend").length}</b> without a clear trend (FDR-controlled).</div></div>` : ""}
    ${flagged.length ? `<div class="finding warn"><div class="ft">Data caveat</div><div class="fv"><b>${flagged.length}</b> of ${sums.length} places show model artifacts (fixed annual mean or abrupt level shift)${top3.filter((t) => t.artifact).length ? `, including <b>${top3.filter((t) => t.artifact).length} of the top 3</b>` : ""}. Toggle “Exclude artifact places” to compare.</div></div>` : ""}
  </div>
  <div class="grid g-2-1 mb">
    ${card("ov-map", "Median PM2.5 by place", `${SRC} · bubble size = population (log)`)}
    ${card("ov-rank", "15 highest medians", "dotted line = WHO 24-h guideline · ⚠ outlined = artifact-flagged")}
  </div>
  <div class="mb">${card("ov-band", "Monthly PM2.5 across all filtered places", "median place with middle-50% and 5–95% bands · months with ≥ 20 valid days")}</div>
  <div class="grid g2 mb">
    ${card("ov-season", "Daily PM2.5 by season", "box = IQR, line = median, dashed = mean, whiskers = 1.5×IQR")}
    ${card("ov-prov", "Place medians by province", "one point per place; province from source ADM1 codes")}
  </div>
  ${section("Place summary", "sortable · searchable · downloadable")}
  <div class="card"><div id="ov-table"></div></div>`;

  sparkline(document.getElementById("spark-med"), nat.map((r) => r.p50), cat()[0]);
  // map
  plot("ov-map", [{
    type: "scattergeo", lat: sums.map((s) => s.lat), lon: sums.map((s) => s.lon), mode: "markers",
    marker: { size: sizeFromPop(sums.map((s) => s.pop)), color: sums.map((s) => s.median), colorscale: seq(), opacity: 0.9,
      line: { width: 0.8, color: "rgba(255,255,255,0.7)" }, colorbar: { title: { text: "µg/m³", side: "right" }, thickness: 10, len: 0.8 } },
    text: sums.map((s) => s.label), customdata: sums.map((s) => [s.province, s.pop, s.n, s.artifact ? "⚠ artifact-flagged" : ""]),
    hovertemplate: "<b>%{text}</b><br>%{customdata[0]}<br>Median %{marker.color:.1f} µg/m³<br>Population %{customdata[1]:,}<br>%{customdata[2]:,} days %{customdata[3]}<extra></extra>",
  }], geoLayout(), 460);
  // ranking
  const top = [...sums].sort((a, b) => b.median - a.median).slice(0, 15).reverse();
  // Flagged places get a light fill + solid outline (plus the ⚠ label), so the flag never relies on colour alone.
  const rankLabel = (s) => (s.artifact ? "⚠ " : "") + s.label;
  const rankTrace = (rows, name, flagged) => ({
    type: "bar", orientation: "h", name, x: rows.map((s) => s.median), y: rows.map(rankLabel),
    text: rows.map((s) => fmt(s.median)), textposition: "outside", cliponaxis: false, textfont: { size: 11 },
    marker: { color: flagged ? "rgba(42,120,214,0.28)" : cat()[0], cornerradius: 4, line: { color: cat()[0], width: flagged ? 1.5 : 0 } },
    customdata: rows.map((s) => [s.province, s.n]), hovertemplate: "<b>%{y}</b> · %{customdata[0]}<br>Median %{x:.1f} µg/m³<br>%{customdata[1]:,} days<extra></extra>",
  });
  plot("ov-rank", [rankTrace(top.filter((s) => !s.artifact), "Not flagged", false), rankTrace(top.filter((s) => s.artifact), "⚠ Artifact-flagged", true)],
    { shapes: [whoLine("x")], barmode: "overlay", xaxis: { title: { text: `Median ${PM}` }, showgrid: true },
      yaxis: { type: "category", categoryorder: "array", categoryarray: top.map(rankLabel) }, margin: { l: 8, r: 36 } }, 460);
  bandChart("ov-band", nat);
  seasonBox("ov-season", pooledBySeason());
  provinceBox("ov-prov", sums);
  table("ov-table", sums.map((s) => ({ ...s, flag: s.artifact ? s.reason : "" })), [
    { key: "label", label: "Place" }, { key: "province", label: "Province" }, { key: "n", label: "Days", num: true, fmt: fmtInt },
    { key: "median", label: "Median µg/m³", num: true, fmt: (v) => fmt(v) }, { key: "mean", label: "Mean", num: true, fmt: (v) => fmt(v) },
    { key: "p95", label: "P95", num: true, fmt: (v) => fmt(v) }, { key: "max", label: "Max", num: true, fmt: (v) => fmt(v) },
    { key: "pctAbove", label: "% days > WHO", num: true, fmt: (v) => fmt(v, 0) + "%", bar: 100 },
    { key: "pop", label: "Population", num: true, fmt: fmtInt }, { key: "flag", label: "Artifact flag" },
  ], { name: "place_summary", sortKey: "median" });
}

export function bandChart(id, nat) {
  if (!nat.length) return empty(id, "No complete months in this selection.");
  const x = nat.map((r) => r.period), c = cat()[0];
  plot(id, [
    { x, y: nat.map((r) => r.p95), mode: "lines", line: { width: 0 }, hoverinfo: "skip", showlegend: false },
    { x, y: nat.map((r) => r.p05), mode: "lines", line: { width: 0 }, fill: "tonexty", fillcolor: "rgba(42,120,214,0.12)", name: "5–95% of places", hoverinfo: "skip" },
    { x, y: nat.map((r) => r.p75), mode: "lines", line: { width: 0 }, hoverinfo: "skip", showlegend: false },
    { x, y: nat.map((r) => r.p25), mode: "lines", line: { width: 0 }, fill: "tonexty", fillcolor: "rgba(42,120,214,0.28)", name: "Middle 50%", hoverinfo: "skip" },
    { x, y: nat.map((r) => r.p50), mode: "lines", line: { color: c, width: 2.4 }, name: "Median place",
      customdata: nat.map((r) => [r.p25, r.p75, r.n]), hovertemplate: "%{x|%b %Y}<br>Median %{y:.1f} µg/m³<br>IQR %{customdata[0]:.1f}–%{customdata[1]:.1f}<br>%{customdata[2]} places<extra></extra>" },
  ], { shapes: [whoLine()], annotations: [whoNote()], yaxis: { title: { text: `Monthly mean ${PM}` }, rangemode: "tozero" }, hovermode: "x unified" }, 360);
}

export function seasonBox(id, boxes) {
  const b = boxes.filter((s) => s.n);
  if (!b.length) return empty(id, "No data for this selection.");
  plot(id, b.map((s, i) => ({
    type: "box", name: s.season, x: [`${s.season}<br><span style="font-size:10px">n=${fmtInt(s.n)}</span>`],
    q1: [s.q1], median: [s.median], q3: [s.q3], lowerfence: [s.lowerfence], upperfence: [s.upperfence], mean: [s.mean],
    boxmean: true, marker: { color: cat()[D.SEASONS.indexOf(s.season)] }, line: { width: 1.6 }, fillcolor: "rgba(0,0,0,0)",
  })), { showlegend: false, shapes: [whoLine()], annotations: [whoNote()], yaxis: { title: { text: `Daily ${PM}` }, rangemode: "tozero" } }, 360);
}

export function provinceBox(id, sums) {
  const provs = [...new Set(sums.map((s) => s.province))];
  const meds = provs.map((p) => [p, quantileSorted(Float64Array.from(sums.filter((s) => s.province === p).map((s) => s.median)).sort(), 0.5)])
    .sort((a, b) => b[1] - a[1]);
  plot(id, meds.map(([p]) => {
    const r = sums.filter((s) => s.province === p);
    return { type: "box", y: r.map((s) => s.median), name: `${p.replace(" Capital Territory", " CT").replace("Khyber Pakhtunkhwa", "KP")}<br>(n=${r.length})`, boxpoints: "all",
      jitter: 0.45, pointpos: 0, marker: { size: 5, color: cat()[0], opacity: 0.5 }, line: { color: getComputedStyle(document.documentElement).getPropertyValue("--ink-2"), width: 1 },
      fillcolor: "rgba(0,0,0,0)", text: r.map((s) => s.label), hovertemplate: "<b>%{text}</b><br>%{y:.1f} µg/m³<extra></extra>" };
  }), { showlegend: false, yaxis: { title: { text: `Place median ${PM}` } } }, 360);
}

// ===================================================================================
export function explorer(root) {
  const sums = byPop(citySummaries());
  if (!sums.length) return noData(root);
  const labels = sums.map((s) => s.label);
  if (!labels.includes(S.explorer)) S.explorer = labels[0];
  const c = D.cities.find((x) => x.city_label === S.explorer);
  const s = sums.find((x) => x.label === S.explorer);
  const tr = D.analysis.trends.find((t) => t.city_id === c.city_id);
  const hasWx = D.wxIndex.has(c.city_id);
  root.innerHTML = `
  <div class="card mb" style="display:flex;gap:16px;align-items:center;flex-wrap:wrap">
    <div id="ex-pick"></div>
    <div><b style="font-size:16px">${esc(c.city_label)}</b> <span class="muted">· ${esc(c.province)} · ${c.latitude.toFixed(3)}°N, ${c.longitude.toFixed(3)}°E · population ${fmtInt(c.population)}</span></div>
    ${c.artifact_flag ? `<span class="pill warn dot">${esc(c.artifact_reason)}</span>` : `<span class="pill">no artifact flag</span>`}
    ${c.series_group_size > 1 ? `<span class="pill warn">shares an identical series with ${c.series_group_size - 1} other place(s)</span>` : ""}
  </div>
  <div class="grid g4 mb">
    ${kpi("gauge", "Median PM2.5", `${fmt(s.median)}<small>µg/m³</small>`, `${fmtInt(s.n)} days`)}
    ${kpi("trends", "95th percentile", `${fmt(s.p95)}<small>µg/m³</small>`, "1 day in 20 exceeds this")}
    ${kpi("calendar", "Days above WHO 24-h", `${fmt(s.pctAbove, 0)}<small>%</small>`, `> ${D.meta.rules.who_24h} µg/m³`)}
    ${kpi("trends", "Deseasonalised trend", tr && isNum(tr.slope_per_year) ? `${signed(tr.slope_per_year)}<small>µg/m³/yr</small>` : "—",
      tr ? `95% CI ${signed(tr.ci_low)} to ${signed(tr.ci_high)} · ${tr.direction} · full period` : "")}
  </div>
  <div class="mb">${card("ex-daily", `Daily PM2.5 — ${esc(c.city_label)}`, SRC, { tools: seg("ex-win", ["7", "30", "90", "365"], String(S.window), { 7: "7 d", 30: "30 d", 90: "90 d", 365: "1 yr" }) })}</div>
  <div class="grid g2 mb">
    ${card("ex-cal", "Monthly mean by year", "blank = month outside selection or < 20 days")}
    ${card("ex-month", "Month-of-year profile", "median with inter-quartile band")}
  </div>
  <div class="grid g2 mb">
    ${card("ex-hist", "Distribution of daily values", "")}
    ${card("ex-out", "Flagged outliers", `robust |z| > ${D.meta.rules.outlier_z} on log PM2.5 within city — flagged, not removed`)}
  </div>
  ${section("Weather context", hasWx ? "Open-Meteo ERA5 reanalysis, local day" : "")}
  <div id="ex-wx"></div>`;
  citySelect("ex-pick", labels, S.explorer, (v) => { S.explorer = v; explorer(root); });

  const mask = dayMask(), idx = [], vals = [], outs = [];
  for (let d = 0; d < D.nD; d++) if (mask[d]) {
    const flag = D.out[c.idx * D.nD + d];
    if (F.noOutliers && flag) continue;
    idx.push(d); vals.push(pm(c.idx, d)); if (flag) outs.push(d);
  }
  const x = idx.map((d) => D.meta.dates[d]);
  const drawDaily = () => {
    const w = +S.window, half = Math.floor(w / 2), roll = [];
    const full = new Float64Array(D.nD).fill(NaN); idx.forEach((d, i) => { full[d] = vals[i]; });
    for (const d of idx) {
      let sum = 0, n = 0;
      for (let k = Math.max(0, d - half); k <= Math.min(D.nD - 1, d + w - 1 - half); k++) if (isNum(full[k])) { sum += full[k]; n++; }
      roll.push(n >= Math.max(1, Math.floor(w * 0.7)) ? sum / n : null);
    }
    plot("ex-daily", [
      { x, y: vals, mode: "lines", name: "Daily value", line: { color: "rgba(57,135,229,0.35)", width: 1 }, hovertemplate: "%{x}<br>%{y:.1f} µg/m³<extra></extra>" },
      { x, y: roll, mode: "lines", name: `${w}-day rolling mean`, line: { color: cat()[0], width: 2.4 }, hovertemplate: "%{x}<br>rolling %{y:.1f}<extra></extra>" },
    ], { shapes: [whoLine()], annotations: [whoNote()], yaxis: { title: { text: PM }, rangemode: "tozero" }, hovermode: "x unified" }, 380);
  };
  drawDaily();
  bindSeg("ex-win", (v) => { S.window = +v; drawDaily(); });

  const m = monthly(c.idx, mask), years = [...new Set(D.periods.map((p) => +p.slice(0, 4)))];
  const z = years.map((y) => MONTHS.map((_, mi) => { const p = D.periods.indexOf(`${y}-${String(mi + 1).padStart(2, "0")}-01`); return p >= 0 && isNum(m.mean[p]) ? m.mean[p] : null; }));
  plot("ex-cal", [{ type: "heatmap", z, x: MONTHS, y: years.map(String), colorscale: seq(), xgap: 2, ygap: 2,
    colorbar: { title: { text: "µg/m³" }, thickness: 10 }, hovertemplate: "%{x} %{y}: %{z:.1f} µg/m³<extra></extra>" }],
  { yaxis: { autorange: "reversed", type: "category", showgrid: false } }, 340);

  const byMonth = MONTHS.map(() => []);
  idx.forEach((d, i) => byMonth[D.month[d] - 1].push(vals[i]));
  const prof = byMonth.map((a) => { const s2 = Float64Array.from(a).sort(); return [quantileSorted(s2, 0.25), quantileSorted(s2, 0.5), quantileSorted(s2, 0.75), a.length]; });
  plot("ex-month", [
    { x: MONTHS, y: prof.map((p) => p[2]), mode: "lines", line: { width: 0 }, hoverinfo: "skip", showlegend: false },
    { x: MONTHS, y: prof.map((p) => p[0]), mode: "lines", line: { width: 0 }, fill: "tonexty", fillcolor: "rgba(42,120,214,0.2)", name: "IQR", hoverinfo: "skip" },
    { x: MONTHS, y: prof.map((p) => p[1]), mode: "lines+markers", name: "Median", line: { color: cat()[0], width: 2.4 }, marker: { size: 7 },
      customdata: prof.map((p) => [p[0], p[2], p[3]]), hovertemplate: "%{x}: median %{y:.1f}<br>IQR %{customdata[0]:.1f}–%{customdata[1]:.1f}<br>n = %{customdata[2]}<extra></extra>" },
  ], { shapes: [whoLine()], yaxis: { title: { text: `Median daily ${PM}` }, rangemode: "tozero" } }, 340);

  histChart("ex-hist", vals, false, "city-days");
  const ox = outs.map((d) => D.meta.dates[d]), oy = outs.map((d) => pm(c.idx, d));
  plot("ex-out", [
    { x, y: vals, mode: "lines", name: "Daily (context)", line: { color: MUTED(), width: 1 }, hovertemplate: "%{x}: %{y:.1f}<extra></extra>" },
    { x: ox, y: oy, mode: "markers", name: `Flagged (n=${outs.length})`, marker: { size: 9, color: cat()[7], symbol: "circle-open", line: { width: 2 } }, hovertemplate: "%{x}: %{y:.1f} (flagged)<extra></extra>" },
  ], {
    yaxis: { title: { text: PM }, rangemode: "tozero" },
    annotations: outs.length ? [] : [{ xref: "paper", yref: "paper", x: 0.5, y: 1, yanchor: "top", showarrow: false,
      text: "No values flagged for this place in the selection", font: { size: 12.5, color: cat()[0] },
      bgcolor: "rgba(127,127,127,0.08)", borderpad: 6 }],
  }, 340);

  const wxEl = document.getElementById("ex-wx");
  if (!hasWx) {
    wxEl.innerHTML = callout(`ERA5 weather was acquired for ${D.meta.weather_city_ids.length} places only (the most populous plus those matching the Kaggle cities). Places with weather: ${D.meta.weather_city_ids.map((id) => esc(D.byId.get(id).city_label)).join(", ")}.`, "warn");
    return;
  }
  wxEl.innerHTML = card("ex-wx-c", "PM2.5 vs weather", "&nbsp;", { tools: seg("ex-wxv", ["temperature", "humidity", "wind_speed", "precipitation"], S.wxVar, D.meta.labels) });
  const drawWx = () => {
    const xs = idx.map((d) => wx(c.city_id, S.wxVar, d));
    const r = spearman(xs, vals);
    const pc = D.analysis.per_city_corr[`${S.wxVar}|raw`].find((p) => p.city_id === c.city_id);
    scatterWithBins("ex-wx-c", xs, vals, S.wxVar, idx.map((d) => D.meta.dates[d]));
    document.querySelector("#ex-wx .card-s").innerHTML = `Spearman ρ = <b>${signed(r.r)}</b> on ${fmtInt(r.n)} days in selection (raw daily values)` +
      (pc ? ` · full period: effective n ≈ ${fmt(pc.n_eff, 0)}, autocorrelation-adjusted ${pEq(pc.p_value_adjusted_n)}` : "");
  };
  drawWx();
  bindSeg("ex-wxv", (v) => { S.wxVar = v; drawWx(); });
}

export function histChart(id, values, log, unitName = "city-days") {
  const h = histogram(values, 60, log);
  if (!h) return empty(id, "No values to plot.");
  const ctr = h.edges.slice(0, -1).map((e, i) => (e + h.edges[i + 1]) / 2), w = h.edges[1] - h.edges[0];
  const lo = h.edges.slice(0, -1).map((e) => (log ? 10 ** e : e)), hi = h.edges.slice(1).map((e) => (log ? 10 ** e : e));
  const med = quantileSorted(Float64Array.from(values.filter(isNum)).sort(), 0.5);
  const ticks = [1, 2, 5, 10, 20, 50, 100, 200, 500, 1000].filter((t) => t >= lo[0] && t <= hi[hi.length - 1]);
  plot(id, [{ type: "bar", x: ctr, y: h.counts, width: w * 0.92, marker: { color: cat()[0] }, customdata: lo.map((l, i) => [l, hi[i]]),
    hovertemplate: `%{customdata[0]:.1f}–%{customdata[1]:.1f} µg/m³<br>%{y:,} ${unitName}<extra></extra>` }],
  { bargap: 0, shapes: [{ type: "line", yref: "paper", y0: 0, y1: 1, x0: log ? Math.log10(med) : med, x1: log ? Math.log10(med) : med, line: { width: 1.5, color: getComputedStyle(document.documentElement).getPropertyValue("--ink") } }],
    annotations: [{ yref: "paper", y: 1, x: log ? Math.log10(med) : med, text: `median ${fmt(med)}`, showarrow: false, xanchor: "left", yanchor: "top", font: { size: 11 } }],
    xaxis: { title: { text: `${PM}${log ? " — log scale" : ""}` }, ...(log ? { tickvals: ticks.map(Math.log10), ticktext: ticks.map(String) } : {}) },
    yaxis: { title: { text: `Number of ${unitName}` } } }, 340);
}

export function scatterWithBins(id, xs, ys, varName, dates, labels = null) {
  const pts = [];
  for (let i = 0; i < xs.length; i++) if (isNum(xs[i]) && isNum(ys[i])) pts.push(i);
  if (!pts.length) return empty(id, "No matched PM2.5–weather days.");
  const step = Math.max(1, Math.floor(pts.length / 7000)), shown = pts.filter((_, k) => k % step === 0);
  const xsorted = Float64Array.from(pts.map((i) => xs[i])).sort();
  const edges = Array.from({ length: 11 }, (_, k) => quantileSorted(xsorted, k / 10));
  const bins = [];
  for (let b = 0; b < 10; b++) {
    const inb = pts.filter((i) => xs[i] >= edges[b] && (b === 9 ? xs[i] <= edges[b + 1] : xs[i] < edges[b + 1]));
    if (inb.length < 5) continue;
    const ysb = Float64Array.from(inb.map((i) => ys[i])).sort(), xsb = Float64Array.from(inb.map((i) => xs[i])).sort();
    bins.push([quantileSorted(xsb, 0.5), quantileSorted(ysb, 0.5), quantileSorted(ysb, 0.25), quantileSorted(ysb, 0.75), inb.length]);
  }
  const unit = D.meta.units[varName] || "";
  plot(id, [
    { type: "scattergl", x: shown.map((i) => xs[i]), y: shown.map((i) => ys[i]), mode: "markers", name: "City-day",
      marker: { size: 4, color: cat()[0], opacity: 0.2 },
      text: shown.map((i) => (labels ? labels[i] + " · " : "") + dates[i]), hovertemplate: `%{text}<br>${D.meta.labels[varName]}: %{x:.1f} ${unit}<br>PM2.5: %{y:.1f}<extra></extra>` },
    { x: bins.map((b) => b[0]), y: bins.map((b) => b[1]), mode: "lines+markers", name: "Median per decile of x",
      line: { color: getComputedStyle(document.documentElement).getPropertyValue("--ink"), width: 2.2 }, marker: { size: 7 },
      customdata: bins.map((b) => [b[2], b[3], b[4]]), hovertemplate: "x ≈ %{x:.1f}<br>median PM2.5 %{y:.1f}<br>IQR %{customdata[0]:.1f}–%{customdata[1]:.1f}<br>n = %{customdata[2]:,}<extra></extra>" },
  ], { xaxis: { title: { text: `${D.meta.labels[varName]} (${unit})` } }, yaxis: { title: { text: `Daily ${PM}` }, rangemode: "tozero" } }, 420);
}

// ===================================================================================
export function compare(root) {
  const sums = citySummaries();
  if (!sums.length) return noData(root);
  ensurePick("compare", 6);
  root.innerHTML = `
  <div class="card mb"><div class="card-t" style="margin-bottom:8px">Places to compare <span class="muted small">(up to 8, one colour each)</span></div><div id="cmp-pick"></div></div>
  <div id="cmp-body"></div>`;
  const draw = () => {
    const body = document.getElementById("cmp-body");
    const sel = S.compare.map((l) => sums.find((s) => s.label === l)).filter(Boolean);
    if (!sel.length) { body.innerHTML = callout("Add at least one place."); return; }
    const colors = colorMap(S.compare);
    body.innerHTML = `
      <div class="mb">${card("cmp-dots", "Median and 5th–95th percentile range", "dot = median, bar = P5–P95 · dotted = WHO 24-h")}</div>
      <div class="mb">${card("cmp-lines", "Over time", "", { tools: seg("cmp-agg", ["monthly", "annual"], S.agg, { monthly: "Monthly mean", annual: "Annual mean" }) })}</div>
      <div class="grid g2 mb">
        ${card("cmp-dist", "Distribution", "", { tools: seg("cmp-kind", ["box", "violin"], S.kind, { box: "Box", violin: "Violin" }) })}
        ${card("cmp-ecdf", "Cumulative distribution", "share of days at or below each concentration")}
      </div>
      ${section("Comparable-window ranking", "all filtered places with ≥ 80% coverage of the selected days")}
      <div class="grid g-1-2 mb"><div class="card"><div id="cmp-rank"></div></div>${card("cmp-map", "95th-percentile PM2.5", "bubble size = population")}</div>`;
    const ord = [...sel].sort((a, b) => a.median - b.median);
    plot("cmp-dots", [
      { x: ord.map((s) => s.p95), y: ord.map((s) => s.label), mode: "markers", marker: { size: 0.1 }, hoverinfo: "skip", showlegend: false,
        error_x: { type: "data", symmetric: false, array: ord.map(() => 0), arrayminus: ord.map((s) => s.p95 - s.p5), color: MUTED(), thickness: 4, width: 0 } },
      { x: ord.map((s) => s.median), y: ord.map((s) => s.label), mode: "markers", marker: { size: 13, color: ord.map((s) => colors[s.label]), line: { width: 2, color: "#fff" } },
        customdata: ord.map((s) => [s.p5, s.p95, s.n]), hovertemplate: "<b>%{y}</b><br>median %{x:.1f}<br>P5–P95 %{customdata[0]:.1f}–%{customdata[1]:.1f}<br>n = %{customdata[2]:,}<extra></extra>" },
    ], { showlegend: false, shapes: [whoLine("x")], xaxis: { title: { text: PM }, showgrid: true } }, Math.max(240, 46 * ord.length + 80));
    const drawLines = () => {
      const traces = sel.map((s) => {
        if (S.agg === "annual") { const a = annual(s.idx); return { x: a.map((r) => `${r.year}-07-01`), y: a.map((r) => r.mean), mode: "lines+markers", name: s.label, line: { color: colors[s.label], width: 2.2 }, marker: { size: 8 }, hovertemplate: `<b>${esc(s.label)}</b> %{x|%Y}: %{y:.1f}<extra></extra>` }; }
        const m = monthly(s.idx);
        return { x: D.periods, y: m.mean.map((v) => (isNum(v) ? v : null)), mode: "lines", name: s.label, line: { color: colors[s.label], width: 2 }, connectgaps: false, hovertemplate: `<b>${esc(s.label)}</b> %{x|%b %Y}: %{y:.1f}<extra></extra>` };
      });
      plot("cmp-lines", traces, { shapes: [whoLine()], yaxis: { title: { text: `${S.agg === "annual" ? "Annual" : "Monthly"} mean ${PM}` }, rangemode: "tozero" }, hovermode: "x unified" }, 380);
    };
    drawLines(); bindSeg("cmp-agg", (v) => { S.agg = v; drawLines(); });
    const drawDist = () => plot("cmp-dist", sel.map((s) => S.kind === "violin"
      ? { type: "violin", y: cityValues(s.idx), name: s.label, line: { color: colors[s.label], width: 1.5 }, fillcolor: "rgba(0,0,0,0)", box: { visible: true }, meanline: { visible: true }, points: false, spanmode: "hard" }
      : { type: "box", y: cityValues(s.idx), name: s.label, marker: { color: colors[s.label], size: 3, opacity: 0.4 }, line: { width: 1.5 }, fillcolor: "rgba(0,0,0,0)", boxpoints: "outliers" }),
    { showlegend: false, shapes: [whoLine()], yaxis: { title: { text: `Daily ${PM}` }, rangemode: "tozero" } }, 380);
    drawDist(); bindSeg("cmp-kind", (v) => { S.kind = v; drawDist(); });
    plot("cmp-ecdf", sel.map((s) => {
      const v = Float64Array.from(cityValues(s.idx)).sort(), k = Math.max(1, Math.floor(v.length / 300)), xs = [], ys = [];
      for (let i = 0; i < v.length; i += k) { xs.push(v[i]); ys.push(((i + 1) / v.length) * 100); }
      return { x: xs, y: ys, mode: "lines", name: s.label, line: { color: colors[s.label], width: 2 }, hovertemplate: `<b>${esc(s.label)}</b><br>%{y:.0f}% of days ≤ %{x:.1f}<extra></extra>` };
    }), { shapes: [whoLine("x")], xaxis: { title: { text: PM } }, yaxis: { title: { text: "Share of days (%)" }, range: [0, 100] } }, 380);
    const rk = comparableRanking();
    table("cmp-rank", rk, [{ key: "rank", label: "#", num: true }, { key: "label", label: "Place" }, { key: "median", label: "Median", num: true, fmt: (v) => fmt(v) },
      { key: "coverage", label: "Coverage", num: true, fmt: (v) => fmt(v * 100, 0) + "%" }, { key: "reason", label: "Artifact flag" }], { name: "comparable_ranking", sortKey: "rank", desc: false });
    plot("cmp-map", [{ type: "scattergeo", lat: sums.map((s) => s.lat), lon: sums.map((s) => s.lon), mode: "markers", text: sums.map((s) => s.label),
      marker: { size: sizeFromPop(sums.map((s) => s.pop)), color: sums.map((s) => s.p95), colorscale: seq(), colorbar: { title: { text: "µg/m³" }, thickness: 10 }, line: { width: 0.6, color: "rgba(255,255,255,.7)" } },
      hovertemplate: "<b>%{text}</b><br>P95 %{marker.color:.1f} µg/m³<extra></extra>" }], geoLayout(), 440);
  };
  picker("cmp-pick", byPop(sums).map((s) => s.label), S.compare, 8, draw);
  draw();
}

// ===================================================================================
export function trendsPage(root) {
  const sums = citySummaries();
  if (!sums.length) return noData(root);
  ensurePick("trends", 5);
  const ids = new Set(cityList().map((i) => D.cities[i].city_id));
  const tr = D.analysis.trends.filter((t) => ids.has(t.city_id)).map((t) => ({ ...t, artifact: D.byId.get(t.city_id).artifact_flag, reason: D.byId.get(t.city_id).artifact_reason }));
  const cnt = (d) => tr.filter((t) => t.direction === d).length;
  const clear = tr.filter((t) => t.direction !== "no clear trend");
  root.innerHTML = `
  ${F.seasons.size ? callout("A season filter is active: annual means need ≥ 11 complete months, so annual views will be empty. Clear the season filter for annual and trend views.", "warn") : ""}
  <div class="mb">${card("tr-band", "Monthly PM2.5 across all filtered places", "median place with middle-50% and 5–95% bands")}</div>
  <div class="card mb"><div class="card-t" style="margin-bottom:8px">Places</div><div id="tr-pick"></div></div>
  <div class="mb">${card("tr-roll", "Rolling mean", "centred, calendar-aware; requires ≥ 70% of days in the window", { tools: seg("tr-win", ["30", "90", "180", "365"], String(S.trendWin), { 30: "30 d", 90: "90 d", 180: "180 d", 365: "1 yr" }) })}</div>
  <div class="grid g2 mb">${card("tr-ann", "Annual mean (complete years)", "years with ≥ 11 complete months")}${card("tr-yoy", "Year-over-year change", "blue = decrease, red = increase")}</div>
  ${section("Long-term trend per place", "deseasonalised monthly anomalies · OLS with Newey–West 95% CI · Benjamini–Hochberg FDR · full data period")}
  <div class="grid g3 mb">
    ${kpi("trends", "Decreasing (q < 0.05)", fmtInt(cnt("decreasing")), `${clear.filter((t) => t.direction === "decreasing" && t.artifact).length} of them artifact-flagged`)}
    ${kpi("trends", "Increasing (q < 0.05)", fmtInt(cnt("increasing")), `${clear.filter((t) => t.direction === "increasing" && t.artifact).length} of them artifact-flagged`)}
    ${kpi("check", "No clear trend", fmtInt(cnt("no clear trend")), `of ${tr.length} places`)}
  </div>
  ${clear.some((t) => t.artifact) ? callout(`<b>Artifact caveat.</b> ${clear.filter((t) => t.artifact).length} of the ${clear.length} “clear” trends belong to places whose modelled series has a fixed annual mean or an abrupt level shift. A straight line fitted across a step describes the step, not gradual change. Use “Exclude artifact places” above to compare.`, "warn") : ""}
  <div class="grid g-1-2 mb">${card("tr-forest", "Largest estimated trends", "blue = decreasing, red = increasing, grey = no clear trend")}${card("tr-map", "Trend map", "µg/m³ per year; grey = no clear trend")}</div>
  <div class="mb">${card("tr-one", "Single-place trend", "", { tools: `<div id="tr-one-pick"></div>` })}</div>
  <div class="card"><div id="tr-table"></div></div>`;

  bandChart("tr-band", nationalMonthly());
  const draw = () => {
    const sel = S.trends.map((l) => sums.find((s) => s.label === l)).filter(Boolean), colors = colorMap(S.trends), mask = dayMask();
    const drawRoll = () => {
      const w = +S.trendWin, half = Math.floor(w / 2);
      plot("tr-roll", sel.map((s) => {
        const full = new Float64Array(D.nD).fill(NaN);
        for (let d = 0; d < D.nD; d++) if (mask[d] && !(F.noOutliers && D.out[s.idx * D.nD + d])) full[d] = pm(s.idx, d);
        const pre = new Float64Array(D.nD + 1), cntA = new Int32Array(D.nD + 1);
        for (let d = 0; d < D.nD; d++) { pre[d + 1] = pre[d] + (isNum(full[d]) ? full[d] : 0); cntA[d + 1] = cntA[d] + (isNum(full[d]) ? 1 : 0); }
        const y = [], x = [];
        for (let d = 0; d < D.nD; d += 3) {
          if (!mask[d]) continue;
          const a = Math.max(0, d - half), b = Math.min(D.nD, d + w - half), n = cntA[b] - cntA[a];
          x.push(D.meta.dates[d]); y.push(n >= Math.floor(w * 0.7) ? (pre[b] - pre[a]) / n : null);
        }
        return { x, y, mode: "lines", name: s.label, line: { color: colors[s.label], width: 2 }, hovertemplate: `<b>${esc(s.label)}</b> %{x}: %{y:.1f}<extra></extra>` };
      }), { shapes: [whoLine()], yaxis: { title: { text: `Rolling mean ${PM}` }, rangemode: "tozero" }, hovermode: "x unified" }, 380);
    };
    drawRoll(); bindSeg("tr-win", (v) => { S.trendWin = +v; drawRoll(); });
    const anns = sel.map((s) => [s, annual(s.idx)]);
    if (anns.every(([, a]) => !a.length)) { empty("tr-ann", "No complete years in this selection."); empty("tr-yoy", "Needs two consecutive complete years."); return; }
    plot("tr-ann", anns.map(([s, a]) => ({ x: a.map((r) => String(r.year)), y: a.map((r) => r.mean), mode: "lines+markers", name: s.label,
      line: { color: colors[s.label], width: 2.2 }, marker: { size: 8 }, hovertemplate: `<b>${esc(s.label)}</b> %{x}: %{y:.1f}<extra></extra>` })),
    { shapes: [whoLine()], yaxis: { title: { text: `Annual mean ${PM}` }, rangemode: "tozero" }, xaxis: { type: "category" } }, 360);
    const years = [...new Set(anns.flatMap(([, a]) => a.map((r) => r.year)))].sort().slice(1);
    const z = anns.map(([, a]) => years.map((y) => { const c = a.find((r) => r.year === y), p = a.find((r) => r.year === y - 1); return c && p ? (100 * (c.mean - p.mean)) / p.mean : null; }));
    const lim = Math.max(1, ...z.flat().filter(isNum).map(Math.abs));
    plot("tr-yoy", [{ type: "heatmap", z, x: years.map(String), y: anns.map(([s]) => s.label), colorscale: div(), zmin: -lim, zmax: lim, xgap: 2, ygap: 2,
      colorbar: { title: { text: "% change" }, thickness: 10 }, hovertemplate: "<b>%{y}</b> %{x} vs previous year: %{z:+.1f}%<extra></extra>" }],
    { yaxis: { autorange: "reversed", showgrid: false } }, 360);
  };
  picker("tr-pick", byPop(sums).map((s) => s.label), S.trends, 8, draw);
  draw();

  const valid = tr.filter((t) => isNum(t.slope_per_year));
  const forest = [...valid].sort((a, b) => a.slope_per_year - b.slope_per_year);
  const pick = [...forest.slice(0, 12), ...forest.slice(-12)].filter((t, i, a) => a.findIndex((u) => u.city_id === t.city_id) === i);
  const col = (t) => (t.direction === "decreasing" ? cat()[0] : t.direction === "increasing" ? cat()[7] : MUTED());
  plot("tr-forest", [{ x: pick.map((t) => t.slope_per_year), y: pick.map((t) => (t.artifact ? "⚠ " : "") + t.city_label), mode: "markers",
    marker: { size: 9, color: pick.map(col), line: { width: 1.5, color: "#fff" } },
    error_x: { type: "data", symmetric: false, array: pick.map((t) => t.ci_high - t.slope_per_year), arrayminus: pick.map((t) => t.slope_per_year - t.ci_low), color: MUTED(), thickness: 1.5, width: 0 },
    customdata: pick.map((t) => [t.ci_low, t.ci_high, t.q_value, t.direction, t.pct_change_per_year]),
    hovertemplate: "<b>%{y}</b><br>%{x:+.2f} µg/m³/yr (%{customdata[4]:+.1f}%/yr)<br>95% CI %{customdata[0]:+.2f} to %{customdata[1]:+.2f}<br>q = %{customdata[2]:.2g} · %{customdata[3]}<extra></extra>" }],
  { shapes: [{ type: "line", yref: "paper", y0: 0, y1: 1, x0: 0, x1: 0, line: { color: MUTED(), width: 1 } }], xaxis: { title: { text: "µg/m³ per year" }, showgrid: true } }, Math.max(420, 20 * pick.length + 80));
  const geo = valid.map((t) => ({ ...t, c: D.byId.get(t.city_id) }));
  const lim = quantileSorted(Float64Array.from(geo.map((t) => Math.abs(t.slope_per_year))).sort(), 0.95) || 1;
  const nc = geo.filter((t) => t.direction === "no clear trend"), cl = geo.filter((t) => t.direction !== "no clear trend");
  plot("tr-map", [
    { type: "scattergeo", lat: nc.map((t) => t.c.latitude), lon: nc.map((t) => t.c.longitude), mode: "markers", name: "No clear trend", marker: { size: 6, color: MUTED() }, text: nc.map((t) => t.city_label), hovertemplate: "<b>%{text}</b><br>no clear trend<extra></extra>" },
    { type: "scattergeo", lat: cl.map((t) => t.c.latitude), lon: cl.map((t) => t.c.longitude), mode: "markers", name: "Clear trend (q < 0.05)", text: cl.map((t) => t.city_label),
      marker: { size: 9, color: cl.map((t) => t.slope_per_year), colorscale: div(), cmin: -lim, cmax: lim, colorbar: { title: { text: "µg/m³/yr" }, thickness: 10 }, line: { width: 0.6, color: "rgba(255,255,255,.7)" } },
      hovertemplate: "<b>%{text}</b><br>%{marker.color:+.2f} µg/m³/yr<extra></extra>" },
  ], geoLayout({ legend: { y: 0.02, x: 0.01, orientation: "v" } }), 460);

  const labels = valid.map((t) => t.city_label);
  if (!labels.includes(S.oneTrend)) S.oneTrend = [...valid].sort((a, b) => Math.abs(b.slope_per_year) - Math.abs(a.slope_per_year))[0]?.city_label;
  const drawOne = () => {
    const t = valid.find((x) => x.city_label === S.oneTrend);
    const c = D.byId.get(t.city_id), all = new Uint8Array(D.nD).fill(1), m = monthly(c.idx, all);
    const clim = MONTHS.map((_, mi) => mean(m.mean.filter((v, p) => +D.periods[p].slice(5, 7) === mi + 1 && isNum(v))));
    const xs = [], an = [];
    m.mean.forEach((v, p) => { if (isNum(v)) { xs.push(D.periods[p]); an.push(v - clim[+D.periods[p].slice(5, 7) - 1]); } });
    const f = t.fit, yrs = xs.map((x) => (Date.parse(x) - Date.parse("2000-01-01")) / 864e5 / 365.25);
    const fit = f ? yrs.map((u) => f.a + f.b * u) : [], se = f ? yrs.map((u) => Math.sqrt(f.vaa + u * u * f.vbb + 2 * u * f.vab)) : [];
    plot("tr-one", [
      { type: "bar", x: xs, y: an, name: "Monthly anomaly", marker: { color: an.map((v) => (v >= 0 ? "#ec8a89" : "#6da7ec")) }, hovertemplate: "%{x|%b %Y}: %{y:+.1f} µg/m³<extra></extra>" },
      ...(f ? [
        { x: xs, y: fit.map((v, i) => v + 1.96 * se[i]), mode: "lines", line: { width: 0 }, hoverinfo: "skip", showlegend: false },
        { x: xs, y: fit.map((v, i) => v - 1.96 * se[i]), mode: "lines", line: { width: 0 }, fill: "tonexty", fillcolor: "rgba(120,120,120,0.22)", name: "95% CI (Newey–West)", hoverinfo: "skip" },
        { x: xs, y: fit, mode: "lines", name: "Linear trend", line: { color: getComputedStyle(document.documentElement).getPropertyValue("--ink"), width: 2.2 }, hovertemplate: "trend %{y:+.1f}<extra></extra>" }] : []),
    ], { bargap: 0.1, yaxis: { title: { text: "Anomaly vs typical month (µg/m³)" }, zeroline: true }, annotations: [{ xref: "paper", yref: "paper", x: 0, y: 1.08, showarrow: false, xanchor: "left",
      text: `slope ${signed(t.slope_per_year)} µg/m³/yr (95% CI ${signed(t.ci_low)} to ${signed(t.ci_high)}) · Theil–Sen ${signed(t.theil_sen_slope)} · ${pEq(t.q_value, "q")}${t.artifact ? " · ⚠ " + t.reason : ""}`, font: { size: 11.5 } }],
      margin: { t: 34 } }, 400);
  };
  citySelect("tr-one-pick", labels, S.oneTrend, (v) => { S.oneTrend = v; drawOne(); });
  drawOne();
  table("tr-table", tr, [{ key: "city_label", label: "Place" }, { key: "n", label: "Months", num: true },
    { key: "mean_level", label: "Mean level", num: true, fmt: (v) => fmt(v) }, { key: "slope_per_year", label: "Slope µg/m³/yr", num: true, fmt: (v) => signed(v) },
    { key: "ci_low", label: "CI low", num: true, fmt: (v) => signed(v) }, { key: "ci_high", label: "CI high", num: true, fmt: (v) => signed(v) },
    { key: "pct_change_per_year", label: "%/yr", num: true, fmt: (v) => signed(v, 1) }, { key: "theil_sen_slope", label: "Theil–Sen", num: true, fmt: (v) => signed(v) },
    { key: "q_value", label: "q (FDR)", num: true, fmt: fmtP }, { key: "direction", label: "Direction" }, { key: "reason", label: "Artifact flag" }],
  { name: "place_trends", sortKey: "slope_per_year", desc: false });
}

// ===================================================================================
export function seasonal(root) {
  const sums = citySummaries();
  if (!sums.length) return noData(root);
  ensurePick("seasonal", 5);
  const mask = dayMask();
  root.innerHTML = `
  <div class="mb">${card("se-heat", "Median PM2.5 by month and place", "median of all daily values in each calendar month",
    { tools: seg("se-mode", ["pop", "high", "low"], S.heatMode, { pop: "Most populous", high: "Highest", low: "Lowest" }) + seg("se-n", ["10", "20", "40"], String(S.heatN)) })}</div>
  <div class="grid g2 mb">${card("se-box", "Daily PM2.5 by season", "Winter Dec–Feb · Spring Mar–Apr · Pre-monsoon May–Jun · Monsoon Jul–Sep · Post-monsoon Oct–Nov")}${card("se-prof", "Month-of-year profile, all filtered places", "pooled median with inter-quartile band")}</div>
  <div class="card mb"><div class="card-t" style="margin-bottom:8px">Profiles for selected places</div><div id="se-pick"></div><div class="chart" id="se-prof2" style="margin-top:10px"></div></div>
  ${section("Seasonal summary by province")}
  <div class="card mb"><div id="se-table"></div></div>
  ${section("Weekday vs weekend", "Saturday–Sunday weekend")}
  <div class="grid g-2-1 mb">${card("se-wd", "Mean PM2.5 by day of week", "orange = weekend")}<div class="card" id="se-wdtest"></div></div>
  ${section("Hour-of-day profile", "Kaggle/HF hourly source only — the World Bank data are daily")}
  <div id="se-hour"></div>`;

  const drawHeat = () => {
    let order = [...sums];
    if (S.heatMode === "pop") order.sort((a, b) => b.pop - a.pop); else if (S.heatMode === "high") order.sort((a, b) => b.median - a.median); else order.sort((a, b) => a.median - b.median);
    order = order.slice(0, +S.heatN);
    const z = order.map((s) => {
      const by = MONTHS.map(() => []);
      for (let d = 0; d < D.nD; d++) if (mask[d] && !(F.noOutliers && D.out[s.idx * D.nD + d])) by[D.month[d] - 1].push(pm(s.idx, d));
      return by.map((a) => (a.length ? quantileSorted(Float64Array.from(a).sort(), 0.5) : null));
    });
    plot("se-heat", [{ type: "heatmap", z, x: MONTHS, y: order.map((s) => s.label), colorscale: seq(), xgap: 2, ygap: 2, colorbar: { title: { text: "µg/m³" }, thickness: 10 },
      hovertemplate: "<b>%{y}</b> · %{x}<br>median %{z:.1f} µg/m³<extra></extra>" }], { yaxis: { autorange: "reversed", showgrid: false } }, Math.max(320, 20 * order.length + 80));
  };
  drawHeat();
  bindSeg("se-mode", (v) => { S.heatMode = v; drawHeat(); });
  bindSeg("se-n", (v) => { S.heatN = +v; drawHeat(); });
  seasonBox("se-box", pooledBySeason());

  const pooledMonth = MONTHS.map(() => []), dow = Array.from({ length: 7 }, () => [0, 0]);
  const provSeason = new Map();
  for (const s of sums) for (let d = 0; d < D.nD; d++) {
    if (!mask[d] || (F.noOutliers && D.out[s.idx * D.nD + d])) continue;
    const v = pm(s.idx, d);
    pooledMonth[D.month[d] - 1].push(v); dow[D.dow[d]][0] += v; dow[D.dow[d]][1]++;
    const k = s.province + "|" + D.SEASONS[D.season[d]]; if (!provSeason.has(k)) provSeason.set(k, []); provSeason.get(k).push(v);
  }
  const pq = pooledMonth.map((a) => { const s2 = Float64Array.from(a).sort(); return [quantileSorted(s2, 0.25), quantileSorted(s2, 0.5), quantileSorted(s2, 0.75), a.length]; });
  plot("se-prof", [
    { x: MONTHS, y: pq.map((p) => p[2]), mode: "lines", line: { width: 0 }, hoverinfo: "skip", showlegend: false },
    { x: MONTHS, y: pq.map((p) => p[0]), mode: "lines", line: { width: 0 }, fill: "tonexty", fillcolor: "rgba(42,120,214,0.2)", name: "IQR", hoverinfo: "skip" },
    { x: MONTHS, y: pq.map((p) => p[1]), mode: "lines+markers", name: "Median", line: { color: cat()[0], width: 2.4 }, marker: { size: 7 }, customdata: pq.map((p) => p[3]),
      hovertemplate: "%{x}: %{y:.1f} µg/m³<br>n = %{customdata:,}<extra></extra>" },
  ], { shapes: [whoLine()], yaxis: { title: { text: `Median daily ${PM}` }, rangemode: "tozero" } }, 360);

  const drawProf = () => {
    const colors = colorMap(S.seasonal);
    plot("se-prof2", S.seasonal.map((l) => sums.find((s) => s.label === l)).filter(Boolean).map((s) => {
      const by = MONTHS.map(() => []);
      for (let d = 0; d < D.nD; d++) if (mask[d] && !(F.noOutliers && D.out[s.idx * D.nD + d])) by[D.month[d] - 1].push(pm(s.idx, d));
      return { x: MONTHS, y: by.map((a) => (a.length ? quantileSorted(Float64Array.from(a).sort(), 0.5) : null)), mode: "lines+markers", name: s.label,
        line: { color: colors[s.label], width: 2.2 }, marker: { size: 7 }, hovertemplate: `<b>${esc(s.label)}</b> %{x}: %{y:.1f}<extra></extra>` };
    }), { shapes: [whoLine()], yaxis: { title: { text: `Median daily ${PM}` }, rangemode: "tozero" } }, 360);
  };
  picker("se-pick", byPop(sums).map((s) => s.label), S.seasonal, 8, drawProf);
  drawProf();

  const rows = [...provSeason].map(([k, v]) => { const [prov, season] = k.split("|"); const s2 = Float64Array.from(v).sort();
    return { province: prov, season, n: v.length, mean: mean(v), median: quantileSorted(s2, 0.5), p25: quantileSorted(s2, 0.25), p75: quantileSorted(s2, 0.75) }; })
    .sort((a, b) => a.province.localeCompare(b.province) || D.SEASONS.indexOf(a.season) - D.SEASONS.indexOf(b.season));
  table("se-table", rows, [{ key: "province", label: "Province" }, { key: "season", label: "Season" }, { key: "n", label: "City-days", num: true, fmt: fmtInt },
    { key: "mean", label: "Mean", num: true, fmt: (v) => fmt(v) }, { key: "median", label: "Median", num: true, fmt: (v) => fmt(v) },
    { key: "p25", label: "P25", num: true, fmt: (v) => fmt(v) }, { key: "p75", label: "P75", num: true, fmt: (v) => fmt(v) }], { name: "seasonal_by_province", search: false, sortKey: null });

  const DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
  const wm = dow.map(([s, n]) => (n ? s / n : null));
  plot("se-wd", [{ type: "bar", x: DAYS, y: wm, marker: { color: DAYS.map((_, i) => (i >= 5 ? cat()[1] : cat()[0])), cornerradius: 4 },
    customdata: dow.map((d) => d[1]), hovertemplate: "%{x}: %{y:.2f} µg/m³<br>n = %{customdata:,}<extra></extra>" }],
  { yaxis: { title: { text: `Mean ${PM}` }, rangemode: "tozero" } }, 320);
  const wt = D.analysis.tests_all.find((t) => t.name.startsWith("Weekday"));
  document.getElementById("se-wdtest").innerHTML = `<div class="card-t">${esc(wt.name)}</div><div class="card-s">full period · one value per distinct model series</div>
    <p style="font-size:13.5px">${esc(wt.interpretation)}</p><ul class="caveats" style="padding-left:16px">${wt.caveats.slice(2).map((c) => `<li>${esc(c)}</li>`).join("")}</ul>`;

  const H = D.hourly, hEl = document.getElementById("se-hour");
  if (!H || !H.profiles) { hEl.innerHTML = callout("No genuinely hourly dataset is available.", "warn"); return; }
  const al = H.alignment;
  hEl.innerHTML = callout(`<b>Timestamp caveat.</b> In this file ozone peaks at hour label <b>${al.pollutant_peak_hour}</b> while temperature peaks at <b>${al.weather_peak_hour}</b> (${signed(al.offset_hours, 0)} h). Both normally peak in the early-to-mid afternoon, so pollutant hours appear to be UTC (hour ${al.pollutant_peak_hour} UTC = ${(al.pollutant_peak_hour + 5) % 24}:00 PKT) while weather hours appear to be local. Hours are shown as labelled. Covers ${H.start} → ${H.end} only. Licence of this dataset is unknown.`, "warn")
    + card("se-hour-c", "Hour-of-day profile (mean)", "Kaggle/HF hourly dataset — modelled (probable CAMS)", { tools: seg("se-pol", H.pollutants, "pm25", D.meta.labels) });
  const drawHour = (p) => {
    const P = H.profiles[p], colors = colorMap(P.cities);
    plot("se-hour-c", P.cities.map((c, i) => ({ x: Array.from({ length: 24 }, (_, h) => h), y: P.values[i], mode: "lines", name: c, line: { color: colors[c], width: 2 },
      hovertemplate: `<b>${esc(c)}</b> hour %{x}: %{y:.1f}<extra></extra>` })),
    { xaxis: { title: { text: "Hour label in source file" }, dtick: 3 }, yaxis: { title: { text: `Mean ${D.meta.labels[p]} (µg/m³)` }, rangemode: "tozero" }, hovermode: "x unified" }, 380);
  };
  drawHour("pm25"); bindSeg("se-pol", drawHour);
}
