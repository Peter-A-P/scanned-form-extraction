// Forms That Read Themselves: the front page's findings and charts, and the page viewer.
// Every number drawn here was computed by `legible site` from the project's runs, with the
// same code that writes the README's tables, and graded beforehand. This script only picks
// among those numbers and draws them: it never compares a read with the truth, and it sends
// nothing anywhere.
"use strict";

const SVG = "http://www.w3.org/2000/svg";

// The four kinds of form, in the order the page talks about them. `table` is the headline
// table's key in results.json, `gap` the mixed-template table beside it.
const CORPORA = [
  { key: "fara", table: "fara-unseen", gap: "fara-mixed", name: "Registration forms", noun: "registration forms",
    about: "Foreign Agents Registration Act filings from the US Department of Justice, from Google's VRDU benchmark. Tested on form designs the fine-tunes never saw in training.",
    shown: false },
  { key: "deepform", table: "deepform-unseen", gap: "deepform-mixed", name: "Ad-buy forms", noun: "ad-buy forms",
    about: "Political advertising orders filed with the FCC (DeepForm, from VRDU): several pages, a table of line items. Tested on designs never seen in training.",
    shown: true },
  { key: "cord", table: "cord", name: "Receipts", noun: "receipts",
    about: "Photographed shop and restaurant receipts from Indonesia (CORD v2): crumpled, skewed, every item a row.",
    shown: true },
  { key: "nist", table: "nist", name: "Tax forms", noun: "tax forms",
    about: "NIST Special Database 2: twenty faces of the 1988 US tax forms, filled in with synthesised entries and scanned in black and white.",
    shown: true },
];
const CORPUS = Object.fromEntries(CORPORA.map((c) => [c.key, c]));
const KIND_NAMES = {
  finetuned: "Fine-tuned here",
  frontier: "Frontier vision API",
  managed: "Azure Document Intelligence",
  "ocr-llm": "OCR text to Sonnet",
  "ocr-rules": "OCR plus rules",
  untuned: "Untuned base",
};
const AZURE = "F, Azure Document Intelligence";
const SONNET = "A, Claude Sonnet 5.5 on the image";
const HAIKU = "A, Claude Haiku 5.5 on the image";
const SONNET_OCR = "D, Claude Sonnet 5.5 on the OCR text";
const RULES = "E, OCR plus rules";

const state = {
  results: null, story: null, index: null,
  landscape: "cord", serving: "fara", scans: "nist", scansOff: new Set(),
  corpus: "nist", page: null, record: null, arm: null, level: 0,
};
const cache = new Map();
const tables = new Map();

// --- Small helpers ------------------------------------------------------------------------

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

