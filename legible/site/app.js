// Forms That Read Themselves: the page viewer and the tables.
// Every value shown here was computed and graded by `legible site` beforehand. This script
// only draws: it never compares a read with the truth, and it sends nothing anywhere.
"use strict";

const SVG = "http://www.w3.org/2000/svg";
const CORPUS_NAMES = {
  nist: "NIST tax forms",
  cord: "CORD receipts",
  deepform: "DeepForm ad-buy forms",
};
const CORPUS_NOTES = {
  nist: "NIST SD2, synthesised 1988 tax forms. Field locations are the zones arm E learned from the training pages, placed by the page's own OCR.",
  cord: "CORD v2 receipt (CC BY 4.0), test set. Field locations are CORD's own word boxes. Read at level 0 only.",
  deepform: "DeepForm ad-buy form (VRDU, FCC public files), a template never seen in training. Field locations are VRDU's entity boxes.",
};
// For the reader table: which curve (or, for CORD, which level-0 table) gives the accuracy.
const CURVE_FOR = { nist: "nist", deepform: "deepform" };
const TABLE_FOR = { cord: "cord" };

const state = { index: null, results: null, corpus: "nist", page: null, record: null, arm: null, level: 0, hot: null };
const cache = new Map();

function el(tag, attrs, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "text") node.textContent = v;
    else if (k === "class") node.className = v;
    else node.setAttribute(k, v === true ? "" : String(v));
  }
  for (const c of children) if (c !== null && c !== undefined) node.append(c);
  return node;
}

function svg(tag, attrs) {
  const node = document.createElementNS(SVG, tag);
  for (const [k, v] of Object.entries(attrs || {})) node.setAttribute(k, String(v));
  return node;
}

async function getJson(path) {
  if (cache.has(path)) return cache.get(path);
  const res = await fetch(path, { credentials: "same-origin" });
  if (!res.ok) throw new Error(`${path}: ${res.status}`);
  const value = await res.json();
  cache.set(path, value);
  return value;
}

function short(s, n) {
  if (s === null || s === undefined) return "(blank)";
  return s.length > n ? s.slice(0, n - 3) + "..." : s;
}

function fieldName(f) {
  return f.item !== null && f.item !== undefined ? `${f.path} #${f.item + 1}` : f.path;
}

// --- Page viewer --------------------------------------------------------------------------

function renderCorpusButtons() {
  const host = document.getElementById("corpora");
  host.replaceChildren();
  for (const c of Object.keys(state.index.pages)) {
    const b = el("button", { type: "button", "aria-pressed": c === state.corpus ? "true" : "false", text: CORPUS_NAMES[c] || c });
    b.addEventListener("click", () => selectCorpus(c));
    host.append(b);
  }
}

function renderPageSelect() {
  const sel = document.getElementById("page");
  sel.replaceChildren();
  state.index.pages[state.corpus].forEach((p, i) => {
    sel.append(el("option", { value: p.id, text: `${i + 1}. ${p.doc}${p.pages > 1 ? ` (${p.pages} pages)` : ""}` }));
  });
  sel.value = state.page;
}

function renderArmSelect() {
  const sel = document.getElementById("arm");
  sel.replaceChildren();
  for (const a of state.index.arms) sel.append(el("option", { value: a.label, text: a.label }));
  sel.value = state.arm;
}

async function selectCorpus(c) {
  state.corpus = c;
  state.page = state.index.pages[c][0].id;
  renderCorpusButtons();
  renderPageSelect();
  await loadPage();
}

async function loadPage() {
  state.record = await getJson(`data/pages/${state.page}.json`);
  const levels = state.record.levels;
  if (!levels.includes(state.level)) state.level = levels.reduce((a, b) => (Math.abs(b - state.level) < Math.abs(a - state.level) ? b : a));
  const slider = document.getElementById("level");
  slider.min = "0";
  slider.max = String(levels.length - 1);
  slider.value = String(levels.indexOf(state.level));
  slider.disabled = levels.length < 2;
  const note = document.getElementById("level-note");
  note.textContent = levels.length < 2 ? "read at level 0 only" : `levels ${levels.join(", ")} read`;
  draw();
}

