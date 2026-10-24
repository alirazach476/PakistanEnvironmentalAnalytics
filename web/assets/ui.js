// Reusable UI building blocks.

import { icon } from "./app.js";
import { colorMap } from "./charts.js";

export const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

export function card(id, title, sub = "", { tools = "", span = "", height = null, body = null } = {}) {
  return `<section class="card ${span}">
    <div class="card-h"><div><div class="card-t">${title}</div>${sub ? `<div class="card-s">${sub}</div>` : ""}</div>
      ${tools ? `<div class="card-tools">${tools}</div>` : ""}</div>
    ${body ?? `<div class="chart" id="${id}" ${height ? `style="min-height:${height}px"` : ""}></div>`}
  </section>`;
}

export function kpi(ic, label, value, note = "", sparkId = "") {
  return `<div class="kpi"><div class="k-top"><div class="k-ic">${icon(ic)}</div><div class="k-l">${label}</div></div>
    <div class="k-v">${value}</div><div class="k-n">${note}</div>${sparkId ? `<div class="spark" id="${sparkId}"></div>` : ""}</div>`;
}

export const section = (title, sub = "") => `<div class="section-h"><h2>${title}</h2>${sub ? `<p>${sub}</p>` : ""}</div>`;
export const callout = (html, kind = "") => `<div class="callout ${kind}">${html}</div>`;

export function seg(id, options, value, labels = {}) {
  return `<div class="seg" id="${id}">${options.map((o) =>
    `<button data-v="${esc(o)}" class="${o === value ? "on" : ""}">${esc(labels[o] ?? o)}</button>`).join("")}</div>`;
}
export function bindSeg(id, onChange) {
  const el = document.getElementById(id);
  if (!el) return;
  el.querySelectorAll("button").forEach((b) => b.onclick = () => {
    el.querySelectorAll("button").forEach((x) => x.classList.toggle("on", x === b));
    onChange(b.dataset.v);
  });
}

export function toCSV(rows, cols) {
  const keys = cols ? cols.map((c) => c.key) : Object.keys(rows[0] || {});
  const head = cols ? cols.map((c) => c.label) : keys;
  const q = (v) => { const s = v === null || v === undefined ? "" : String(v); return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s; };
  return [head.map(q).join(","), ...rows.map((r) => keys.map((k) => q(r[k])).join(","))].join("\n");
}
export function download(name, rows, cols) {
  const blob = new Blob([toCSV(rows, cols)], { type: "text/csv;charset=utf-8" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob); a.download = `${name}.csv`; a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 2000);
}
export const dlBtn = (id, label = "CSV") => `<button class="btn ghost" id="${id}">${icon("download")}${label}</button>`;

/** Sortable, searchable table. cols: [{key,label,num,fmt,bar:max}] */
export function table(containerId, rows, cols, { search = true, name = "table", maxRows = 400, sortKey = null, desc = true } = {}) {
  const el = document.getElementById(containerId);
  if (!el) return;
  let q = "", key = sortKey, dir = desc ? -1 : 1;
  const draw = () => {
    let r = rows;
    if (q) r = r.filter((x) => cols.some((c) => String(x[c.key] ?? "").toLowerCase().includes(q)));
    if (key) r = [...r].sort((a, b) => {
      const va = a[key], vb = b[key];
      if (typeof va === "number" || typeof vb === "number") return dir * ((va ?? -Infinity) - (vb ?? -Infinity));
      return dir * String(va ?? "").localeCompare(String(vb ?? ""));
    });
    const shown = r.slice(0, maxRows);
    el.querySelector("tbody").innerHTML = shown.map((x) => `<tr>${cols.map((c) => {
      const v = x[c.key];
      const txt = c.fmt ? c.fmt(v, x) : esc(v ?? "—");
      const bar = c.bar && Number.isFinite(v) ? `<span class="bar" style="width:${Math.max(2, (46 * v) / c.bar)}px"></span>` : "";
      return `<td class="${c.num ? "num" : ""}">${bar}${txt}</td>`;
    }).join("")}</tr>`).join("") || `<tr><td colspan="${cols.length}" class="muted">No rows</td></tr>`;
    el.querySelector(".count").textContent = `${r.length.toLocaleString()} row${r.length === 1 ? "" : "s"}${r.length > maxRows ? ` (first ${maxRows} shown)` : ""}`;
    el.querySelectorAll("th").forEach((th) => th.textContent = th.dataset.label + (th.dataset.k === key ? (dir < 0 ? " ↓" : " ↑") : ""));
  };
  el.innerHTML = `<div class="tbl-tools">${search ? `<input class="search" placeholder="Search…" aria-label="Search table">` : ""}
      <span class="count small muted"></span><span style="flex:1"></span>${dlBtn(containerId + "-dl", "Download CSV")}</div>
    <div class="tbl-wrap"><table class="tbl"><thead><tr>${cols.map((c) =>
      `<th class="${c.num ? "num" : ""}" data-k="${c.key}" data-label="${esc(c.label)}">${esc(c.label)}</th>`).join("")}</tr></thead><tbody></tbody></table></div>`;
  if (search) el.querySelector(".search").oninput = (e) => { q = e.target.value.toLowerCase(); draw(); };
  el.querySelectorAll("th").forEach((th) => th.onclick = () => { if (key === th.dataset.k) dir *= -1; else { key = th.dataset.k; dir = -1; } draw(); });
  document.getElementById(containerId + "-dl").onclick = () => download(name, rows, cols.map((c) => ({ key: c.key, label: c.label })));
  draw();
}

/** Multi-city picker with search (max n). state: array of labels (mutated). */
export function picker(containerId, options, state, max, onChange) {
  const el = document.getElementById(containerId);
  if (!el) return;
  const listId = containerId + "-list";
  const draw = () => {
    const colors = colorMap(state);
    el.innerHTML = `<div class="picker">${state.map((s) => `<span class="picked"><i style="background:${colors[s]}"></i>${esc(s)}
      <button data-x="${esc(s)}" aria-label="Remove ${esc(s)}">×</button></span>`).join("")}
      ${state.length < max ? `<input class="search" list="${listId}" placeholder="Add a city…" style="min-width:180px">
      <datalist id="${listId}">${options.filter((o) => !state.includes(o)).map((o) => `<option value="${esc(o)}">`).join("")}</datalist>` : `<span class="small muted">max ${max}</span>`}</div>`;
    el.querySelectorAll("[data-x]").forEach((b) => b.onclick = () => { state.splice(state.indexOf(b.dataset.x), 1); draw(); onChange(); });
    const inp = el.querySelector("input");
    if (inp) inp.onchange = () => { if (options.includes(inp.value) && !state.includes(inp.value)) { state.push(inp.value); draw(); onChange(); } };
  };
  draw();
}

export function citySelect(containerId, options, value, onChange) {
  const el = document.getElementById(containerId);
  el.innerHTML = `<input class="search" list="${containerId}-l" value="${esc(value)}" style="min-width:280px" aria-label="Choose city">
    <datalist id="${containerId}-l">${options.map((o) => `<option value="${esc(o)}">`).join("")}</datalist>`;
  const inp = el.querySelector("input");
  inp.onchange = () => { if (options.includes(inp.value)) onChange(inp.value); };
  inp.onfocus = () => inp.select();
}