function svg(tag, attrs, text) {
  const node = document.createElementNS(SVG, tag);
  for (const [k, v] of Object.entries(attrs || {})) if (v !== null && v !== undefined) node.setAttribute(k, String(v));
  if (text !== undefined) node.textContent = text;
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

const pct = (x, d = 1) => `${(100 * x).toFixed(d)}%`;
const pts = (x) => `${Math.abs(100 * x).toFixed(1)}`;
const int = (x) => Math.round(x).toLocaleString("en-US");
function usd(x) {
  if (x >= 100) return `US$${int(x)}`;
  if (x >= 10) return `US$${x.toFixed(x % 1 === 0 ? 0 : 2)}`;
  return `US$${x.toFixed(2)}`;
}
function usdBare(x) { return usd(x).replace("US$", ""); }
function big(x) {
  if (x >= 1e6) return `${(x / 1e6).toFixed(x >= 1e7 ? 0 : 1)} million`;
  return int(x);
}
function times(x) { return x >= 10 ? `${Math.round(x)}` : x.toFixed(1); }
function span(lo, hi, f) { return Math.abs(lo - hi) < 1e-9 ? f(lo) : `${f(lo)} to ${f(hi)}`; }
function list(items) {
  if (items.length < 2) return items.join("");
  return `${items.slice(0, -1).join(", ")} and ${items[items.length - 1]}`;
}
function minutes(m) {
  if (m < 90) return `${Math.round(m)} minutes`;
  return `${(m / 60).toFixed(1)} hours`;
}

function arm(label) { return state.results.arms.find((a) => a.label === label); }
function short(label) { const a = arm(label); return a ? a.short : label; }
function kind(label) {
  if (label.startsWith("A, Claude Opus")) return "opus";
  const a = arm(label); return a ? a.kind : "frontier";
}
function table(key) { return state.results.tables.find((t) => t.key === key); }
function row(key, label) {
  const t = table(key);
  return t ? t.rows.find((r) => r.arm === label && r.accuracy) || null : null;
}
function curve(key) { return state.results.curves.find((c) => c.key === key); }

function ftLabel(size) { return `B, Gemma 4 E${size === "2b" ? "2" : "4"}B fine-tuned on the image`; }
function baseLabel(size) { return `C, Gemma 4 E${size === "2b" ? "2" : "4"}B untuned on the image`; }
// The size the release gate compared on each corpus: the better of the two on dev.
function gatedSize(corpus) {
  const s = state.story.serving.find((x) => x.corpus === corpus && x.gated);
  return s ? s.size : "2b";
}
function ft(corpus) { return row(CORPUS[corpus].table, ftLabel(gatedSize(corpus))); }
function frontierRows(key) { return table(key).rows.filter((r) => kind(r.arm) === "frontier" && r.accuracy); }
function bestFrontier(key) { return frontierRows(key).reduce((a, b) => (b.accuracy.point > a.accuracy.point ? b : a)); }
function cheapestFrontier(key) { return frontierRows(key).reduce((a, b) => (b.per_thousand.point < a.per_thousand.point ? b : a)); }

function fill(name, value) {
  for (const n of document.querySelectorAll(`[data-fill="${name}"]`)) n.textContent = value;
}

// A chart can always be read as a table: `register` keeps the rows for the figure with that
// name, and the switch under the figure swaps one for the other.
function register(name, head, rows, caption) {
  tables.set(name, { head, rows, caption });
  const fig = document.querySelector(`figure[data-table="${name}"]`);
  if (!fig) return;
  let host = fig.querySelector(".chart-table");
  if (!host) {
    host = el("div", { class: "table-wrap chart-table", hidden: true });
    const button = el("button", { type: "button", "aria-pressed": "false", text: "See as a table" });
    button.addEventListener("click", () => {
      const on = button.getAttribute("aria-pressed") !== "true";
      button.setAttribute("aria-pressed", on ? "true" : "false");
      button.textContent = on ? "See as a chart" : "See as a table";
      host.hidden = !on;
      for (const c of fig.querySelectorAll(".chart, .readout")) c.hidden = on;
    });
    fig.append(el("div", { class: "view-switch" }, button), host);
  }
  const t = tables.get(name);
  const thead = el("thead", {}, el("tr", {}, ...t.head.map((h, i) => el("th", { scope: "col", class: i ? "num" : null, text: h }))));
  const tbody = el("tbody", {}, ...t.rows.map((r) => el("tr", {}, ...r.map((v, i) => (i ? el("td", { class: "num", text: v }) : el("th", { scope: "row", class: "wrap", text: v }))))));
  host.replaceChildren(el("table", { class: "tight" }, t.caption ? el("caption", { text: t.caption }) : null, thead, tbody));
}

function legend(host, kinds, extra) {
  const node = typeof host === "string" ? document.getElementById(host) : host;
  node.replaceChildren(...kinds.map((k) => el("span", { class: "legend-item" }, el("span", { class: `swatch solid sw-${k}` }), KIND_NAMES[k] || k)), ...(extra || []));
}

function chips(id, items, current, pick) {
  const host = document.getElementById(id);
  host.replaceChildren();
  for (const [key, text] of items) {
    const b = el("button", { type: "button", class: "chip", "aria-pressed": key === current ? "true" : "false", text });
    b.addEventListener("click", () => {
      for (const o of host.children) o.setAttribute("aria-pressed", o === b ? "true" : "false");
      pick(key);
    });
    host.append(b);
  }
}

// A reader's mark: the shape carries the kind as well as the colour does.
function mark(k, x, y, r, extra) {
  const cls = `mark k-fill-${k}${extra ? ` ${extra}` : ""}`;
  if (k === "finetuned") {
    const d = r * 1.3;
    return svg("path", { d: `M${x},${y - d}L${x + d},${y}L${x},${y + d}L${x - d},${y}Z`, class: cls });
  }
  if (k === "managed") return svg("rect", { x: x - r, y: y - r, width: 2 * r, height: 2 * r, rx: 1.5, class: cls });
  if (k === "ocr-llm" || k === "ocr-rules") {
    const d = r * 1.25;
    return svg("path", { d: `M${x},${y - d}L${x + d},${y + d * 0.8}L${x - d},${y + d * 0.8}Z`, class: cls });
  }
  return svg("circle", { cx: x, cy: y, r, class: cls });
}

// A round axis top and step for a maximum: 1, 2, 2.5 or 5 times a power of ten, about four
// steps to the top.
function nice(max) {
  const raw = max / 4;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((v) => v >= raw);
  return [Math.ceil(max / step) * step, step];
}

// The first place for a label of width w beside the mark at (px, py) that overlaps no other
// mark and no label placed before it; the label's box is added to `placed`.
function placeLabel(placed, marks, px, py, w, right) {
  const h = 12;
  const tries = [
    { x: px + 10, y: py + 4, anchor: "start" }, { x: px - 10, y: py + 4, anchor: "end" },
    { x: px, y: py - 10, anchor: "middle" }, { x: px, y: py + 18, anchor: "middle" },
    { x: px + 10, y: py + 17, anchor: "start" }, { x: px + 10, y: py - 9, anchor: "start" },
    { x: px - 10, y: py + 17, anchor: "end" }, { x: px - 10, y: py - 9, anchor: "end" },
    { x: px + 10, y: py + 30, anchor: "start" }, { x: px + 10, y: py - 22, anchor: "start" },
  ];
  const box = (t) => {
    const x0 = t.anchor === "start" ? t.x : t.anchor === "end" ? t.x - w : t.x - w / 2;
    return { x0, x1: x0 + w, y0: t.y - h + 2, y1: t.y + 2 };
  };
  const clear = (b) => b.x1 < right && b.x0 > 0
    && !placed.some((o) => b.x0 < o.x1 && b.x1 > o.x0 && b.y0 < o.y1 && b.y1 > o.y0)
    && !marks.some((m) => (m.x !== px || m.y !== py) && m.x > b.x0 - 6 && m.x < b.x1 + 6 && m.y > b.y0 - 6 && m.y < b.y1 + 6);
  const pick = tries.find((t) => clear(box(t))) || tries[0];
  placed.push(box(pick));
  return pick;
}

function logScale(lo, hi, a, b) {
  const l0 = Math.log10(lo), l1 = Math.log10(hi);
  return (v) => a + ((Math.log10(Math.max(v, lo)) - l0) / (l1 - l0)) * (b - a);
}
function linScale(lo, hi, a, b) { return (v) => a + ((v - lo) / (hi - lo)) * (b - a); }
function costTick(v) { return v < 1 ? `$${v}` : `$${int(v)}`; }

// --- The fills: every number in the page's prose ------------------------------------------

function fills() {
  const s = state.story;
  fill("pages-read", int(s.read.pages));
  fill("corpus-pages", int(s.corpora.pages));

  const pairs = CORPORA.map((c) => ({ c, f: ft(c.key), z: row(c.table, AZURE), best: bestFrontier(c.table), cheap: cheapestFrontier(c.table) }));
  // Beats: the fine-tune's whole 95% interval is above Azure's score. Matches: its score is
  // inside Azure's interval or above it, short of that.
  const beat = pairs.filter((p) => p.f.accuracy.low > p.z.accuracy.point);
  const level = pairs.filter((p) => !beat.includes(p) && p.f.accuracy.point >= p.z.accuracy.low);
  const words = ["none", "one", "two", "three", "four", "five", "six"];
  fill("beat-words", 2 * beat.length === pairs.length ? "half" : `${words[beat.length]} of the ${words[pairs.length]}`);
  fill("beat-figure", beat.map((p) => `+${Math.round(100 * (p.f.accuracy.point - p.z.accuracy.point))}`).join(" and "));
  fill("beat-unit", `percentage points more fields right than Azure on ${list(beat.map((p) => p.c.noun))}`);
  fill("beat-note", `${list(beat.map((p) => `${pct(p.f.accuracy.point)} against ${pct(p.z.accuracy.point)}`))}, the fine-tune's whole 95% interval above Azure's score; level with it on ${list(level.map((p) => p.c.noun))}`);
  fill("f-azure-figure", `${words[beat.length]} better, ${words[level.length]} level`.replace(/^./, (c) => c.toUpperCase()));
  const readers = state.results.arms.length + (s.ceiling.length ? 1 : 0);
  fill("scale-note", `${int(s.corpora.pages)} distinct pages of ${int(s.corpora.documents)} documents, read by ${readers} readers across 4 form types, up to 5 scan qualities, development and test, 3 training seeds and second reads`);
  const ratios = pairs.map((p) => p.z.per_thousand.point / p.f.per_thousand.point);
  const ftCosts = pairs.map((p) => p.f.per_thousand.point);
  const azCosts = pairs.map((p) => p.z.per_thousand.point);
  // One number: 1,000 pages of each form type, read by each, the bills compared. A mean of the
  // four ratios would be pulled up by the cheapest form alone.
  const azTotal = azCosts.reduce((a, b) => a + b, 0), ftTotal = ftCosts.reduce((a, b) => a + b, 0);
  fill("vs-azure-ratio", `${Math.round(azTotal / ftTotal)}x cheaper`);
  fill("ft-price-range", span(Math.min(...ftCosts), Math.max(...ftCosts), usd).replace(/ to US\$/, " to "));
  fill("azure-price", span(Math.min(...azCosts), Math.max(...azCosts), usd).replace(/ to US\$/, " to "));
  fill("vs-azure-ratio-note", `1,000 pages of each of the ${pairs.length} form types: ${usd(azTotal)} on Azure (${s.prices.docintel}), ${usd(ftTotal)} on the fine-tune (${s.prices.serve_checked}); ${times(Math.min(...ratios))}x to ${times(Math.max(...ratios))}x form by form`);
  fill("f-azure-detail", `It gets more fields right than Azure's model on ${list(beat.map((p) => `${p.c.noun} (${pct(p.f.accuracy.point)} against ${pct(p.z.accuracy.point)})`))}, by more than the uncertainty in either, and as many on ${list(level.map((p) => `${p.c.noun} (${pct(p.f.accuracy.point)} against ${pct(p.z.accuracy.point)})`))}`);

  const bests = pairs.map((p) => p.best.accuracy.point);
  fill("best-frontier-range", `${Math.round(100 * Math.min(...bests))} to ${Math.round(100 * Math.max(...bests))}%`);
  const gaps = pairs.map((p) => p.best.accuracy.point - p.f.accuracy.point);
  fill("best-frontier-gap", `the fine-tune trails it by ${Math.round(100 * Math.min(...gaps))} to ${Math.round(100 * Math.max(...gaps))} points`);
  fill("f-frontier-figure", `${Math.round(100 * Math.min(...bests))} to ${Math.round(100 * Math.max(...bests))}%`);
  const leaders = new Map();
  for (const p of pairs) {
    const k = p.best.arm;
    if (!leaders.has(k)) leaders.set(k, []);
    leaders.get(k).push(`${p.c.noun} (${pct(p.best.accuracy.point)})`);
  }
  fill("f-frontier-detail", list([...leaders].map(([k, v]) => `${short(k)} leads on ${list(v)}`)));

  const nist = curve("nist");
  const lv = nist.levels[nist.levels.length - 1];
  const at = (label, level) => nist.cells[label][String(level)].accuracy.point;
  const ocr0 = at(SONNET_OCR, 0), ocrN = at(SONNET_OCR, lv);
  fill("f-scan-figure", `${pts(at(SONNET, 0) - at(SONNET, lv))} points against ${pts(ocr0 - ocrN)}`);
  fill("f-scan-detail", `From a clean page to the worst scan, Claude Sonnet 5.5 reading the image goes from ${pct(at(SONNET, 0))} to ${pct(at(SONNET, lv))} of the tax forms' fields; the same model reading OCR's text goes from ${pct(ocr0)} to ${pct(ocrN)}, and OCR plus rules from ${pct(at(RULES, 0))} to ${pct(at(RULES, lv))}`);

  const lifts = [];
  for (const c of CORPORA) for (const size of ["2b", "4b"]) {
    const a = row(c.table, baseLabel(size)), b = row(c.table, ftLabel(size));
    if (a && b) lifts.push({ c, size, from: a.accuracy.point, to: b.accuracy.point });
  }
  const top = lifts.reduce((a, b) => (b.to - b.from > a.to - a.from ? b : a));
  fill("f-lift-figure", `+${pts(top.to - top.from)} points`);
  const nextBest = lifts.filter((l) => l.c !== top.c).reduce((a, b) => (b.to - b.from > a.to - a.from ? b : a));
  fill("f-lift-detail", `On ${top.c.noun} the untuned Gemma 4 E${top.size[0]}B gets ${pct(top.from)} of fields right and the fine-tuned one ${pct(top.to)}; on ${nextBest.c.noun}, ${pct(nextBest.from)} becomes ${pct(nextBest.to)}`);
  fill("s-untuned-max", pts(top.to - top.from));
  const mins = s.training.map((t) => t.minutes);
  fill("train-minutes-range", `${minutes(Math.min(...mins))} to ${minutes(Math.max(...mins))}`);

  const inv = (key, label) => row(key, label).invented.point;
  const invented = ["fara", "cord"].map((k) => {
    const c = CORPUS[k];
    const fr = frontierRows(c.table).map((r) => r.invented.point);
    return { c, f: inv(c.table, ftLabel(gatedSize(k))), lo: Math.min(...fr), hi: Math.max(...fr) };
  });
  // The four frontier models' mean beside the fine-tune: one number reads better than a range.
  for (const v of invented) v.mean = frontierRows(v.c.table).reduce((a, r) => a + r.invented.point, 0) / frontierRows(v.c.table).length;
  fill("f-invent-figure", `${pct(invented[0].f)} against ${pct(invented[0].mean)}`);
  const nistFt = inv("nist", ftLabel(gatedSize("nist")));
  const nistFr = frontierRows("nist").map((r) => r.invented.point);
  fill("f-invent-detail", `On ${invented[0].c.noun} it writes a value the page does not hold for ${pct(invented[0].f)} of fields, against ${pct(invented[0].mean)} on average for the four frontier models (${pct(invented[0].lo)} to ${pct(invented[0].hi)}); on ${invented[1].c.noun}, ${pct(invented[1].f)} against ${pct(invented[1].lo)} to ${pct(invented[1].hi)}. Not on every form: on the tax forms it is ${pct(nistFt)} against ${pct(Math.min(...nistFr))} to ${pct(Math.max(...nistFr))}`);

  const hk = row("nist", HAIKU), sn = row("nist", SONNET);
  fill("f-cheap-figure", `1/${Math.round(sn.per_thousand.point / hk.per_thousand.point)} the price`);
  fill("f-cheap-detail", `Claude Haiku 5.5 reads ${pct(hk.accuracy.point)} of the tax forms' fields against Claude Sonnet 5.5's ${pct(sn.accuracy.point)}, at ${usd(hk.per_thousand.point)} a thousand pages against ${usd(sn.per_thousand.point)}`);

  const cordFt = ft("cord"), cordHaiku = row("cord", HAIKU);
  const faraInv = invented[0];
  fill("m-strong", `It beats Azure's models on ${list(beat.map((p) => `${p.c.noun} by ${Math.round(100 * (p.f.accuracy.point - p.z.accuracy.point))} percentage points`))} and matches them on ${list(level.map((p) => p.c.noun))}, at ${times(Math.min(...ratios))} to ${times(Math.max(...ratios))} times less a page. On receipts it gets ${pct(cordFt.accuracy.point)} of fields right against Claude Haiku 5.5's ${pct(cordHaiku.accuracy.point)}, for ${usd(cordFt.per_thousand.point)} a thousand pages against ${usd(cordHaiku.per_thousand.point)}. It invents fewer values than any frontier model on ${faraInv.c.noun} and receipts. And it runs on one consumer card you control, so no page has to leave your network.`);
  const vsBest = s.gate.filter((g) => g.name.endsWith("-vs-best") && g.verdict === "block" && !g.name.includes("mixed"));
  const worst = vsBest.map((g) => {
    const corpus = CORPORA.find((c) => g.name.includes(`-${c.key}-`));
    const b = g.blocks[0];
    return `${b.field.replaceAll("_", " ").replaceAll("-", " ")} on ${corpus.noun}, ${b.difference.split(" ")[0].replace("-", "")} behind`;
  });
  const widest = pairs.reduce((a, b) => (b.best.accuracy.point - b.f.accuracy.point > a.best.accuracy.point - a.f.accuracy.point ? b : a));
  fill("m-weak", `It trails the most accurate frontier model by ${Math.round(100 * Math.min(...gaps))} to ${Math.round(100 * Math.max(...gaps))} points, most on ${widest.c.noun} (${pts(widest.best.accuracy.point - widest.f.accuracy.point)} behind ${short(widest.best.arm)}). The release gate blocks it against the best frontier model on registration and ad-buy forms; the worst fields: ${list(worst)}. Train it for one form type and use it for that.`);
  fill("gate-blocks", list(worst));

  fill("azure-receipt-price", usd(row("cord", AZURE).per_thousand.point));
  fill("azure-date", s.prices.docintel);
  fill("gpu-rate", `${usd(s.prices.serve_usd_per_hour)} an hour`);
  fill("gpu-date", s.prices.serve_checked);
  const docs = (d) => s.training.filter((t) => t.dataset.startsWith(d)).map((t) => t.documents);
  fill("ft-train", `${Math.max(...docs("fara"))} of each registration split, ${Math.max(...docs("deepform"))} ad-buy orders, ${Math.max(...docs("nist"))} tax-form pages over the twenty faces and ${Math.max(...docs("cord"))} receipts`);
  const bench = s.serving[0];
  fill("bench-gpu", bench.gpu);
  fill("bench-rate", usd(bench.usd_per_hour));

  const ceil = s.ceiling;
  // Better: Opus's point estimate above the top of Sonnet's interval on the same documents.
  const better = ceil.filter((c) => c.first.point > c.second.high);
  const same = ceil.filter((c) => !(c.first.point > c.second.high));
  const ratio = ceil.map((c) => c.first_cost.point / c.second_cost.point);
  fill("s-opus", `At ${span(Math.min(...ratio), Math.max(...ratio), (x) => x.toFixed(1))} times Sonnet's price, it reads ${list(better.map((c) => `${pct(c.first.point)} of ${CORPUS[c.corpus.toLowerCase()].noun}' fields against ${pct(c.second.point)}`))}, and is no better on ${list(same.map((c) => CORPUS[c.corpus.toLowerCase()].noun))}.`);

  const fm = row("fara-mixed", ftLabel("2b")), fu = row("fara-unseen", ftLabel("2b"));
  const sm = row("fara-mixed", SONNET), su = row("fara-unseen", SONNET);
  fill("s-gap", `On registration forms the 2B fine-tune gets ${pct(fm.accuracy.point)} of fields right on designs it saw in training and ${pct(fu.accuracy.point)} on designs it did not; Claude Sonnet 5.5 gets ${pct(sm.accuracy.point)} and ${pct(su.accuracy.point)}.`);

  const ch = s.noise.filter((n) => n.changed).map((n) => n.changed.point);
  fill("s-noise", `Claude Sonnet 5.5, sent the same requests again days later, changed the outcome of ${pct(Math.min(...ch))} to ${pct(Math.max(...ch))} of its fields.`);

  const u4 = row("fara-unseen", baseLabel("4b")), f4 = row("fara-unseen", ftLabel("4b"));
  fill("s-untuned", `On registration forms of designs it never saw, the untuned Gemma 4 E4B gets ${pct(u4.accuracy.point)} of fields right and the fine-tuned E4B ${pct(f4.accuracy.point)}.`);
  const zf = row("fara-unseen", AZURE), bf = row("fara-unseen", ftLabel("2b"));
  const visionInv = table("fara-unseen").rows.filter((r) => ["frontier", "finetuned"].includes(kind(r.arm)) && r.invented).map((r) => r.invented.point);
  fill("s-azure-careful", `On registration forms Azure invents a value for ${pct(zf.invented.point)} of fields, against ${pct(Math.min(...visionInv))} to ${pct(Math.max(...visionInv))} for the vision models, but gets fewer whole documents entirely right: ${pct(zf.all_right.point)} against the 2B fine-tune's ${pct(bf.all_right.point)}.`);

  const rates = state.results.reviews.flatMap((r) => r.rows.map((x) => x.review_rate).filter(Boolean).map((x) => x.point));
  fill("review-rate", span(Math.min(...rates), Math.max(...rates), (x) => pct(x)).replace(/% to /, " to "));
  fill("azure-hours", s.docintel_training.hours.toFixed(1));
  fill("azure-train-usd", usd(s.docintel_training.usd));
  document.getElementById("foot-built").textContent = `Built ${state.index.built} from the runs; frontier prices of ${s.prices.frontier}, Azure's of ${s.prices.docintel}, the GPU's of ${s.prices.serve_checked}`;
}

// --- Head to head -------------------------------------------------------------------------

function drawHeadToHead() {
  const host = document.getElementById("h2h");
  // Fields correct starts at 25%: no reader shown here is near the bottom, and the space goes
  // to the cost panel, whose thousandfold spread is the point.
  const W = 920, labelW = 200, accX0 = labelW + 10, accX1 = 470, costX0 = 545, costX1 = W - 55;
  const ACC_LO = 0.25;
  const rowH = 22, groupGap = 30, top = 34;
  const groups = CORPORA.map((c) => {
    const picks = [ft(c.key), row(c.table, AZURE), cheapestFrontier(c.table), bestFrontier(c.table)];
    const seen = new Set();
    return { c, rows: picks.filter((r) => r && !seen.has(r.arm) && seen.add(r.arm)) };
  });
  const H = top + groups.reduce((n, g) => n + (g.rows.length + 1) * rowH + groupGap, 0);
  const s = svg("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": "Fields correct and cost per thousand pages for the fine-tune, Azure, the cheapest and the best frontier model on each form type" });
  const ax = linScale(ACC_LO, 1, accX0, accX1);
  const cx = logScale(0.01, 100, costX0, costX1);
  s.append(svg("text", { x: accX0, y: 14, class: "panel-title" }, "Fields correct"), svg("text", { x: costX0, y: 14, class: "panel-title" }, "US$ per 1,000 pages"));
  for (const v of [0.25, 0.5, 0.75, 1]) {
    s.append(svg("line", { x1: ax(v), x2: ax(v), y1: top - 8, y2: H - groupGap + 6, class: "gridline" }));
    s.append(svg("text", { x: ax(v), y: 28, "text-anchor": "middle", class: "tick" }, `${100 * v}%`));
  }
  for (const v of [0.01, 0.1, 1, 10, 100]) {
    s.append(svg("line", { x1: cx(v), x2: cx(v), y1: top - 8, y2: H - groupGap + 6, class: "gridline" }));
    s.append(svg("text", { x: cx(v), y: 28, "text-anchor": "middle", class: "tick" }, costTick(v)));
  }
  let y = top;
  const out = [];
  for (const g of groups) {
    s.append(svg("text", { x: 0, y: y + 14, class: "corpus-label" }, g.c.name));
    y += rowH;
    for (const r of g.rows) {
      const k = kind(r.arm);
      const mid = y + rowH / 2;
      s.append(svg("rect", { x: 0, y: y + 2, width: W, height: rowH - 4, rx: 4, class: "row-band", opacity: k === "finetuned" ? 1 : 0 }));
      s.append(svg("text", { x: 10, y: mid + 4, class: `mark-label${k === "finetuned" ? " strong" : ""}` }, short(r.arm)));
      const a = r.accuracy;
      s.append(svg("line", { x1: ax(a.low), x2: ax(a.high), y1: mid, y2: mid, class: `ci-line k-stroke-${k}` }));
      s.append(mark(k, ax(a.point), mid, 5));
      s.append(svg("text", { x: ax(a.high) + 8, y: mid + 4, class: `value-label${k === "finetuned" ? " strong" : ""}` }, pct(a.point)));
      const p = r.per_thousand;
      s.append(svg("line", { x1: cx(p.low), x2: cx(p.high), y1: mid, y2: mid, class: `ci-line k-stroke-${k}` }));
      s.append(mark(k, cx(p.point), mid, 5));
      s.append(svg("text", { x: cx(p.point) + 9, y: mid + 4, class: "value-label" }, usd(p.point)));
      out.push([`${g.c.name}: ${short(r.arm)}`, r.accuracy_text, r.per_thousand_text, r.price_date]);
      y += rowH;
    }
    y += groupGap;
  }
  host.replaceChildren(s);
  legend("h2h-legend", ["finetuned", "managed", "frontier"]);
  document.getElementById("h2h-caption").textContent = `Test sets read once by each reader. Intervals are 95% bootstrap over documents. Registration and ad-buy forms are the unseen-template splits. Prices: frontier ${state.story.prices.frontier} (batch rate), Azure ${state.story.prices.docintel}, the fine-tune's GPU ${state.story.prices.serve_checked}.`;
  register("h2h", ["Reader", "Fields correct (95% CI)", "US$ per 1,000 pages (95% CI)", "Price dated"], out);
}

// --- The landscape ------------------------------------------------------------------------

function drawLandscape() {
  const c = CORPUS[state.landscape];
  const t = table(c.table);
  const rows = t.rows.filter((r) => r.accuracy && r.per_thousand);
  // As wide as the column allows, the cost axis running to the right edge; labels near the
  // edge go to the left of their mark.
  const W = 1100, H = 500, L = 56, R = 24, T = 16, B = 46;
  const x = logScale(0.01, 100, L, W - R);
  const y = linScale(0, 1, H - B, T);
  const s = svg("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": `Fields correct against cost per thousand pages, ${c.name}` });
  for (const v of [0, 0.2, 0.4, 0.6, 0.8, 1]) {
    s.append(svg("line", { x1: L, x2: W - R, y1: y(v), y2: y(v), class: "gridline" }));
    s.append(svg("text", { x: L - 8, y: y(v) + 4, "text-anchor": "end", class: "tick" }, `${100 * v}%`));
  }
  for (const v of [0.01, 0.1, 1, 10, 100]) {
    s.append(svg("line", { x1: x(v), x2: x(v), y1: T, y2: H - B, class: "gridline" }));
    s.append(svg("text", { x: x(v), y: H - B + 16, "text-anchor": "middle", class: "tick" }, costTick(v)));
  }
  s.append(svg("text", { x: (L + W - R) / 2, y: H - 6, "text-anchor": "middle", class: "axis-title" }, "US$ per 1,000 pages, log scale"));
  s.append(svg("text", { x: 14, y: (T + H - B) / 2, transform: `rotate(-90 14 ${(T + H - B) / 2})`, "text-anchor": "middle", class: "axis-title" }, "Fields correct"));
  const readout = document.getElementById("landscape-readout");
  // Each label takes the first spot beside its mark that clears every mark and every label
  // already placed: right, left, above, below, then further out.
  const placed = [];
  const marks = rows.map((r) => ({ x: x(r.per_thousand.point), y: y(r.accuracy.point) }));
  const order = [...rows].sort((a, b) => b.accuracy.point - a.accuracy.point);
  for (const r of order) {
    const k = kind(r.arm);
    const px = x(r.per_thousand.point), py = y(r.accuracy.point);
    const g = svg("g", { tabindex: "0", role: "img", "aria-label": `${short(r.arm)}: ${r.accuracy_text} of fields, ${r.per_thousand_text} per 1,000 pages` });
    g.append(svg("line", { x1: x(r.per_thousand.low), x2: x(r.per_thousand.high), y1: py, y2: py, class: `ci-line k-stroke-${k}` }));
    g.append(svg("line", { x1: px, x2: px, y1: y(r.accuracy.low), y2: y(r.accuracy.high), class: `ci-line k-stroke-${k}` }));
    const m = mark(k, px, py, k === "finetuned" ? 7 : 6);
    g.append(m);
    const spot = placeLabel(placed, marks, px, py, short(r.arm).length * 6.3, W - 4);
    g.append(svg("text", { x: spot.x, y: spot.y, "text-anchor": spot.anchor, class: `mark-label halo${k === "finetuned" ? " strong" : ""}` }, short(r.arm)));
    const show = () => {
      m.classList.add("on");
      readout.replaceChildren(el("span", { class: "when", text: short(r.arm) }),
        el("span", { class: "pair" }, el("span", { class: "key", text: "fields right " }), r.accuracy_text),
        el("span", { class: "pair" }, el("span", { class: "key", text: "per 1,000 pages " }), r.per_thousand_text),
        r.invented_text ? el("span", { class: "pair" }, el("span", { class: "key", text: "invented " }), r.invented_text) : null,
        el("span", { class: "pair" }, el("span", { class: "key", text: "priced " }), r.price_date));
    };
    g.addEventListener("mouseenter", show);
    g.addEventListener("focus", show);
    g.addEventListener("mouseleave", () => m.classList.remove("on"));
    g.addEventListener("blur", () => m.classList.remove("on"));
    s.append(g);
  }
  document.getElementById("landscape-chart").replaceChildren(s);
  const kinds = [...new Set(rows.map((r) => kind(r.arm)))];
  legend("landscape-legend", ["finetuned", "frontier", "managed", "ocr-llm", "ocr-rules", "untuned"].filter((k) => kinds.includes(k)));
  const docs = t.rows[0].documents;
  document.getElementById("landscape-caption").textContent = `${t.title}: ${docs} documents, each read once by each reader. Whiskers are 95% bootstrap intervals over documents.`;
  register("landscape", ["Reader", "Fields correct (95% CI)", "Every field right", "Invented fields", "US$ per 1,000 pages (95% CI)", "Price dated"],
    t.rows.map((r) => [short(r.arm), r.accuracy_text, r.all_right_text, r.invented_text, r.per_thousand_text, r.price_date]), t.title);
}