function currentRead() {
  const byArm = state.record.reads[String(state.level)] || {};
  return byArm[state.arm] || null;
}

function draw() {
  const rec = state.record;
  const lv = String(state.level);
  document.getElementById("level-name").textContent = `level ${state.level}${state.level === 0 ? " (clean)" : ""}`;
  const read = currentRead();
  const boxes = rec.boxes[lv] || {};
  const labelWrong = document.getElementById("labels").checked;
  const sheets = document.getElementById("sheets");
  sheets.replaceChildren();
  const placed = [];
  const unplaced = [];
  for (const f of read ? read.fields : []) {
    if (f.key && boxes[f.key]) placed.push(f);
    else unplaced.push(f);
  }
  rec.pages.forEach((p, i) => {
    const sheet = el("div", { class: "sheet" });
    const img = el("img", { src: rec.images[lv][i], alt: `${CORPUS_NAMES[rec.corpus]} page ${i + 1} at scan level ${state.level}`, width: p.width, height: p.height });
    const over = svg("svg", { viewBox: `0 0 ${p.width} ${p.height}`, preserveAspectRatio: "none", role: "img", "aria-label": "Field reads drawn on the page" });
    const fs = Math.max(10, Math.round(p.width * 0.012));
    const tags = [];
    for (const f of placed) {
      const [pg, x1, y1, x2, y2] = boxes[f.key];
      if (pg !== i) continue;
      const r = svg("rect", { x: x1 * p.width, y: y1 * p.height, width: Math.max(2, (x2 - x1) * p.width), height: Math.max(2, (y2 - y1) * p.height), class: `box ${f.correct ? "ok" : "bad"}`, "data-key": fieldName(f) });
      const t = svg("title", {});
      t.textContent = `${fieldName(f)}: ${f.correct ? "right" : "wrong"}. Read: ${short(f.read, 80)}. Truth: ${short(f.truth, 80)}`;
      r.append(t);
      r.addEventListener("mouseenter", () => highlight(fieldName(f)));
      r.addEventListener("mouseleave", () => highlight(null));
      over.append(r);
      if (labelWrong && !f.correct) tags.push([f, x1 * p.width, y2 * p.height]);
    }
    for (const [f, x0, y] of tags) {
      const g = svg("g", { class: "tag" });
      const label = `read ${short(f.read, 28)} | truth ${short(f.truth, 28)}`;
      const w = label.length * fs * 0.56 + fs * 0.6;
      const x = Math.max(0, Math.min(x0, p.width - w));
      const text = svg("text", { x: x + fs * 0.3, y: y + fs * 1.05, "font-size": fs });
      text.textContent = label;
      g.append(svg("rect", { x, y: y + 1, width: w, height: fs * 1.35, rx: 3 }), text);
      over.append(g);
    }
    sheet.append(img, over);
    if (rec.pages.length > 1) sheet.append(el("div", { class: "pageno", text: `page ${i + 1} of ${rec.pages_total}` }));
    sheets.append(sheet);
  });
  const extra = rec.pages_total > rec.pages.length ? ` The first ${rec.pages.length} of its ${rec.pages_total} pages are shown.` : "";
  document.getElementById("caption").textContent = `${CORPUS_NOTES[rec.corpus]} Document ${rec.doc}.${extra}`;

  const summary = document.getElementById("summary");
  if (!read) summary.textContent = `${state.arm} has not yet read this page at level ${state.level}.`;
  else summary.textContent = `${state.arm}: ${read.correct} of ${read.scored} fields right on this page${read.unparsed ? " (its output did not parse, so every field is wrong)" : ""}.`;
  fillList(document.getElementById("field-list"), placed, rec.labels);
  fillList(document.getElementById("unplaced"), unplaced, rec.labels);
  document.getElementById("unplaced-h").hidden = unplaced.length === 0;
  document.getElementById("unplaced-note").hidden = unplaced.length === 0;
  drawArms();
}

