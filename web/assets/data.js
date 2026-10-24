// Data loading and the client-side analysis engine.
// Aggregation rules mirror src/data/transform.py: monthly mean needs >= 20 valid days,
// annual mean is the mean of complete monthly means and needs >= 11 complete months.

import { boxStats, quantileSorted } from "./stats.js";

export const D = { ready: false };
const SEASONS = ["Winter", "Spring", "Pre-monsoon", "Monsoon", "Post-monsoon"];
const SEASON_OF_MONTH = [null, 0, 0, 1, 1, 2, 2, 3, 3, 3, 4, 4, 0]; // index by month 1..12

async function json(name) {
  const r = await fetch(`data/${name}`);
  if (!r.ok) throw new Error(`Failed to load ${name} (${r.status})`);
  return r.json();
}
async function bin(name, Type) {
  const r = await fetch(`data/${name}`);
  if (!r.ok) throw new Error(`Failed to load ${name} (${r.status})`);
  return new Type(await r.arrayBuffer());
}

export async function loadAll(onProgress = () => {}) {
  const steps = [
    ["meta", () => json("meta.json")], ["cities", () => json("cities.json")],
    ["pm", () => bin("pm25.bin", Uint16Array)], ["outliers", () => json("outliers.json")],
    ["wx", () => bin("weather.bin", Int16Array)], ["analysis", () => json("analysis.json")],
    ["hourly", () => json("hourly.json")], ["docs", () => json("docs.json")],
  ];
  let done = 0;
  await Promise.all(steps.map(async ([k, f]) => { D[k] = await f(); onProgress(++done / steps.length); }));
  prepare();
  D.ready = true;
}

function prepare() {
  const dates = D.meta.dates;
  D.nD = dates.length;
  D.nC = D.cities.length;
  D.SEASONS = SEASONS;
  D.year = new Int16Array(D.nD); D.month = new Int8Array(D.nD); D.season = new Int8Array(D.nD);
  D.dow = new Int8Array(D.nD); D.period = new Int16Array(D.nD); D.ts = new Float64Array(D.nD);
  const y0 = +dates[0].slice(0, 4), m0 = +dates[0].slice(5, 7);
  dates.forEach((s, i) => {
    const y = +s.slice(0, 4), m = +s.slice(5, 7), dt = new Date(s + "T00:00:00Z");
    D.year[i] = y; D.month[i] = m; D.season[i] = SEASON_OF_MONTH[m];
    D.dow[i] = (dt.getUTCDay() + 6) % 7; // Monday = 0
    D.period[i] = (y - y0) * 12 + (m - m0); D.ts[i] = dt.getTime();
  });
  D.nP = D.period[D.nD - 1] + 1;
  D.periods = Array.from({ length: D.nP }, (_, p) => {
    const t = new Date(Date.UTC(y0, m0 - 1 + p, 1));
    return t.toISOString().slice(0, 10);
  });
  D.out = new Uint8Array(D.nC * D.nD);
  for (const [c, d] of D.outliers) D.out[c * D.nD + d] = 1;
  D.byId = new Map(D.cities.map((c) => [c.city_id, c]));
  D.wxIndex = new Map(D.meta.weather_city_ids.map((id, i) => [id, i]));
  D.provinces = [...new Set(D.cities.map((c) => c.province))].sort();
}

export const pm = (c, d) => D.pm[c * D.nD + d] / 10;
export function wx(cityId, varName, d) {
  const i = D.wxIndex.get(cityId);
  if (i === undefined) return NaN;
  const j = D.meta.weather_vars.indexOf(varName);
  return D.wx[(i * D.meta.weather_vars.length + j) * D.nD + d] / 10;
}

// ---------------------------------------------------------------------------
// Filter state
// ---------------------------------------------------------------------------
export const F = { start: 0, end: 0, provinces: new Set(), seasons: new Set(), noOutliers: false, noArtifacts: false };
let cacheKey = "", cache = {};
export function filterKey() {
  return [F.start, F.end, [...F.provinces].sort().join(","), [...F.seasons].sort().join(","), F.noOutliers, F.noArtifacts].join("|");
}
function memo(name, fn) {
  const k = filterKey();
  if (k !== cacheKey) { cacheKey = k; cache = {}; }
  if (!(name in cache)) cache[name] = fn();
  return cache[name];
}