function drawCorpusCards() {
  const by = state.story.corpora.by_corpus;
  document.getElementById("corpora-cards").replaceChildren(...CORPORA.map((c) => el("article", { class: "corpus-card" },
    el("h3", { text: c.name }),
    el("p", { text: c.about }),
    el("p", { class: "meta", text: `${int(by[c.key].documents)} documents, ${int(by[c.key].pages)} pages in all; ${table(c.table).rows[0].documents} in the test set${c.shown ? "" : "; never shown as images"}` }))));
}

// --- Training -----------------------------------------------------------------------------

function drawLift() {
  const W = 900, labelW = 210, x0 = labelW + 10, x1 = W - 70, rowH = 26, top = 30;
  const rows = [];
  for (const c of CORPORA) for (const size of ["2b", "4b"]) {
    const a = row(c.table, baseLabel(size)), b = row(c.table, ftLabel(size));
    if (a && b) rows.push({ c, size, a, b });
  }
  const H = top + rows.length * rowH + 12;
  const x = linScale(0, 1, x0, x1);
  const s = svg("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": "Fields correct before and after fine-tuning, per form type and size" });
  for (const v of [0, 0.25, 0.5, 0.75, 1]) {
    s.append(svg("line", { x1: x(v), x2: x(v), y1: top - 6, y2: H - 8, class: "gridline" }));
    s.append(svg("text", { x: x(v), y: 18, "text-anchor": "middle", class: "tick" }, `${100 * v}%`));
  }
  const out = [];
  rows.forEach((r, i) => {
    const mid = top + i * rowH + rowH / 2;
    if (r.size === "2b") s.append(svg("rect", { x: 0, y: mid - rowH / 2 + 1, width: W, height: rowH * 2 - 2, rx: 4, class: "row-band", opacity: (i / 2) % 2 ? 0 : 1 }));
    s.append(svg("text", { x: 10, y: mid + 4, class: "mark-label strong" }, `${r.size === "2b" ? r.c.name : ""}`));
    s.append(svg("text", { x: labelW - 10, y: mid + 4, "text-anchor": "end", class: "mark-label" }, `E${r.size[0]}B`));
    const from = r.a.accuracy.point, to = r.b.accuracy.point;
    s.append(svg("line", { x1: x(from), x2: x(to), y1: mid, y2: mid, class: "lift-arrow" }));
    s.append(mark("untuned", x(from), mid, 5));
    s.append(mark("finetuned", x(to), mid, 5.5));
    const gain = to - from;
    s.append(svg("text", { x: x(Math.max(from, to)) + 10, y: mid + 4, class: gain >= 0 ? "lift-gain" : "lift-loss" }, `${gain >= 0 ? "+" : "-"}${pts(gain)}`));
    out.push([`${r.c.name}, E${r.size[0]}B`, r.a.accuracy_text, r.b.accuracy_text, `${gain >= 0 ? "+" : "-"}${pts(gain)} points`]);
  });
  document.getElementById("lift").replaceChildren(s);
  document.getElementById("lift-caption").textContent = "Pale circle: the untuned base, prompted with the same instruction. Diamond: the same base after fine-tuning, seed 0. Test sets, level 0; registration and ad-buy forms on designs never seen in training.";
  register("lift", ["Form type and size", "Untuned", "Fine-tuned", "Change"], out);
}