function fillList(host, fields, labels) {
  const wrongOnly = document.getElementById("wrong-only").checked;
  host.replaceChildren();
  for (const f of fields) {
    if (wrongOnly && f.correct) continue;
    const li = el("li", { class: f.correct ? "ok" : "bad", "data-key": fieldName(f), tabindex: "0" },
      el("span", { class: "verdict", text: f.correct ? "✓ right" : `✗ ${f.outcome.replaceAll("_", " ")}` }),
      el("span", { class: "name", text: fieldName(f) }),
      labels[f.path] ? el("span", { class: "desc", text: labels[f.path] }) : null,
      el("dl", { class: "vals" },
        el("dt", { text: "Read" }), el("dd", { text: f.read === null ? "(blank)" : f.read }),
        el("dt", { text: "Truth" }), el("dd", { text: f.truth === null ? "(blank on the page)" : f.truth })));
    li.addEventListener("mouseenter", () => highlight(fieldName(f)));
    li.addEventListener("mouseleave", () => highlight(null));
    li.addEventListener("focus", () => highlight(fieldName(f)));
    li.addEventListener("blur", () => highlight(null));
    host.append(li);
  }
}

function highlight(key) {
  for (const n of document.querySelectorAll(".hot")) n.classList.remove("hot");
  if (key === null) return;
  for (const n of document.querySelectorAll("[data-key]")) if (n.getAttribute("data-key") === key) n.classList.add("hot");
}

function ciBar(iv) {
  const s = svg("svg", { viewBox: "0 0 100 18", preserveAspectRatio: "none", class: "ci", "aria-hidden": "true" });
  s.append(svg("line", { x1: 0, x2: 100, y1: 9, y2: 9, class: "track" }));
  if (iv) {
    s.append(svg("line", { x1: iv.low * 100, x2: iv.high * 100, y1: 9, y2: 9, class: "whisker" }));
    s.append(svg("circle", { cx: iv.point * 100, cy: 9, r: 4, class: "dot" }));
  }
  return s;
}

function drawArms() {
  const rec = state.record;
  const lv = String(state.level);
  const body = document.getElementById("arms-body");
  body.replaceChildren();
  const curve = CURVE_FOR[rec.corpus] ? state.results.curves.find((c) => c.key === CURVE_FOR[rec.corpus]) : null;
  const table = TABLE_FOR[rec.corpus] ? state.results.tables.find((t) => t.key === TABLE_FOR[rec.corpus]) : null;
  const note = document.getElementById("arms-note");
  if (curve) note.textContent = `${curve.title}. The page above is one of them. The bar runs from 0 to 100%.`;
  else if (table) note.textContent = `${table.title}, at level 0. The bar runs from 0 to 100%.`;
  for (const a of state.index.arms) {
    const read = (rec.reads[lv] || {})[a.label];
    let text = "not yet read";
    let iv = null;
    if (curve) {
      const cell = (curve.cells[a.label] || {})[lv];
      if (cell && cell.accuracy) {
        text = cell.text;
        iv = cell.accuracy;
        if (cell.accuracy.n < curve.documents) text += `, ${cell.accuracy.n} of ${curve.documents} pages read so far`;
      }
    } else if (table) {
      const row = table.rows.find((r) => r.arm === a.label);
      if (row && row.accuracy) { text = row.accuracy_text; iv = row.accuracy; }
    }
    const tr = el("tr", { class: a.label === state.arm ? "sel" : "", tabindex: "0" },
      el("th", { scope: "row", text: a.label }),
      el("td", { class: "num", text: read ? `${read.correct} of ${read.scored} right` : "not yet read" }),
      el("td", { class: "num", text }),
      el("td", {}, ciBar(iv)));
    const pick = () => { state.arm = a.label; document.getElementById("arm").value = a.label; draw(); };
    tr.addEventListener("click", pick);
    tr.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); pick(); } });
    body.append(tr);
  }
}

// --- Tables -------------------------------------------------------------------------------

function cells(tr, values, tag) {
  for (const v of values) tr.append(el(tag || "td", { text: v }));
  return tr;
}