export function dayMask() {
  return memo("dayMask", () => {
    const m = new Uint8Array(D.nD);
    for (let d = F.start; d <= F.end; d++) m[d] = F.seasons.size === 0 || F.seasons.has(SEASONS[D.season[d]]) ? 1 : 0;
    return m;
  });
}
export function cityList() {
  return memo("cityList", () => D.cities.filter((c) =>
    (F.provinces.size === 0 || F.provinces.has(c.province)) && (!F.noArtifacts || !c.artifact_flag)).map((c) => c.idx));
}
export const included = (c, d, mask) => mask[d] && !(F.noOutliers && D.out[c * D.nD + d]);

export function cityValues(c, mask = dayMask()) {
  const out = [];
  const base = c * D.nD;
  for (let d = 0; d < D.nD; d++) if (mask[d] && !(F.noOutliers && D.out[base + d])) out.push(D.pm[base + d] / 10);
  return out;
}

export function citySummaries() {
  return memo("summaries", () => {
    const mask = dayMask(), who = D.meta.rules.who_24h;
    return cityList().map((ci) => {
      const v = Float64Array.from(cityValues(ci, mask)).sort();
      const c = D.cities[ci];
      let sum = 0, above = 0;
      for (const x of v) { sum += x; if (x > who) above++; }
      return {
        idx: ci, city_id: c.city_id, label: c.city_label, province: c.province, lat: c.latitude, lon: c.longitude,
        pop: c.population, n: v.length, mean: v.length ? sum / v.length : NaN, median: quantileSorted(v, 0.5),
        p5: quantileSorted(v, 0.05), p25: quantileSorted(v, 0.25), p75: quantileSorted(v, 0.75),
        p95: quantileSorted(v, 0.95), max: v.length ? v[v.length - 1] : NaN, min: v.length ? v[0] : NaN,
        pctAbove: v.length ? (100 * above) / v.length : NaN, artifact: c.artifact_flag, reason: c.artifact_reason,
      };
    }).filter((s) => s.n > 0);
  });
}

export function monthly(ci, mask = dayMask()) {
  const sum = new Float64Array(D.nP), n = new Int32Array(D.nP), base = ci * D.nD;
  for (let d = 0; d < D.nD; d++) {
    if (!mask[d] || (F.noOutliers && D.out[base + d])) continue;
    sum[D.period[d]] += D.pm[base + d] / 10; n[D.period[d]]++;
  }
  const mean = Array.from(sum, (s, p) => (n[p] >= D.meta.rules.min_days_per_month ? s / n[p] : NaN));
  return { mean, n: Array.from(n) };
}

export function annual(ci, mask = dayMask()) {
  const m = monthly(ci, mask), acc = new Map();
  m.mean.forEach((v, p) => {
    if (!Number.isFinite(v)) return;
    const y = +D.periods[p].slice(0, 4);
    const a = acc.get(y) || [0, 0]; a[0] += v; a[1]++; acc.set(y, a);
  });
  const out = [];
  for (const [y, [s, k]] of [...acc].sort((a, b) => a[0] - b[0])) {
    if (k >= D.meta.rules.min_months_per_year) out.push({ year: y, mean: s / k, months: k });
  }
  return out;
}

export function nationalMonthly() {
  return memo("national", () => {
    const rows = cityList().map((ci) => monthly(ci).mean);
    return D.periods.map((p, i) => {
      const v = Float64Array.from(rows.map((r) => r[i]).filter(Number.isFinite)).sort();
      return { period: p, n: v.length, p05: quantileSorted(v, 0.05), p25: quantileSorted(v, 0.25),
        p50: quantileSorted(v, 0.5), p75: quantileSorted(v, 0.75), p95: quantileSorted(v, 0.95) };
    }).filter((r) => r.n > 0);
  });
}

export function pooledBySeason() {
  return memo("seasonBox", () => {
    const mask = dayMask(), buckets = SEASONS.map(() => []);
    for (const ci of cityList()) {
      const base = ci * D.nD;
      for (let d = 0; d < D.nD; d++) if (mask[d] && !(F.noOutliers && D.out[base + d])) buckets[D.season[d]].push(D.pm[base + d] / 10);
    }
    return SEASONS.map((s, i) => ({ season: s, ...(boxStats(Float64Array.from(buckets[i]).sort()) || { n: 0 }) }));
  });
}

export function pooledValues() {
  return memo("pooled", () => {
    const mask = dayMask(), out = [];
    for (const ci of cityList()) {
      const base = ci * D.nD;
      for (let d = 0; d < D.nD; d++) if (mask[d] && !(F.noOutliers && D.out[base + d])) out.push(D.pm[base + d] / 10);
    }
    return out;
  });
}

export function cityByLabel(label) { return D.cities.find((c) => c.city_label === label); }
export const SEASON_LIST = SEASONS;