function drawRecipes() {
  const host = document.getElementById("recipes");
  host.replaceChildren();
  for (const size of ["2b", "4b"]) {
    const runs = state.story.training.filter((t) => t.size === size);
    if (!runs.length) continue;
    const r = runs[0];
    const n = runs.map((t) => t.minutes);
    const lifts = CORPORA.map((c) => [row(c.table, baseLabel(size)), row(c.table, ftLabel(size))]).filter(([a, b]) => a && b);
    const mean = (xs) => xs.reduce((a, b) => a + b, 0) / xs.length;
    const from = mean(lifts.map(([a]) => a.accuracy.point)), to = mean(lifts.map(([, b]) => b.accuracy.point));
    const public_ = runs.filter((t) => t.hub);
    host.append(el("article", { class: "recipe" },
      el("h3", { text: `Gemma 4 E${size[0]}B` }),
      el("p", { class: "maker", text: `google/gemma-4-E${size[0]}B, Apache 2.0, ${runs.length} adapters` }),
      el("div", { class: "lift" }, el("span", { class: "from", text: pct(from) }), el("span", { class: "arrow", text: "→" }), el("span", { class: "to", text: pct(to) })),
      el("p", { class: "lift-note", text: "fields right, the mean over the four form types, untuned and fine-tuned" }),
      el("dl", {},
        el("dt", { text: "Adapter" }), el("dd", { text: `LoRA rank ${r.rank}, alpha ${r.alpha}` }),
        el("dt", { text: "Base" }), el("dd", { text: "4-bit NF4, double quantisation, bf16 compute" }),
        el("dt", { text: "Learning rate" }), el("dd", { text: `${r.learning_rate}, cosine, ${r.epochs} epoch` }),
        el("dt", { text: "Batch" }), el("dd", { text: `1 document, ${r.grad_accum} steps accumulated` }),
        el("dt", { text: "Image" }), el("dd", { text: `${int(r.visual_tokens)} visual tokens a page` }),
        el("dt", { text: "Sequence" }), el("dd", { text: `up to ${int(r.max_seq_len)} tokens` }),
        el("dt", { text: "Training time" }), el("dd", { text: `${minutes(Math.min(...n))} to ${minutes(Math.max(...n))} an adapter` })),
      el("p", { class: "links" }, ...(public_.length
        ? [`On Hugging Face: `, ...public_.flatMap((t, i) => [i ? ", " : "", el("a", { href: t.hub, text: CORPUS[t.dataset.split("-")[0]].noun })]), "; the registration-form adapters stay private."]
        : ["The adapters stay private."]))));
  }
}

function drawMinutes() {
  const runs = [...state.story.training].sort((a, b) => CORPORA.findIndex((c) => a.dataset.startsWith(c.key)) - CORPORA.findIndex((c) => b.dataset.startsWith(c.key)) || a.dataset.localeCompare(b.dataset) || a.size.localeCompare(b.size));
  const W = 900, labelW = 290, x0 = labelW, x1 = W - 150, rowH = 20, top = 28;
  const H = top + runs.length * rowH + 10;
  const maxM = Math.max(...runs.map((r) => r.minutes));
  const x = linScale(0, Math.ceil(maxM / 60) * 60, x0, x1);
  const s = svg("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": "Training minutes per adapter" });
  for (let m = 0; m <= Math.ceil(maxM / 60) * 60; m += 60) {
    s.append(svg("line", { x1: x(m), x2: x(m), y1: top - 6, y2: H - 6, class: "gridline" }));
    s.append(svg("text", { x: x(m), y: 16, "text-anchor": "middle", class: "tick" }, m ? `${m / 60} h` : "0"));
  }
  const name = (d) => {
    const c = CORPORA.find((k) => d.startsWith(k.key));
    const held = d.match(/unseen-(.+)-s0/);
    return held && c.key === "fara" ? `${c.name}, ${held[1].replaceAll("_", " ").replace("-", " ")} held out` : c.name;
  };
  const out = [];
  runs.forEach((r, i) => {
    const mid = top + i * rowH + rowH / 2;
    s.append(svg("text", { x: labelW - 10, y: mid + 4, "text-anchor": "end", class: "mark-label" }, `${name(r.dataset)}, E${r.size[0]}B`));
    s.append(svg("rect", { x: x0, y: mid - 6, width: Math.max(1, x(r.minutes) - x0), height: 12, rx: 2, class: `bar-fill k-fill-finetuned${r.size === "4b" ? " light" : ""}` }));
    s.append(svg("text", { x: x(r.minutes) + 6, y: mid + 4, class: "value-label" }, `${minutes(r.minutes)}, ${int(r.documents)} docs`));
    out.push([`${name(r.dataset)}, E${r.size[0]}B`, minutes(r.minutes), int(r.documents), String(r.steps), r.train_loss.toFixed(3)]);
  });
  document.getElementById("minutes").replaceChildren(s);
  document.getElementById("minutes-caption").textContent = "Wall time of each headline adapter's training run, start to finish, on one rented 24 or 48 GB card (RunPod, US$0.27 to US$0.89 an hour, 2026-10-18). Dark: E2B; light: E4B. The tax forms take longest: twenty faces in one model, every field of a face in its prompt.";
  register("minutes", ["Adapter", "Training time", "Documents", "Optimiser steps", "Final train loss"], out);
}