function renderTables() {
  const host = document.getElementById("tables-body");
  host.replaceChildren();
  const r = state.results;
  for (const t of r.tables) {
    const tbody = el("tbody");
    for (const row of t.rows) {
      const n = row.accuracy === null ? "0" : `${row.documents - row.missing}${row.missing ? ` of ${row.documents}` : ""}`;
      const tr = el("tr", {}, el("th", { scope: "row", text: row.arm }));
      cells(tr, [row.accuracy_text, row.all_right_text, row.invented_text, row.per_thousand_text, row.price_date, n]);
      tbody.append(tr);
    }
    const head = cells(el("tr"), ["Reader", "Fields correct (95% CI)", "Every field right", "Invented fields", "Cost per 1,000 pages (95% CI)", "Price dated", "Documents"], "th");
    host.append(el("div", { class: "table-wrap" }, el("h3", { text: t.title }), el("table", { class: "data" }, el("thead", {}, head), tbody)));
  }
  for (const c of r.curves) {
    const tbody = el("tbody");
    for (const [label, byLevel] of Object.entries(c.cells)) {
      const tr = el("tr", {}, el("th", { scope: "row", text: label }));
      cells(tr, c.levels.map((lv) => {
        const cell = byLevel[String(lv)];
        if (!cell || !cell.accuracy) return "not yet read";
        return cell.accuracy.n < c.documents ? `${cell.text}, ${cell.accuracy.n} of ${c.documents} read` : cell.text;
      }));
      tbody.append(tr);
    }
    const head = cells(el("tr"), ["Reader", ...c.levels.map((lv) => `Level ${lv}`)], "th");
    host.append(el("div", { class: "table-wrap" }, el("h3", { text: `${c.title}: fields correct (95% CI)` }), el("table", { class: "data" }, el("thead", {}, head), tbody)));
  }
  for (const v of r.reviews) {
    const tbody = el("tbody");
    for (const row of v.rows) {
      const tr = el("tr", {}, el("th", { scope: "row", text: row.corpus }));
      cells(tr, [row.sent_text, row.accepted_text, row.dev_text]);
      tbody.append(tr);
    }
    const head = cells(el("tr"), ["Corpus", "Fields sent to a person (95% CI)", "Accuracy of the fields accepted", "Reached 99% on dev"], "th");
    host.append(el("div", { class: "table-wrap" }, el("h3", { text: v.title }), el("p", { class: "muted", text: v.note }), el("table", { class: "data" }, el("thead", {}, head), tbody)));
  }
}

// --- Wiring -------------------------------------------------------------------------------

function route() {
  const tables = location.hash === "#tables";
  document.getElementById("pages").hidden = tables;
  document.getElementById("tables").hidden = !tables;
  document.getElementById("tab-pages").setAttribute("aria-current", tables ? "false" : "page");
  document.getElementById("tab-tables").setAttribute("aria-current", tables ? "page" : "false");
}

async function main() {
  [state.index, state.results] = await Promise.all([getJson("data/index.json"), getJson("data/results.json")]);
  state.corpus = Object.keys(state.index.pages)[0];
  state.page = state.index.pages[state.corpus][0].id;
  state.arm = state.index.arms[0].label;
  document.getElementById("built").textContent = `Built ${state.index.built}.`;
  renderCorpusButtons();
  renderPageSelect();
  renderArmSelect();
  renderTables();
  document.getElementById("page").addEventListener("change", (e) => { state.page = e.target.value; loadPage(); });
  document.getElementById("arm").addEventListener("change", (e) => { state.arm = e.target.value; draw(); });
  document.getElementById("level").addEventListener("input", (e) => { state.level = state.record.levels[Number(e.target.value)]; draw(); });
  document.getElementById("labels").addEventListener("change", draw);
  document.getElementById("wrong-only").addEventListener("change", draw);
  window.addEventListener("hashchange", route);
  route();
  await loadPage();
}

main().catch((err) => {
  const p = el("p", { text: `The site's data did not load: ${err.message}` });
  document.querySelector("main").prepend(p);
});
