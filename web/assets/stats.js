// Small numeric helpers. Quantiles use linear interpolation (numpy default), matching the Python code.

export const isNum = (v) => v !== null && v !== undefined && Number.isFinite(v);

export function sorted(arr) {
  const a = Float64Array.from(arr.filter ? arr.filter(isNum) : arr);
  return a.sort();
}

export function quantileSorted(s, q) {
  const n = s.length;
  if (!n) return NaN;
  const pos = (n - 1) * q, lo = Math.floor(pos), hi = Math.ceil(pos);
  return s[lo] + (s[hi] - s[lo]) * (pos - lo);
}

export function mean(a) {
  let s = 0, n = 0;
  for (const v of a) if (Number.isFinite(v)) { s += v; n++; }
  return n ? s / n : NaN;
}

export function median(a) { return quantileSorted(sorted(Array.from(a)), 0.5); }

export function boxStats(s) {
  // s must be sorted. Tukey whiskers: most extreme points within 1.5×IQR.
  if (!s.length) return null;
  const q1 = quantileSorted(s, 0.25), q3 = quantileSorted(s, 0.75), med = quantileSorted(s, 0.5);
  const iqr = q3 - q1, lo = q1 - 1.5 * iqr, hi = q3 + 1.5 * iqr;
  let lf = s[0], uf = s[s.length - 1];
  for (let i = 0; i < s.length; i++) if (s[i] >= lo) { lf = s[i]; break; }
  for (let i = s.length - 1; i >= 0; i--) if (s[i] <= hi) { uf = s[i]; break; }
  let sum = 0; for (const v of s) sum += v;
  return { q1, median: med, q3, lowerfence: lf, upperfence: uf, mean: sum / s.length, n: s.length };
}

export function histogram(values, nbins = 60, log = false) {
  const v = [];
  for (const x of values) if (Number.isFinite(x) && (!log || x > 0)) v.push(log ? Math.log10(x) : x);
  if (!v.length) return null;
  let mn = Infinity, mx = -Infinity;
  for (const x of v) { if (x < mn) mn = x; if (x > mx) mx = x; }
  if (mx === mn) mx = mn + 1;
  const w = (mx - mn) / nbins, counts = new Array(nbins).fill(0);
  for (const x of v) counts[Math.min(nbins - 1, Math.floor((x - mn) / w))]++;
  const edges = Array.from({ length: nbins + 1 }, (_, i) => mn + i * w);
  return { counts, edges, n: v.length };
}

function ranks(a) {
  const idx = a.map((v, i) => [v, i]).sort((x, y) => x[0] - y[0]);
  const r = new Array(a.length);
  for (let i = 0; i < idx.length;) {
    let j = i;
    while (j + 1 < idx.length && idx[j + 1][0] === idx[i][0]) j++;
    const avg = (i + j) / 2 + 1;
    for (let k = i; k <= j; k++) r[idx[k][1]] = avg;
    i = j + 1;
  }
  return r;
}

export function pearson(x, y) {
  const n = x.length;
  if (n < 3) return NaN;
  const mx = mean(x), my = mean(y);
  let sxy = 0, sxx = 0, syy = 0;
  for (let i = 0; i < n; i++) { const dx = x[i] - mx, dy = y[i] - my; sxy += dx * dy; sxx += dx * dx; syy += dy * dy; }
  return sxy / Math.sqrt(sxx * syy);
}

export function spearman(x, y) {
  const px = [], py = [];
  for (let i = 0; i < x.length; i++) if (Number.isFinite(x[i]) && Number.isFinite(y[i])) { px.push(x[i]); py.push(y[i]); }
  return { r: pearson(ranks(px), ranks(py)), n: px.length };
}

export function lag1(a) {
  const v = a.filter(Number.isFinite);
  if (v.length < 3) return NaN;
  return pearson(v.slice(0, -1), v.slice(1));
}

export const fmt = (v, d = 1) => (isNum(v) ? Number(v).toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d }) : "—");
export const fmtInt = (v) => (isNum(v) ? Math.round(v).toLocaleString("en-US") : "—");
export const fmtP = (p) => (!isNum(p) ? "—" : p < 0.001 ? p.toExponential(2) : p.toFixed(3));
export const signed = (v, d = 2) => (isNum(v) ? (v > 0 ? "+" : "") + v.toFixed(d) : "—");