// The three ablations, each change's paired difference from the E2B it changes, in points.
const ABLATION_SETS = { "visual-tokens": ["FARA, unseen templates", "DeepForm, unseen templates", "CORD", "NIST"] };
const ABLATION_NAMES = { "FARA, unseen templates": "Registration, unseen designs", "DeepForm, unseen templates": "Ad-buy, unseen designs", "FARA, mixed templates": "Registration, designs seen", "DeepForm, mixed templates": "Ad-buy, designs seen", CORD: "Receipts", NIST: "Tax forms" };
const ABLATION_HEADS = { "visual-tokens": "Half the visual tokens (560 a page, not 1,120)", volume: "Fewer training documents (of 800)", "multi-corpus": "One model for every form type" };

function drawAblations() {
  const abl = state.story.ablations || [];
  const rows = [];
  for (const a of abl) {
    rows.push({ head: ABLATION_HEADS[a.key] || a.title });
    const keep = ABLATION_SETS[a.key];
    for (const set of a.sets.filter((x) => !keep || keep.includes(x.name))) {
      set.rows.slice(1).forEach((r, j) => {
        const n = a.key === "volume" ? `, ${r.label.match(/(\d+) documents/)[1]}` : "";
        rows.push({ label: `${ABLATION_NAMES[set.name] || set.name}${n}`, d: set.deltas[j + 1], ref: set.rows[0], r });
      });
    }
  }
  const W = 900, labelW = 280, x0 = labelW, x1 = W - 150, rowH = 22, top = 28;
  const H = top + rows.length * rowH + 8;
  const lo = -0.4, hi = 0.1;
  const x = linScale(lo, hi, x0, x1);
  const s = svg("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": "Each recipe change's difference in fields correct from the recipe it changes" });
  for (let v = lo; v <= hi + 1e-9; v += 0.1) {
    s.append(svg("line", { x1: x(v), x2: x(v), y1: top - 6, y2: H - 6, class: Math.abs(v) < 1e-9 ? "zero" : "gridline" }));
    s.append(svg("text", { x: x(v), y: 16, "text-anchor": "middle", class: "tick" }, `${v > 1e-9 ? "+" : ""}${Math.round(100 * v)}`));
  }
  const out = [];
  rows.forEach((r, i) => {
    const mid = top + i * rowH + rowH / 2;
    if (r.head) { s.append(svg("text", { x: 10, y: mid + 4, class: "mark-label strong" }, r.head)); return; }
    s.append(svg("text", { x: labelW - 10, y: mid + 4, "text-anchor": "end", class: "mark-label" }, r.label));
    if (!r.d) {
      s.append(svg("text", { x: x(0) + 8, y: mid + 4, class: "value-label" }, "not measured"));
      out.push([r.label, r.ref.accuracy_text, "not measured", ""]);
      return;
    }
    s.append(svg("line", { x1: x(Math.max(lo, r.d.low)), x2: x(Math.min(hi, r.d.high)), y1: mid, y2: mid, class: "ci-line k-stroke-finetuned" }));
    s.append(mark("finetuned", x(r.d.point), mid, 5));
    const text = `${r.d.point >= 0 ? "+" : "-"}${pts(r.d.point)} points`;
    s.append(svg("text", { x: x1 + 14, y: mid + 4, class: r.d.high < 0 ? "lift-loss" : r.d.low > 0 ? "lift-gain" : "value-label" }, text));
    out.push([r.label, r.ref.accuracy_text, r.r.accuracy_text, `${text} (${r.d.low >= 0 ? "+" : "-"}${pts(r.d.low)} to ${r.d.high >= 0 ? "+" : "-"}${pts(r.d.high)})`]);
  });
  document.getElementById("ablations").replaceChildren(s);
  document.getElementById("ablations-caption").textContent = "Each change trained on Gemma 4 E2B at seed 0 and read like the headline models, against the seed-0 E2B whose recipe it changes. The difference is in points of fields correct, paired over the documents both read, with its 95% interval. Test sets, level 0.";
  register("ablations", ["Change and form type", "Headline recipe", "Changed", "Difference (95% CI)"], out);
}

// --- Serving ------------------------------------------------------------------------------

function drawServing() {
  const corpus = state.serving;
  const runs = state.story.serving.filter((r) => r.corpus === corpus).sort((a, b) => a.size.localeCompare(b.size));
  const W = 900, H = 300, gap = 70, panelW = (W - 60 - gap) / 2, T = 26, B = 40;
  const s = svg("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": `Throughput and latency at 1, 8 and 32 requests in flight, ${CORPUS[corpus].name}` });
  const panels = [
    { title: "Pages a second", x0: 50, get: (lv) => lv.pages_per_second, f: (v) => v.toFixed(2) },
    { title: "Seconds to read one document (p50)", x0: 50 + panelW + gap, get: (lv) => lv.read_p50_s, f: (v) => v.toFixed(1) },
  ];
  const levels = [1, 8, 32];
  const out = [];
  for (const p of panels) {
    const [max, step] = nice(Math.max(...runs.flatMap((r) => r.levels.map((lv) => (p.get(lv) ? p.get(lv).high : 0)))) * 1.12);
    const y = linScale(0, max, H - B, T);
    s.append(svg("text", { x: p.x0, y: 14, class: "panel-title" }, p.title));
    for (let v = 0; v <= max + 1e-9; v += step) {
      s.append(svg("line", { x1: p.x0, x2: p.x0 + panelW, y1: y(v), y2: y(v), class: "gridline" }));
      s.append(svg("text", { x: p.x0 - 6, y: y(v) + 4, "text-anchor": "end", class: "tick" }, step < 1 ? v.toFixed(1) : int(v)));
    }
    const groupW = panelW / levels.length, barW = Math.min(36, (groupW - 24) / Math.max(1, runs.length));
    levels.forEach((c, gi) => {
      const gx = p.x0 + gi * groupW + groupW / 2;
      s.append(svg("text", { x: gx, y: H - B + 16, "text-anchor": "middle", class: "tick" }, `${c} in flight`));
      runs.forEach((r, ri) => {
        const lv = r.levels.find((l) => l.concurrency === c);
        const m = lv && p.get(lv);
        if (!m) return;
        const bx = gx + (ri - runs.length / 2) * barW + 2;
        s.append(svg("rect", { x: bx, y: y(m.point), width: barW - 4, height: H - B - y(m.point), rx: 2, class: `bar-fill k-fill-finetuned${r.size === "4b" ? " light" : ""}` }));
        s.append(svg("line", { x1: bx + (barW - 4) / 2, x2: bx + (barW - 4) / 2, y1: y(m.low), y2: y(m.high), class: "whisker" }));
        s.append(svg("text", { x: bx + (barW - 4) / 2, y: y(m.high) - 5, "text-anchor": "middle", class: "value-label" }, p.f(m.point)));
      });
    });
  }
  for (const r of runs) for (const lv of r.levels) {
    if (!lv.pages_per_second) continue;
    out.push([`E${r.size[0]}B, ${lv.concurrency} in flight`, `${lv.reads} (${lv.errors})`, lv.pages_per_read.toFixed(1),
      `${lv.pages_per_second.point.toFixed(2)} (${lv.pages_per_second.low.toFixed(2)} to ${lv.pages_per_second.high.toFixed(2)})`,
      `${lv.read_p50_s.point.toFixed(1)} s (${lv.read_p50_s.low.toFixed(1)} to ${lv.read_p50_s.high.toFixed(1)})`,
      `${lv.read_p99_s.point.toFixed(1)} s`, `${lv.first_token_p50_s.point.toFixed(1)} s`]);
  }
  document.getElementById("serving-chart").replaceChildren(s);
  legend("serving-legend", [], [
    el("span", { class: "legend-item" }, el("span", { class: "swatch solid sw-finetuned" }), "Gemma 4 E2B fine-tune"),
    el("span", { class: "legend-item" }, el("span", { class: "swatch solid sw-finetuned light" }), "Gemma 4 E4B fine-tune")]);
  const r0 = runs[0];
  document.getElementById("serving-caption").textContent = `${CORPUS[corpus].name}: each fine-tune served alone on one ${r0.gpu} (${usd(r0.usd_per_hour)} an hour, ${r0.provider}, ${r0.checked}) and read on its own test documents. Whiskers are 95% bootstrap intervals over reads; the first 30 seconds of each level are discarded.${corpus === "fara" ? " The registration-form models served are the ones with the amendment template held out." : ""}`;
  register("serving", ["Fine-tune and load", "Reads (errors)", "Pages a read", "Pages a second (95% CI)", "Read p50 (95% CI)", "Read p99", "First token p50"], out);

  const g = runs.find((r) => r.gated) || runs[0];
  const pps = g.best.pages_per_second.point;
  const month = pps * 3600 * 730.5;
  const p50at8 = g.levels.find((l) => l.concurrency === 8);
  document.getElementById("serving-stats").replaceChildren(
    stat(`${pps.toFixed(2)}`, `pages a second from the E${g.size[0]}B at ${g.best.concurrency} in flight, the one the gate compared`),
    stat(big(month), "pages a month from one card at that rate, if it never sits idle"),
    stat(usd(g.usd_per_hour * 730.5), `a month to rent the card, at ${usd(g.usd_per_hour)} an hour`),
    stat(usd((1000 * g.usd_per_hour) / (pps * 3600)), "per 1,000 pages with the card kept busy"),
    p50at8 && p50at8.read_p50_s ? stat(`${p50at8.read_p50_s.point.toFixed(1)} s`, "to read one document, at 8 in flight (median)") : null);
}

function stat(figure, caption) {
  return el("div", { class: "stat" }, el("span", { class: "figure", text: figure }), el("span", { class: "caption", text: caption }));
}

// --- The break-even calculator ------------------------------------------------------------

const calc = { served: null, api: null, apiLabel: null };

