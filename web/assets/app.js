// App shell: navigation, global filters, theme and routing.

import { D, F, loadAll, SEASON_LIST } from "./data.js";
import { PAGES } from "./pages.js";

export const ICONS = {
  overview: '<path d="M3 13h8V3H3zM13 21h8V11h-8zM3 21h8v-6H3zM13 3v6h8V3z"/>',
  explorer: '<circle cx="12" cy="10" r="3"/><path d="M12 21s-7-6.2-7-11a7 7 0 0 1 14 0c0 4.8-7 11-7 11z"/>',
  compare: '<path d="M8 3 4 7l4 4M4 7h16M16 21l4-4-4-4M20 17H4"/>',
  trends: '<path d="M3 17l6-6 4 4 8-8"/><path d="M14 7h7v7"/>',
  seasonal: '<rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/>',
  weather: '<path d="M14 14.76V3.5a2.5 2.5 0 0 0-5 0v11.26a4.5 4.5 0 1 0 5 0z"/>',
  dist: '<path d="M3 3v18h18"/><rect x="7" y="12" width="3" height="6"/><rect x="12" y="7" width="3" height="11"/><rect x="17" y="10" width="3" height="8"/>',
  stats: '<path d="M18 4H6l6 8-6 8h12"/>',
  quality: '<path d="M9 11l3 3L22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/>',
  method: '<path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/>',
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
  moon: '<path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/>',
  download: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3"/>',
  city: '<path d="M3 21h18M5 21V7l7-4v18M19 21V11l-7-4"/>',
  calendar: '<rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/>',
  rows: '<path d="M3 3h18v18H3zM3 9h18M3 15h18"/>',
  gauge: '<path d="M12 14l4-4"/><path d="M3.3 19a10 10 0 1 1 17.4 0"/>',
  pin: '<path d="M12 2l3 7h7l-5.5 4.5L18 21l-6-4-6 4 1.5-7.5L2 9h7z"/>',
  check: '<path d="M20 6 9 17l-5-5"/>',
  layers: '<path d="m12 2 10 5-10 5L2 7z"/><path d="m2 17 10 5 10-5M2 12l10 5 10-5"/>',
};
export const icon = (k) => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${ICONS[k] || ""}</svg>`;

const NAV = [
  ["Overview", [["overview", "Executive Overview", "overview"], ["explorer", "City Explorer", "explorer"], ["compare", "City Comparison", "compare"]]],
  ["Analysis", [["trends", "Historical Trends", "trends"], ["seasonal", "Seasonal Analysis", "seasonal"], ["weather", "Weather & Pollution", "weather"],
    ["distributions", "Pollutant Distributions", "dist"], ["statistics", "Statistical Analysis", "stats"]]],
  ["Data", [["quality", "Data Quality & Coverage", "quality"], ["methodology", "Methodology & Sources", "method"]]],
];
const TITLES = Object.fromEntries(NAV.flatMap(([, items]) => items.map(([k, t]) => [k, t])));

function renderNav(active) {
  const qs = location.hash.includes("?") ? "?" + location.hash.split("?")[1] : ""; // keep filters across pages
  document.getElementById("nav").innerHTML = NAV.map(([g, items]) => `
    <div class="nav-group"><div class="nav-label">${g}</div>
      ${items.map(([k, t, ic]) => `<a class="nav-item ${k === active ? "active" : ""}" href="#/${k}${qs}">${icon(ic)}<span>${t}</span></a>`).join("")}
    </div>`).join("");
}

// ---------------- filters ----------------
const dIdx = (s) => { const i = D.meta.dates.findIndex((d) => d >= s); return i < 0 ? D.nD - 1 : i; };
const dIdxEnd = (s) => { let i = -1; D.meta.dates.forEach((d, k) => { if (d <= s) i = k; }); return Math.max(i, 0); };

function readHashFilters() {
  const q = new URLSearchParams(location.hash.split("?")[1] || "");
  F.start = q.get("from") ? dIdx(q.get("from")) : 0;
  F.end = q.get("to") ? dIdxEnd(q.get("to")) : D.nD - 1;
  F.provinces = new Set(q.get("prov") ? q.get("prov").split("~") : []);
  F.seasons = new Set(q.get("season") ? q.get("season").split("~") : []);
  F.noOutliers = q.get("noout") === "1";
  F.noArtifacts = q.get("noart") === "1";
}
export function writeHash(page = currentPage()) {
  const q = new URLSearchParams();
  if (F.start > 0) q.set("from", D.meta.dates[F.start]);
  if (F.end < D.nD - 1) q.set("to", D.meta.dates[F.end]);
  if (F.provinces.size) q.set("prov", [...F.provinces].join("~"));
  if (F.seasons.size) q.set("season", [...F.seasons].join("~"));
  if (F.noOutliers) q.set("noout", "1");
  if (F.noArtifacts) q.set("noart", "1");
  const s = q.toString();
  history.replaceState(null, "", `#/${page}${s ? "?" + s : ""}`);
}
const currentPage = () => (location.hash.replace(/^#\//, "").split("?")[0] || "overview");

function renderFilters() {
  const nArt = D.cities.filter((c) => c.artifact_flag).length;
  const el = document.getElementById("filters");
  el.innerHTML = `
    <div class="f-field"><label>From</label><input type="date" id="f-from" min="${D.meta.dates[0]}" max="${D.meta.dates[D.nD - 1]}" value="${D.meta.dates[F.start]}"></div>
    <div class="f-field"><label>To</label><input type="date" id="f-to" min="${D.meta.dates[0]}" max="${D.meta.dates[D.nD - 1]}" value="${D.meta.dates[F.end]}">
      <button class="preset" data-preset="all">All</button><button class="preset" data-preset="full">2019–25</button><button class="preset" data-preset="last1">12 mo</button></div>
    <div class="f-field"><label>Province</label><div class="chipset">${D.provinces.map((p) =>
      `<button class="chip ${F.provinces.has(p) ? "on" : ""}" data-prov="${p}">${p.replace(" Capital Territory", " CT").replace("Khyber Pakhtunkhwa", "KP")}</button>`).join("")}</div></div>
    <div class="f-field"><label>Season</label><div class="chipset">${SEASON_LIST.map((s) =>
      `<button class="chip ${F.seasons.has(s) ? "on" : ""}" data-season="${s}">${s}</button>`).join("")}</div></div>
    <label class="toggle" title="Robust z-score > ${D.meta.rules.outlier_z} on log PM2.5 within city"><input type="checkbox" id="f-out" ${F.noOutliers ? "checked" : ""}><span class="sw"></span>Exclude outliers</label>
    <label class="toggle" title="Places with a fixed annual mean (≥3 yrs) or an abrupt level shift in the modelled series"><input type="checkbox" id="f-art" ${F.noArtifacts ? "checked" : ""}><span class="sw"></span>Exclude artifact places (${nArt})</label>`;
  el.querySelector("#f-from").onchange = (e) => { F.start = Math.min(dIdx(e.target.value), F.end); apply(); };
  el.querySelector("#f-to").onchange = (e) => { F.end = Math.max(dIdxEnd(e.target.value), F.start); apply(); };
  el.querySelectorAll("[data-preset]").forEach((b) => b.onclick = () => {
    const p = b.dataset.preset;
    if (p === "all") { F.start = 0; F.end = D.nD - 1; }
    if (p === "full") { F.start = dIdx("2019-01-01"); F.end = dIdxEnd("2025-12-31"); }
    if (p === "last1") { F.end = D.nD - 1; const t = new Date(D.ts[F.end]); t.setUTCFullYear(t.getUTCFullYear() - 1); F.start = dIdx(t.toISOString().slice(0, 10)); }
    apply();
  });
  el.querySelectorAll("[data-prov]").forEach((b) => b.onclick = () => { toggleSet(F.provinces, b.dataset.prov); apply(); });
  el.querySelectorAll("[data-season]").forEach((b) => b.onclick = () => { toggleSet(F.seasons, b.dataset.season); apply(); });
  el.querySelector("#f-out").onchange = (e) => { F.noOutliers = e.target.checked; apply(); };
  el.querySelector("#f-art").onchange = (e) => { F.noArtifacts = e.target.checked; apply(); };
  document.getElementById("active-filters").textContent = filterSummary();
}
const toggleSet = (s, v) => (s.has(v) ? s.delete(v) : s.add(v));
export function filterSummary() {
  const p = [`${D.meta.dates[F.start]} → ${D.meta.dates[F.end]}`, F.provinces.size ? [...F.provinces].join(", ") : "all provinces",
    F.seasons.size ? [...F.seasons].join(", ") : "all seasons"];
  if (F.noOutliers) p.push("outliers excluded");
  if (F.noArtifacts) p.push("artifact places excluded");
  return "Showing: " + p.join(" · ");
}

function apply() { writeHash(); renderFilters(); route(); }

// ---------------- theme ----------------
function setThemeIcon() {
  const dark = document.documentElement.dataset.theme === "dark" ||
    (!document.documentElement.dataset.theme && matchMedia("(prefers-color-scheme: dark)").matches);
  document.getElementById("theme-btn").innerHTML = icon(dark ? "sun" : "moon");
  return dark;
}
function bindTheme() {
  setThemeIcon();
  document.getElementById("theme-btn").onclick = () => {
    const dark = setThemeIcon();
    document.documentElement.dataset.theme = dark ? "light" : "dark";
    try { localStorage.setItem("pea-theme", document.documentElement.dataset.theme); } catch (e) {}
    setThemeIcon();
    route();
  };
}

// ---------------- routing ----------------
let rendering = false;
function route() {
  if (!D.ready || rendering) return;
  rendering = true;
  const page = PAGES[currentPage()] ? currentPage() : "overview";
  renderNav(page);
  document.getElementById("page-title").textContent = TITLES[page];
  document.title = `${TITLES[page]} · Pakistan Environmental Analytics`;
  const content = document.getElementById("content");
  content.innerHTML = "";
  content.classList.remove("fade-in"); void content.offsetWidth; content.classList.add("fade-in");
  try { PAGES[page](content); }
  catch (e) { console.error(e); content.innerHTML = `<div class="callout warn">This view could not be rendered: ${e.message}</div>`; }
  document.getElementById("sidebar").classList.remove("open");
  rendering = false;
}

async function boot() {
  bindTheme();
  document.getElementById("menu-btn").onclick = () => document.getElementById("sidebar").classList.toggle("open");
  try {
    await loadAll((f) => { document.getElementById("load-msg").textContent = `Loading datasets… ${Math.round(f * 100)}%`; });
    await new Promise((r) => (window.Plotly ? r() : window.addEventListener("load", r)));
  } catch (e) {
    document.getElementById("content").innerHTML = `<div class="callout warn">Failed to load data: ${e.message}</div>`;
    return;
  }
  readHashFilters();
  renderFilters();
  document.getElementById("side-foot").innerHTML = `<b>${D.nC} places</b> · ${D.meta.dates[0]} → ${D.meta.dates[D.nD - 1]}<br>
    Data prepared ${D.meta.prepared.slice(0, 10)}<br>All PM2.5 values are model estimates.`;
  window.addEventListener("hashchange", () => { readHashFilters(); renderFilters(); route(); });
  matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => { setThemeIcon(); route(); });
  route();
}
boot();