function setupCalculator() {
  const sel = document.getElementById("calc-served");
  const runs = [...state.story.serving].sort((a, b) => (b.gated - a.gated) || CORPORA.findIndex((c) => c.key === a.corpus) - CORPORA.findIndex((c) => c.key === b.corpus));
  for (const r of runs) sel.append(el("option", { value: r.model, text: `${CORPUS[r.corpus].name}, E${r.size[0]}B: ${r.best.pages_per_second.point.toFixed(2)} pages/s` }));
  sel.addEventListener("change", () => pickServed(sel.value, true));
  for (const id of ["calc-rate", "calc-api", "calc-fixed", "calc-util", "calc-volume"]) {
    document.getElementById(id).addEventListener("input", () => {
      if (id === "calc-api") { calc.apiLabel = null; markPreset(); }
      updateCalculator();
    });
  }
  pickServed(runs[0].model, true);
}

function pickServed(model, resetApi) {
  const r = state.story.serving.find((x) => x.model === model);
  calc.served = r;
  document.getElementById("calc-served").value = model;
  document.getElementById("calc-rate").value = r.usd_per_hour.toFixed(2);
  document.getElementById("calc-rate-hint").textContent = `${r.gpu}, ${r.provider}, ${r.checked}`;
  const key = CORPUS[r.corpus].table;
  const presets = table(key).rows.filter((x) => ["frontier", "managed"].includes(kind(x.arm)) && x.per_thousand);
  const host = document.getElementById("calc-api-presets");
  host.replaceChildren(...presets.map((p) => {
    const b = el("button", { type: "button", class: "chip", "data-arm": p.arm, "aria-pressed": "false", text: `${short(p.arm)}, ${usd(p.per_thousand.point)}` });
    b.addEventListener("click", () => { setApi(p); updateCalculator(); });
    return b;
  }));
  if (resetApi || calc.api === null) setApi(presets.find((p) => p.arm === AZURE) || presets[0]);
  updateCalculator();
}

function setApi(p) {
  calc.apiLabel = p.arm;
  document.getElementById("calc-api").value = p.per_thousand.point.toFixed(2);
  document.getElementById("calc-api-hint").textContent = `${short(p.arm)} on these forms, priced ${p.price_date}`;
  markPreset();
}

function markPreset() {
  for (const b of document.querySelectorAll("#calc-api-presets .chip")) b.setAttribute("aria-pressed", b.getAttribute("data-arm") === calc.apiLabel ? "true" : "false");
  if (!calc.apiLabel) document.getElementById("calc-api-hint").textContent = "your own price";
}

function calcInputs() {
  const num = (id, lo) => { const v = Number(document.getElementById(id).value); return Number.isFinite(v) && v > lo ? v : null; };
  const rate = num("calc-rate", 0), api = num("calc-api", 0);
  const fixed = Math.max(0, Number(document.getElementById("calc-fixed").value) || 0);
  if (rate === null || api === null) return null;
  return { usdPerHour: rate, requestsPerSecond: calc.served.best.pages_per_second.point, apiUsdPerCall: api / 1000, fixedUsdPerMonth: fixed, hoursPerMonth: 730.5, secondsPerHour: 3600 };
}

function updateCalculator() {
  const u = Number(document.getElementById("calc-util").value) / 100;
  document.getElementById("calc-util-out").textContent = `${Math.round(u * 100)}%`;
  const volume = Math.round(10 ** Number(document.getElementById("calc-volume").value));
  document.getElementById("calc-volume-out").textContent = `${big(volume)} pages`;
  const inputs = calcInputs();
  if (!inputs) return;
  const B = window.Breakeven;
  const p = B.breakEven(inputs, u);
  const evenEl = document.getElementById("out-even");
  if (p.volumePerMonth === null) {
    evenEl.textContent = "Never";
    evenEl.classList.add("never");
    document.getElementById("out-even-note").textContent = "at this load one card costs more a page than paying by the page";
  } else {
    evenEl.textContent = big(p.volumePerMonth);
    evenEl.classList.remove("never");
    document.getElementById("out-even-note").textContent = `pages a month and the card is the cheaper${p.gpus > 1 ? `, on ${p.gpus} cards` : ""}`;
  }
  document.getElementById("out-own").textContent = usd(1000 * p.selfHostedUsdPerCall);
  document.getElementById("out-own-note").textContent = `per 1,000 pages on the card at ${Math.round(u * 100)}% busy`;
  const apiMonth = volume * inputs.apiUsdPerCall;
  const ownMonth = B.selfHostedMonthly(inputs, volume, u);
  document.getElementById("out-month-api").textContent = usd(apiMonth);
  document.getElementById("out-month-api-note").textContent = `a month paying by the page for ${big(volume)} pages`;
  document.getElementById("out-month-own").textContent = usd(ownMonth);
  const cards = Math.max(1, Math.ceil(volume / B.capacity(inputs, u)));
  document.getElementById("out-month-own-note").textContent = `a month on ${cards} rented card${cards > 1 ? "s" : ""}${ownMonth < apiMonth ? `, ${usd(apiMonth - ownMonth)} less` : ""}`;
  drawMonth(inputs, u, volume, p);
}

function drawMonth(inputs, u, volume, p) {
  const B = window.Breakeven;
  const W = 900, H = 330, L = 70, R = 24, T = 16, Bm = 44;
  const vLo = 1e3, vHi = 10 ** 7.5;
  const x = logScale(vLo, vHi, L, W - R);
  const costs = [vLo * inputs.apiUsdPerCall, vHi * inputs.apiUsdPerCall, B.selfHostedMonthly(inputs, vLo, u), B.selfHostedMonthly(inputs, vHi, u)];
  const cLo = 10 ** Math.floor(Math.log10(Math.max(1, Math.min(...costs)))), cHi = 10 ** Math.ceil(Math.log10(Math.max(...costs)));
  const y = logScale(cLo, cHi, H - Bm, T);
  const s = svg("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": "Monthly cost against monthly pages, paid by the page and on rented cards" });
  for (let v = cLo; v <= cHi; v *= 10) {
    s.append(svg("line", { x1: L, x2: W - R, y1: y(v), y2: y(v), class: "gridline" }));
    s.append(svg("text", { x: L - 8, y: y(v) + 4, "text-anchor": "end", class: "tick" }, `$${big(v)}`));
  }
  for (let v = 1e3; v <= vHi; v *= 10) {
    s.append(svg("line", { x1: x(v), x2: x(v), y1: T, y2: H - Bm, class: "gridline" }));
    s.append(svg("text", { x: x(v), y: H - Bm + 16, "text-anchor": "middle", class: "tick" }, big(v)));
  }
  s.append(svg("text", { x: (L + W - R) / 2, y: H - 6, "text-anchor": "middle", class: "axis-title" }, "Pages a month, log scale"));
  s.append(svg("path", { d: `M${x(vLo)},${y(vLo * inputs.apiUsdPerCall)}L${x(vHi)},${y(vHi * inputs.apiUsdPerCall)}`, class: "api-line" }));
  let d = "";
  const steps = 400;
  for (let i = 0; i <= steps; i++) {
    const v = vLo * (vHi / vLo) ** (i / steps);
    const c = B.selfHostedMonthly(inputs, v, u);
    d += `${i ? "L" : "M"}${x(v).toFixed(1)},${y(c).toFixed(1)}`;
  }
  s.append(svg("path", { d, class: "own-line" }));
  if (p.volumePerMonth !== null && p.volumePerMonth >= vLo && p.volumePerMonth <= vHi) {
    const ex = x(p.volumePerMonth);
    s.append(svg("line", { x1: ex, x2: ex, y1: T, y2: H - Bm, class: "even-mark" }));
    s.append(svg("text", { x: ex + 6, y: T + 12, class: "even-label" }, `break-even, ${big(p.volumePerMonth)}`));
  }
  const vx = x(volume);
  s.append(svg("line", { x1: vx, x2: vx, y1: T, y2: H - Bm, class: "you-mark" }));
  s.append(svg("text", { x: vx + 6, y: H - Bm - 8, class: "you-label" }, "you"));
  document.getElementById("month").replaceChildren(s);
}

// --- Bad scans ----------------------------------------------------------------------------

const SCAN_SETS = [
  ["nist", "Tax forms, 300 pages, levels 0 to 4"],
  ["fara", "Registration forms, 39 real scans"],
  ["deepform", "Ad-buy forms, 30 real scans"],
];

function scanCurve() { return curve(state.scans); }

function drawScans() {
  const c = scanCurve();
  if (!c) return;
  const labels = Object.keys(c.cells).filter((l) => c.levels.some((lv) => c.cells[l][String(lv)] && c.cells[l][String(lv)].accuracy));
  const W = 900, H = 420, L = 56, R = 210, T = 16, B = 44;
  const x = linScale(c.levels[0], c.levels[c.levels.length - 1], L + 10, W - R - 10);
  const y = linScale(0, 1, H - B, T);
  const s = svg("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": `Fields correct at each degradation level, ${c.title}` });
  for (const v of [0, 0.2, 0.4, 0.6, 0.8, 1]) {
    s.append(svg("line", { x1: L, x2: W - R, y1: y(v), y2: y(v), class: "gridline" }));
    s.append(svg("text", { x: L - 8, y: y(v) + 4, "text-anchor": "end", class: "tick" }, `${100 * v}%`));
  }
  for (const lv of c.levels) {
    s.append(svg("line", { x1: x(lv), x2: x(lv), y1: T, y2: H - B, class: "gridline" }));
    s.append(svg("text", { x: x(lv), y: H - B + 16, "text-anchor": "middle", class: "tick" }, lv === 0 ? "0, clean" : `level ${lv}`));
  }
  s.append(svg("text", { x: (L + W - R) / 2, y: H - 6, "text-anchor": "middle", class: "axis-title" }, "Scan degradation"));
  const ends = [];
  for (const label of labels) {
    if (state.scansOff.has(label)) continue;
    const k = kind(label);
    const pts_ = c.levels.map((lv) => [lv, c.cells[label][String(lv)]]).filter(([, cell]) => cell && cell.accuracy);
    if (pts_.length > 1) {
      let band = pts_.map(([lv, cell], i) => `${i ? "L" : "M"}${x(lv)},${y(cell.accuracy.high)}`).join("");
      band += [...pts_].reverse().map(([lv, cell]) => `L${x(lv)},${y(cell.accuracy.low)}`).join("") + "Z";
      s.append(svg("path", { d: band, class: `curve-band k-fill-${k}` }));
      s.append(svg("path", { d: pts_.map(([lv, cell], i) => `${i ? "L" : "M"}${x(lv)},${y(cell.accuracy.point)}`).join(""), class: `curve-line k-stroke-${k}` }));
    }
    for (const [lv, cell] of pts_) s.append(mark(k, x(lv), y(cell.accuracy.point), 4));
    const [lvN, last] = pts_[pts_.length - 1];
    ends.push({ label, k, x: x(lvN), y: y(last.accuracy.point) });
  }
  ends.sort((a, b) => a.y - b.y);
  let prev = -Infinity;
  for (const e of ends) {
    const ly = Math.max(e.y + 4, prev + 12);
    prev = ly;
    s.append(svg("text", { x: W - R + 12, y: ly, class: `mark-label${e.k === "finetuned" ? " strong" : ""}` }, short(e.label)));
  }
  // The readout follows the pointer to the nearest level.
  const catcher = svg("rect", { x: L, y: T, width: W - R - L, height: H - B - T, fill: "transparent", class: "catcher" });
  const cursor = svg("line", { x1: 0, x2: 0, y1: T, y2: H - B, class: "cursor", visibility: "hidden" });
  s.append(cursor, catcher);
  const readout = document.getElementById("scans-readout");
  catcher.addEventListener("pointermove", (ev) => {
    const box = s.getBoundingClientRect();
    const px = ((ev.clientX - box.left) / box.width) * W;
    const lv = c.levels.reduce((a, b) => (Math.abs(x(b) - px) < Math.abs(x(a) - px) ? b : a));
    cursor.setAttribute("x1", x(lv)); cursor.setAttribute("x2", x(lv)); cursor.setAttribute("visibility", "visible");
    const items = labels.filter((l) => !state.scansOff.has(l) && c.cells[l][String(lv)] && c.cells[l][String(lv)].accuracy)
      .sort((a, b) => c.cells[b][String(lv)].accuracy.point - c.cells[a][String(lv)].accuracy.point);
    readout.replaceChildren(el("span", { class: "when", text: lv === 0 ? "Clean" : `Level ${lv}` }),
      ...items.map((l) => el("span", { class: "pair" }, el("span", { class: "key", text: `${short(l)} ` }), pct(c.cells[l][String(lv)].accuracy.point))));
  });
  catcher.addEventListener("pointerleave", () => cursor.setAttribute("visibility", "hidden"));
  document.getElementById("scans-chart").replaceChildren(s);
  const host = document.getElementById("scans-legend");
  host.replaceChildren(...labels.map((l) => {
    const b = el("button", { type: "button", class: "legend-item", "aria-pressed": state.scansOff.has(l) ? "false" : "true" }, el("span", { class: `swatch solid sw-${kind(l)}` }), short(l));
    b.addEventListener("click", () => { if (state.scansOff.has(l)) state.scansOff.delete(l); else state.scansOff.add(l); drawScans(); });
    return b;
  }));
  document.getElementById("scans-caption").textContent = `${c.title}. ${c.documents} documents at every level; the band is the 95% bootstrap interval over documents. Select a reader in the legend to hide or show it. What each level does to OCR's word accuracy is in the repository's docs/degradation.md.`;
  register("scans", ["Reader", ...c.levels.map((lv) => (lv === 0 ? "Clean" : `Level ${lv}`))],
    labels.map((l) => [short(l), ...c.levels.map((lv) => (c.cells[l][String(lv)] ? c.cells[l][String(lv)].text : ""))]), c.title);
}

// --- Surprises ----------------------------------------------------------------------------

function dumbbells(hostId, rows, opts) {
  const W = 900, labelW = opts.labelW || 200, x0 = labelW + 10, x1 = W - (opts.noteW || 120), rowH = 28, top = 28;
  const H = top + rows.length * rowH + 8;
  const x = linScale(opts.lo || 0, opts.hi || 1, x0, x1);
  const s = svg("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": opts.aria });
  for (let v = opts.lo || 0; v <= (opts.hi || 1) + 1e-9; v += opts.step || 0.25) {
    s.append(svg("line", { x1: x(v), x2: x(v), y1: top - 6, y2: H - 6, class: "gridline" }));
    s.append(svg("text", { x: x(v), y: 18, "text-anchor": "middle", class: "tick" }, `${Math.round(100 * v)}%`));
  }
  rows.forEach((r, i) => {
    const mid = top + i * rowH + rowH / 2;
    s.append(svg("text", { x: 10, y: mid + 4, class: "mark-label strong" }, r.label));
    s.append(svg("line", { x1: x(r.a.point), x2: x(r.b.point), y1: mid, y2: mid, class: "lift-arrow" }));
    for (const [v, k] of [[r.a, r.ka], [r.b, r.kb]]) {
      s.append(svg("line", { x1: x(v.low), x2: x(v.high), y1: mid, y2: mid, class: `ci-line k-stroke-${k}` }));
      s.append(mark(k, x(v.point), mid, 5.5));
    }
    s.append(svg("text", { x: x1 + 14, y: mid + 4, class: "value-label" }, r.note));
  });
  document.getElementById(hostId).replaceChildren(s);
}

function drawCeiling() {
  const rows = state.story.ceiling.map((c) => ({
    label: `${CORPUS[c.corpus.toLowerCase()].name}, ${c.documents} documents`, a: c.second, ka: "frontier", b: c.first, kb: "opus",
    note: `${usd(c.first_cost.point)} against ${usd(c.second_cost.point)} a 1,000`,
  }));
  dumbbells("ceiling", rows, { lo: 0.5, hi: 1, step: 0.1, labelW: 230, noteW: 210, aria: "Opus 5.5 against Sonnet 5.5, fields correct per form type" });
  register("ceiling", ["Form type", "Documents", "Opus 5.5", "Sonnet 5.5", "Opus per 1,000 pages", "Sonnet per 1,000 pages"],
    state.story.ceiling.map((c) => [CORPUS[c.corpus.toLowerCase()].name, String(c.documents), c.first_text, c.second_text, usd(c.first_cost.point), usd(c.second_cost.point)]),
    "Ceiling subset of the headline test documents, batch rate, fields correct with 95% CI over documents.");
}

function drawGap() {
  const labels = [ftLabel("2b"), ftLabel("4b"), SONNET, HAIKU, "A, GPT-6.1 Sol on the image", "A, Gemini 3.8 Flash on the image"];
  const rows = [];
  const out = [];
  for (const c of CORPORA.filter((k) => k.gap)) for (const l of labels) {
    const seen = row(c.gap, l), unseen = row(c.table, l);
    if (!seen || !unseen) continue;
    const k = kind(l);
    const d = unseen.accuracy.point - seen.accuracy.point;
    rows.push({ label: `${c.name}: ${short(l)}`, a: seen.accuracy, ka: "untuned", b: unseen.accuracy, kb: k, note: `${d >= 0 ? "+" : "-"}${pts(d)} on unseen` });
    out.push([`${c.name}: ${short(l)}`, seen.accuracy_text, unseen.accuracy_text]);
  }
  dumbbells("gap", rows, { lo: 0.4, hi: 0.9, step: 0.1, labelW: 330, aria: "Fields correct on seen and unseen form designs" });
  register("gap", ["Reader", "Designs seen in training", "Designs never seen"], out, "Pale circle: test forms of designs the fine-tunes trained on. Coloured mark: designs none of them saw.");
}

function drawNoise() {
  const rows = state.story.noise.filter((n) => n.changed);
  const W = 420, labelW = 120, x0 = labelW, x1 = W - 60, rowH = 24, top = 22;
  const H = top + rows.length * rowH + 6;
  const max = Math.max(...rows.map((r) => r.changed.high)) * 1.1;
  const x = linScale(0, max, x0, x1);
  const s = svg("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": "Share of fields whose outcome changed on a second read" });
  for (let v = 0; v <= max; v += 0.05) {
    s.append(svg("line", { x1: x(v), x2: x(v), y1: top - 6, y2: H - 4, class: "gridline" }));
    s.append(svg("text", { x: x(v), y: 14, "text-anchor": "middle", class: "tick" }, `${Math.round(100 * v)}%`));
  }
  rows.forEach((r, i) => {
    const mid = top + i * rowH + rowH / 2;
    s.append(svg("text", { x: labelW - 8, y: mid + 4, "text-anchor": "end", class: "mark-label" }, CORPUS[r.corpus.toLowerCase()].name));
    s.append(svg("rect", { x: x0, y: mid - 6, width: Math.max(1, x(r.changed.point) - x0), height: 12, rx: 2, class: "bar-fill k-fill-frontier" }));
    s.append(svg("line", { x1: x(r.changed.low), x2: x(r.changed.high), y1: mid, y2: mid, class: "whisker" }));
    s.append(svg("text", { x: x(r.changed.high) + 6, y: mid + 4, class: "value-label" }, pct(r.changed.point)));
  });
  document.getElementById("noise").replaceChildren(s);
}

// --- The page viewer ----------------------------------------------------------------------

const VIEW_CURVE = { nist: "nist", deepform: "deepform" };
const VIEW_TABLE = { cord: "cord" };

function fieldName(f) { return f.item !== null && f.item !== undefined ? `${f.path} #${f.item + 1}` : f.path; }
function clip(s, n) {
  if (s === null || s === undefined) return "(blank)";
  return s.length > n ? `${s.slice(0, n - 3)}...` : s;
}

function setupViewer() {
  const corpora = Object.keys(state.index.pages);
  state.corpus = corpora.includes("nist") ? "nist" : corpora[0];
  state.page = state.index.pages[state.corpus][0].id;
  state.arm = ftLabel(gatedSize(state.corpus));
  chips("corpora", corpora.map((c) => [c, CORPUS[c] ? CORPUS[c].name : c]), state.corpus, (c) => selectCorpus(c));
  const sel = document.getElementById("arm");
  for (const a of state.index.arms) sel.append(el("option", { value: a.label, text: short(a.label) }));
  sel.value = state.arm;
  renderPageSelect();
  document.getElementById("page").addEventListener("change", (e) => { state.page = e.target.value; loadPage(); });
  sel.addEventListener("change", (e) => { state.arm = e.target.value; drawPage(); });
  document.getElementById("level").addEventListener("input", (e) => { state.level = state.record.levels[Number(e.target.value)]; drawPage(); });
  document.getElementById("labels").addEventListener("change", drawPage);
  document.getElementById("wrong-only").addEventListener("change", drawPage);
  return loadPage();
}

function renderPageSelect() {
  const sel = document.getElementById("page");
  sel.replaceChildren(...state.index.pages[state.corpus].map((p, i) => el("option", { value: p.id, text: `Page ${i + 1}: ${p.doc}${p.pages > 1 ? ` (${p.pages} pages)` : ""}` })));
  sel.value = state.page;
}

async function selectCorpus(c) {
  state.corpus = c;
  state.page = state.index.pages[c][0].id;
  renderPageSelect();
  await loadPage();
}

async function loadPage() {
  state.record = await getJson(`data/pages/${state.page}.json`);
  const levels = state.record.levels;
  if (!levels.includes(state.level)) state.level = levels.reduce((a, b) => (Math.abs(b - state.level) < Math.abs(a - state.level) ? b : a));
  const slider = document.getElementById("level");
  slider.max = String(levels.length - 1);
  slider.value = String(levels.indexOf(state.level));
  slider.disabled = levels.length < 2;
  document.getElementById("level-note").textContent = levels.length < 2 ? "receipts were read at the clean scan only" : `levels ${levels.join(", ")} were read`;
  drawPage();
}

function drawPage() {
  const rec = state.record;
  const lv = String(state.level);
  document.getElementById("level-name").textContent = state.level === 0 ? "level 0, clean" : `level ${state.level}`;
  const read = (rec.reads[lv] || {})[state.arm] || null;
  const boxes = rec.boxes[lv] || {};
  const labelWrong = document.getElementById("labels").checked;
  const sheets = document.getElementById("sheets");
  sheets.replaceChildren();
  const placed = [], unplaced = [];
  for (const f of read ? read.fields : []) (f.key && boxes[f.key] ? placed : unplaced).push(f);
  rec.pages.forEach((p, i) => {
    const sheet = el("div", { class: "sheet" });
    const img = el("img", { src: rec.images[lv][i], alt: `${CORPUS[rec.corpus].name}, page ${i + 1}, scan level ${state.level}`, width: p.width, height: p.height });
    const over = svg("svg", { viewBox: `0 0 ${p.width} ${p.height}`, preserveAspectRatio: "none", role: "img", "aria-label": "Each field read, drawn on the page" });
    const fs = Math.max(10, Math.round(p.width * 0.012));
    const tags = [];
    for (const f of placed) {
      const [pg, x1, y1, x2, y2] = boxes[f.key];
      if (pg !== i) continue;
      const r = svg("rect", { x: x1 * p.width, y: y1 * p.height, width: Math.max(2, (x2 - x1) * p.width), height: Math.max(2, (y2 - y1) * p.height), class: `box ${f.correct ? "ok" : "bad"}`, "data-key": fieldName(f) });
      r.append(svg("title", {}, `${fieldName(f)}: ${f.correct ? "right" : "wrong"}. Read: ${clip(f.read, 80)}. Truth: ${clip(f.truth, 80)}`));
      r.addEventListener("mouseenter", () => highlight(fieldName(f)));
      r.addEventListener("mouseleave", () => highlight(null));
      over.append(r);
      if (labelWrong && !f.correct) tags.push([f, x1 * p.width, y2 * p.height]);
    }
    for (const [f, x0, y] of tags) {
      const label = `read ${clip(f.read, 28)} | truth ${clip(f.truth, 28)}`;
      const w = label.length * fs * 0.56 + fs * 0.6;
      const x = Math.max(0, Math.min(x0, p.width - w));
      const g = svg("g", { class: "tag" });
      g.append(svg("rect", { x, y: y + 1, width: w, height: fs * 1.35, rx: 3 }), svg("text", { x: x + fs * 0.3, y: y + fs * 1.05, "font-size": fs }, label));
      over.append(g);
    }
    sheet.append(img, over);
    if (rec.pages.length > 1) sheet.append(el("div", { class: "pageno", text: `page ${i + 1} of ${rec.pages_total}` }));
    sheets.append(sheet);
  });
  const extra = rec.pages_total > rec.pages.length ? ` The first ${rec.pages.length} of its ${rec.pages_total} pages are shown.` : "";
  const where = { nist: "Field places are the zones learned from the training pages, set on this page by its own OCR; approximate.", cord: "Field places are CORD's own word boxes.", deepform: "Field places are VRDU's entity boxes." };
  document.getElementById("caption").textContent = `${CORPUS[rec.corpus].about} Document ${rec.doc}. ${where[rec.corpus] || ""}${extra}`;
  const summary = document.getElementById("summary");
  if (!read) summary.textContent = `${short(state.arm)} did not read this page at this level.`;
  else summary.textContent = `${short(state.arm)}: ${read.correct} of ${read.scored} fields right${read.unparsed ? " (its answer did not parse, so every field is wrong)" : ""}.`;
  fillList(document.getElementById("field-list"), placed, rec.labels);
  fillList(document.getElementById("unplaced"), unplaced, rec.labels);
  document.getElementById("unplaced-h").hidden = unplaced.length === 0;
  document.getElementById("unplaced-note").hidden = unplaced.length === 0;
  drawViewerArms();
}

function fillList(host, fields, labels) {
  const wrongOnly = document.getElementById("wrong-only").checked;
  host.replaceChildren();
  for (const f of fields) {
    if (wrongOnly && f.correct) continue;
    const li = el("li", { class: f.correct ? "ok" : "bad", "data-key": fieldName(f), tabindex: "0" },
      el("span", { class: "outcome", text: f.correct ? "✓ right" : `✗ ${f.outcome.replaceAll("_", " ")}` }),
      el("span", { class: "name", text: fieldName(f) }),
      labels[f.path] ? el("span", { class: "desc", text: labels[f.path] }) : null,
      el("dl", { class: "vals" },
        el("dt", { text: "Read" }), el("dd", { text: f.read === null ? "(blank)" : f.read }),
        el("dt", { text: "Truth" }), el("dd", { text: f.truth === null ? "(blank on the page)" : f.truth })));
    for (const [ev, key] of [["mouseenter", fieldName(f)], ["focus", fieldName(f)], ["mouseleave", null], ["blur", null]]) li.addEventListener(ev, () => highlight(key));
    host.append(li);
  }
}

function highlight(key) {
  for (const n of document.querySelectorAll(".hot")) n.classList.remove("hot");
  if (key === null) return;
  for (const n of document.querySelectorAll("[data-key]")) if (n.getAttribute("data-key") === key) n.classList.add("hot");
}

function drawViewerArms() {
  const rec = state.record;
  const lv = String(state.level);
  const c = VIEW_CURVE[rec.corpus] ? state.results.curves.find((x) => x.key === VIEW_CURVE[rec.corpus]) : null;
  const t = VIEW_TABLE[rec.corpus] ? table(VIEW_TABLE[rec.corpus]) : null;
  document.getElementById("arms-note").textContent = c ? `${c.title}, at ${state.level === 0 ? "the clean scan" : `level ${state.level}`}.` : t ? `${t.title}, clean scan.` : "";
  const items = state.index.arms.map((a) => {
    let iv = null, text = "not read at this level";
    if (c) {
      const cell = (c.cells[a.label] || {})[lv];
      if (cell && cell.accuracy) { iv = cell.accuracy; text = cell.text; }
    } else if (t) {
      const r = t.rows.find((x) => x.arm === a.label);
      if (r && r.accuracy) { iv = r.accuracy; text = r.accuracy_text; }
    }
    const read = (rec.reads[lv] || {})[a.label];
    return { a, iv, text, page: read ? `${read.correct} of ${read.scored} on this page` : "" };
  }).filter((i) => i.iv);
  const W = 900, labelW = 230, x0 = labelW, x1 = W - 190, rowH = 26, top = 24;
  const H = top + items.length * rowH + 6;
  const x = linScale(0, 1, x0, x1);
  const s = svg("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": "Each reader's accuracy on this set at this level" });
  for (const v of [0, 0.25, 0.5, 0.75, 1]) {
    s.append(svg("line", { x1: x(v), x2: x(v), y1: top - 6, y2: H - 4, class: "gridline" }));
    s.append(svg("text", { x: x(v), y: 14, "text-anchor": "middle", class: "tick" }, `${100 * v}%`));
  }
  items.sort((p, q) => q.iv.point - p.iv.point).forEach((it, i) => {
    const k = kind(it.a.label);
    const mid = top + i * rowH + rowH / 2;
    const g = svg("g", { class: `arm-row${it.a.label === state.arm ? " sel" : ""}`, tabindex: "0", role: "button", "aria-label": `${short(it.a.label)}, ${it.text}. Draw its read.` });
    g.append(svg("rect", { x: 0, y: mid - rowH / 2 + 2, width: W, height: rowH - 4, rx: 4, class: "row-band", opacity: it.a.label === state.arm ? 1 : 0.0001 }));
    g.append(svg("text", { x: 10, y: mid + 4, class: `mark-label${k === "finetuned" ? " strong" : ""}` }, short(it.a.label)));
    g.append(svg("line", { x1: x(it.iv.low), x2: x(it.iv.high), y1: mid, y2: mid, class: `ci-line k-stroke-${k}` }));
    g.append(mark(k, x(it.iv.point), mid, 5));
    g.append(svg("text", { x: x1 + 14, y: mid + 4, class: "value-label" }, `${pct(it.iv.point)}${it.page ? `; ${it.page}` : ""}`));
    const pick = () => { state.arm = it.a.label; document.getElementById("arm").value = it.a.label; drawPage(); };
    g.addEventListener("click", pick);
    g.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); pick(); } });
    s.append(g);
  });
  document.getElementById("arms-chart").replaceChildren(s);
  register("arms", ["Reader", "Fields correct over the set (95% CI)", "This page"], items.map((it) => [short(it.a.label), it.text, it.page]));
}

// --- Wiring -------------------------------------------------------------------------------

async function main() {
  [state.results, state.story, state.index] = await Promise.all([getJson("data/results.json"), getJson("data/story.json"), getJson("data/index.json")]);
  fills();
  drawHeadToHead();
  chips("landscape-corpus", CORPORA.map((c) => [c.key, c.name]), state.landscape, (k) => { state.landscape = k; drawLandscape(); });
  drawLandscape();
  drawCorpusCards();
  drawLift();
  drawRecipes();
  drawMinutes();
  drawAblations();
  chips("serving-corpus", CORPORA.map((c) => [c.key, c.name]), state.serving, (k) => { state.serving = k; drawServing(); });
  drawServing();
  setupCalculator();
  chips("scans-corpus", SCAN_SETS.filter(([k]) => curve(k)), state.scans, (k) => { state.scans = k; drawScans(); });
  drawScans();
  drawCeiling();
  drawGap();
  drawNoise();
  await setupViewer();
}

main().catch((err) => {
  const p = el("p", { class: "warning", text: `The page's data did not load: ${err.message}` });
  document.querySelector("main").prepend(p);
  console.error(err);
});
