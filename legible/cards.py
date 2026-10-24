"""Model cards for the fine-tuned adapters, written from the run records and the graded reads.

One card per seed-0 headline adapter (`legible serve headline`), each a Hugging Face model
card: front matter the Hub reads (base model, library, licence, tags), then what the adapter
reads and writes, how it was trained and on how many pages, what it measured on its own test
set beside the frontier models, its failure modes, and the licence of every corpus it learned
from (PLAN.md section 8). `legible cards` writes them to `docs/cards/`; no number in a card is
typed by hand.

The numbers are the README's: the same reads, the same grader, the same intervals
(`legible.report.row`). What a card adds is the adapter's own share of a table. FARA's
unseen-template table pools three models, one per held-out template, and each card reports its
model on its own template's test set, with the pooled row beside it.

Where the training record (`run.json`, written beside the adapter by `legible train run`) is
not on the machine writing the cards, the card gives what the recipe and the training set fix
(documents, pages, the step count they imply) and says that the measured loss and step count
are in the record that travels with the adapter.
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import yaml

from legible.data.vrdu import FARA_TEMPLATES
from legible.grade import HALLUCINATIONS, DocGrade, Outcome
from legible.report import GateResult, Row, pct, usd
from legible.review import ReviewResult
from legible.schema import CorpusSchema, FieldSpec
from legible.stats import Interval, ratio_ci
from legible.train.dataset import TrainingHeader, TrainingRow
from legible.train.recipe import TrainConfig
from legible.train.vision import RunRecord

#: The token probability docs/review.md and docs/rejected.md count a field as sure at.
SURE = 0.999

#: The serving card and its rate, and the frontier price list: every cost in a card is at these.
SELF_HOSTED_PRICE = "an RTX 3090 at US$0.50 an hour on RunPod (2026-10-18)"
FRONTIER_PRICE = "the gateway ledger's cost at the 2026-10-16 price list, batch rate"


@dataclass(frozen=True)
class CorpusLicence:
    """A corpus's terms, as docs/data.md quotes them."""

    name: str
    source: str
    terms: str
    quote: str
    quoted_from: str
    attribution: str
    #: The corpus's Hugging Face dataset id, where it has one.
    hub_dataset: str | None


_VRDU_QUOTE = (
    '"We are excited to announce the public release of the VRDU dataset and evaluation code '
    'under a Creative Commons license."'
)
_VRDU_FROM = (
    'Google\'s release post, "Advances in document understanding" (2023-08-09), '
    'https://research.google/blog/advances-in-document-understanding/, where "Creative '
    'Commons license" links to https://creativecommons.org/licenses/by/4.0/. That hyperlink '
    "is the only statement of the variant; the repository has no licence file (read "
    "2026-10-16)."
)
_VRDU_ATTRIBUTION = (
    "Google Research's VRDU benchmark (Wang et al., \"VRDU: A Benchmark for Visually-rich "
    'Document Understanding", KDD 2023), annotations used under CC BY 4.0.'
)

LICENCES: Mapping[str, CorpusLicence] = {
    "fara": CorpusLicence(
        name="VRDU Registration Forms (FARA)",
        source="https://github.com/google-research-datasets/vrdu (registration-form)",
        terms=(
            "CC BY 4.0 for the benchmark's annotations; the pages are US public records, "
            "Foreign Agents Registration Act filings published by the Department of Justice"
        ),
        quote=_VRDU_QUOTE,
        quoted_from=_VRDU_FROM,
        attribution=_VRDU_ATTRIBUTION,
        hub_dataset=None,
    ),
    "deepform": CorpusLicence(
        name="VRDU Ad-buy Forms (DeepForm)",
        source="https://github.com/google-research-datasets/vrdu (ad-buy-form)",
        terms=(
            "CC BY 4.0 for the benchmark's annotations; the pages are US public records, "
            "political advertising orders from television stations' FCC public files"
        ),
        quote=_VRDU_QUOTE,
        quoted_from=_VRDU_FROM,
        attribution=_VRDU_ATTRIBUTION,
        hub_dataset=None,
    ),
    "cord": CorpusLicence(
        name="CORD v2 receipts (Clova AI)",
        source=(
            "https://huggingface.co/datasets/naver-clova-ix/cord-v2 at commit "
            "7f0115a4b758a71d6473b8d085751692da2fef98"
        ),
        terms="CC BY 4.0",
        quote=(
            '"This work is licensed under a [Creative Commons Attribution 4.0 International '
            'License][cc-by]."'
        ),
        quoted_from=(
            "https://github.com/clovaai/cord README, linking to "
            "http://creativecommons.org/licenses/by/4.0/; the Hugging Face card has "
            "`license: cc-by-4.0` (read 2026-10-16)."
        ),
        attribution=(
            "Clova AI's CORD (Park et al., \"CORD: A Consolidated Receipt Dataset for "
            'Post-OCR Parsing", 2019), used under CC BY 4.0.'
        ),
        hub_dataset="naver-clova-ix/cord-v2",
    ),
    "nist": CorpusLicence(
        name="NIST Special Database 2 (1988 IRS tax forms, synthesised)",
        source="https://www.nist.gov/srd/nist-special-database-2",
        terms=(
            "Public domain in the United States (title 17 United States Code Section 105), "
            "confirmed by NIST to Peter Parker on 2026-10-17, including that adapters trained "
            "on the pages may be published"
        ),
        quote=(
            '"This data/work was created by employees of the National Institute of Standards '
            "and Technology (NIST), an agency of the Federal Government. Pursuant to title 17 "
            "United States Code Section 105, works of NIST employees are not subject to "
            "copyright protection in the United States. This data/work may be subject to "
            "foreign copyright. The data/work is provided by NIST as a public service and is "
            'expressly provided "AS IS." ..."'
        ),
        quoted_from="https://www.nist.gov/open/license, the regime NIST confirmed applies to SD2.",
        attribution="NIST Special Database 2, DOI 10.18434/M3J08M.",
        hub_dataset=None,
    ),
}

#: Gemma 4's terms, as docs/models.md and PLAN.md section 2.3 record them.
BASE_LICENCE = "apache-2.0"


@dataclass(frozen=True)
class Publication:
    publishable: bool
    why: str


#: The plan's rule (PLAN.md, risks): a corpus whose terms forbid redistributing derived models
#: drops its adapter from publication and keeps its numbers. None of the four does.
PUBLICATION: Mapping[str, Publication] = {
    "fara": Publication(
        True,
        "VRDU's annotations are CC BY 4.0 and the pages are public records the Department of "
        "Justice publishes for inspection; neither forbids a derived model. The forms name "
        "individuals, and an adapter trained on them can write a name it saw in "
        "training: it is uploaded private, and making it public is a decision recorded in "
        "docs/models.md, not a default.",
    ),
    "deepform": Publication(
        True,
        "VRDU's annotations are CC BY 4.0 and the pages are public records from the FCC's "
        "public files; neither forbids a derived model.",
    ),
    "cord": Publication(True, "CORD is CC BY 4.0, which permits a derived model with attribution."),
    "nist": Publication(
        True,
        "NIST SD2 is public domain in the United States; NIST confirmed on 2026-10-17 that "
        "adapters trained on it may be published.",
    ),
}

CORPUS_LABEL: Mapping[str, str] = {
    "fara": "FARA registration forms",
    "deepform": "DeepForm ad-buy forms",
    "cord": "CORD receipts",
    "nist": "NIST tax forms",
}


def family(dataset: str) -> str:
    """The corpus a training set is drawn from: `fara-unseen-amendment-s0` is FARA's."""
    return "nist" if dataset.startswith("nist") else dataset.split("-")[0]


# --- Training counts ------------------------------------------------------------------------


@dataclass(frozen=True)
class TrainingCounts:
    """What the recipe took from its training set(s): documents and their pages."""

    #: Documents in the training set(s) as written.
    available: int
    #: Documents the recipe takes (the first `volume`, or all).
    documents: int
    pages: int
    #: Documents by FARA template or NIST face, among those taken; empty otherwise.
    by_group: Mapping[str, int]
    #: Documents known before the run to exceed the sequence limit (NIST's Schedule D page 1).
    over_limit: int


def _template(doc_id: str) -> str | None:
    """A FARA file's template, from the end of its name (`..._Dissemination Report.pdf`)."""
    stem = doc_id.removesuffix(".pdf").replace(" ", "_")
    return next((t for t in FARA_TEMPLATES if stem.endswith(f"_{t}")), None)


def training_counts(
    config: TrainConfig, sets: Sequence[tuple[TrainingHeader, Sequence[TrainingRow]]]
) -> TrainingCounts:
    """The documents and pages a run took, in the order `legible train run` puts them: NIST's
    faces interleaved by the hash of their id, then the volume cut."""
    rows = [(h.corpus, r) for h, rs in sets for r in rs]
    if family(config.dataset) == "nist":
        rows.sort(key=lambda e: hashlib.sha256(e[1].doc_id.encode()).hexdigest())
    taken = rows if config.volume is None else rows[: config.volume]
    groups: dict[str, int] = {}
    for corpus, r in taken:
        g = corpus if corpus.startswith("nist") else _template(r.doc_id)
        if g is not None:
            groups[g] = groups.get(g, 0) + 1
    return TrainingCounts(
        available=len(rows),
        documents=len(taken),
        pages=sum(len(r.pages) for _, r in taken),
        by_group=dict(sorted(groups.items())),
        over_limit=groups.get("nist_sch_d_1", 0),
    )


# --- What a card says ----------------------------------------------------------------------


@dataclass(frozen=True)
class Measured:
    """One reader on a card's documents: the README's row and the unparsed share."""

    row: Row
    unparsed: Interval | None = None


@dataclass(frozen=True)
class Confidence:
    """The adapter's token probability on its own dev and test reads (docs/review.md)."""

    sure_fields: int
    #: The share right among dev fields written at SURE or more, by document resampling.
    sure_right: Interval | None
    #: The commonest miss among those, and how often.
    sure_miss: tuple[str, int] | None
    review: ReviewResult | None


@dataclass(frozen=True)
class CardFacts:
    run_id: str
    config: TrainConfig
    #: The README table this adapter's reads belong to: fara-unseen, deepform-unseen, cord, nist.
    table: str
    schemas: Sequence[CorpusSchema]
    prompt_version: int
    counts: TrainingCounts
    record: RunRecord | None
    #: What the adapter's test documents are, in words.
    test_name: str
    #: The adapter first, then its untuned base, then the frontier models, on its test set.
    own: Sequence[Measured]
    #: FARA only: the README's pooled unseen-template rows for this size and the best frontier.
    pooled: Sequence[Measured] = ()
    #: VRDU only: (label, mixed-template row, unseen-template row) for this size and the best
    #: frontier model, as the README's two tables give them.
    gap: Sequence[tuple[str, Row, Row]] = ()
    #: Degradation: the levels, a description of the pages, and rows by label and level.
    curve_levels: Sequence[int] = ()
    curve_pages: str = ""
    curve: Mapping[str, Mapping[int, Row]] = field(default_factory=dict)
    #: Seeds 1 and 2: (seed, row on that seed's own test set).
    seeds: Sequence[tuple[int, Row]] = ()
    #: The gate's decisions on this corpus, and the size the gate compared.
    gate: Sequence[GateResult] = ()
    gated_size: str | None = None
    confidence: Confidence | None = None

    @property
    def corpus(self) -> str:
        return family(self.config.dataset)

    @property
    def size_name(self) -> str:
        return "E2B" if self.config.size == "2b" else "E4B"


def confidence(dev: Sequence[DocGrade], review: ReviewResult | None) -> Confidence:
    """How right the adapter is where its token probability is SURE or more, on dev."""
    sure: list[float] = []
    right: list[float] = []
    misses: dict[str, int] = {}
    for g in dev:
        hits = [o for o in g.outcomes if o.confidence is not None and o.confidence >= SURE]
        sure.append(float(len(hits)))
        right.append(float(sum(o.correct for o in hits)))
        for o in hits:
            if not o.correct:
                misses[o.outcome.value] = misses.get(o.outcome.value, 0) + 1
    n = int(sum(sure))
    commonest = max(misses.items(), key=lambda kv: kv[1]) if misses else None
    return Confidence(
        sure_fields=n,
        sure_right=ratio_ci(right, sure) if n else None,
        sure_miss=commonest,
        review=review,
    )


_MISS_WORDS: Mapping[str, str] = {
    Outcome.MISSING.value: "a null where the form carries a value",
    Outcome.WRONG_FIELD.value: "the value of another field on the page",
    Outcome.WRONG_VALUE.value: "a wrong value",
    Outcome.MALFORMED.value: "a value not of the field's type",
    Outcome.INVENTED.value: "a value on no part of the page",
    Outcome.BLANK_FILLED.value: "a blank box filled from elsewhere on the page",
}
assert set(_MISS_WORDS) == {o.value for o in Outcome if o is not Outcome.CORRECT}
assert {o.value for o in HALLUCINATIONS} <= set(_MISS_WORDS)


# --- Rendering ------------------------------------------------------------------------------


def _points(a: Interval | None, b: Interval | None) -> str:
    """b minus a in points, signed."""
    if a is None or b is None:
        return "not measured"
    return f"{100 * (b.point - a.point):+.1f} points"


def _ok(i: Interval | None) -> bool:
    return i is not None and not math.isnan(i.point)


def best_frontier(facts: CardFacts) -> Measured | None:
    frontier = [m for m in facts.own if m.row.label.startswith("A,") and _ok(m.row.accuracy)]
    return max(
        frontier, key=lambda m: m.row.accuracy.point if m.row.accuracy else 0.0, default=None
    )


def _model_name(label: str) -> str:
    """`A, Gemini 3.8 Flash on the image` -> `Gemini 3.8 Flash`."""
    return label.split(", ", 1)[-1].removesuffix(" on the image").removesuffix(" fine-tuned")


def front_matter(facts: CardFacts) -> dict[str, Any]:
    base = facts.config.base
    lic = LICENCES[facts.corpus]
    pub = PUBLICATION[facts.corpus]
    meta: dict[str, Any] = {
        "base_model": base.repo,
        "base_model_revision": base.revision,
        "library_name": "peft",
        "pipeline_tag": "image-text-to-text",
        "license": BASE_LICENCE,
        "language": ["en"],
        "tags": [
            "document-understanding",
            "form-extraction",
            "vision-language-model",
            "qlora",
            "lora",
            "gemma4",
            "legible",
            facts.corpus,
        ],
    }
    if lic.hub_dataset:
        meta["datasets"] = [lic.hub_dataset]
    meta["legible_run_id"] = facts.run_id
    meta["legible_publishable"] = pub.publishable
    return meta


def _pct(i: Interval | None) -> str:
    return pct(i) if _ok(i) else "none"


def _partial(r: Row) -> str:
    """How much of a row's documents were read, when not all of them were."""
    return f", {r.documents - r.missing:,} of {r.documents:,} read so far" if r.missing else ""


def _training_table(facts: CardFacts) -> list[str]:
    c, r, n = facts.config, facts.record, facts.counts
    fit = n.documents - (r.left_out if r is not None else n.over_limit)
    steps = math.ceil(fit / (c.batch_size * c.grad_accum)) * c.epochs
    lines = [
        "| Setting | Value |",
        "|---|---|",
        f"| Base | `{c.base.repo}` at revision `{c.base.revision}` |",
        f"| Chat template | `{c.base.instruct_repo}` at revision `{c.base.instruct_revision}` |",
        "| Quantisation | NF4 4-bit with double quantisation, bf16 compute; the vision and audio "
        "towers, the vision projector and the output layer kept at full precision |",
        f"| LoRA | rank {c.rank}, alpha {c.alpha}, dropout {c.dropout}, on the language model's "
        "attention and MLP projections and the vision projector, never the towers |",
        f"| Optimisation | learning rate {c.learning_rate:g}, cosine schedule, warmup "
        f"{c.warmup_ratio:g}, {c.epochs} epoch, {c.batch_size} document a step, "
        f"{c.grad_accum} steps accumulated |",
        f"| Visual tokens a page | {c.visual_tokens:,} |",
        f"| Sequence limit | {c.max_seq_len:,} tokens |",
        f"| Seed | {c.seed} |",
        f"| Training set | `{c.dataset}` ({n.available:,} documents"
        + (f"; the first {c.volume:,} taken" if c.volume is not None else "")
        + ") |",
        f"| Training documents and pages | {n.documents:,} documents, {n.pages:,} pages |",
    ]
    if r is not None:
        lines += [
            f"| Left out for length | {r.left_out:,} |",
            f"| Optimiser steps | {r.steps:,} |",
            f"| Final train loss | {r.train_loss:.3f} |" if r.train_loss is not None else "",
            f"| Finished | {r.finished_at:%Y-%m-%d} |" if r.finished_at else "",
            "| Stack | " + ", ".join(f"{k} {v}" for k, v in sorted(r.versions.items())) + " |",
        ]
        lines = [x for x in lines if x]
    else:
        over = (
            f"; {n.over_limit:,} of them Schedule D page 1, over the sequence limit and left "
            "out by the run (legible/train/recipe.py)"
            if n.over_limit
            else ""
        )
        lines += [
            f"| Optimiser steps | {steps:,}, from {fit:,} documents at "
            f"{c.batch_size * c.grad_accum} a step{over} |",
            "| Loss and timing | in `run.json`, the training record uploaded with the adapter; it "
            "was not on the machine that wrote this card |",
        ]
    if n.by_group:
        what = "Faces" if facts.corpus == "nist" else "Templates"
        lines.append(
            f"| {what} trained on | "
            + ", ".join(f"{g.removeprefix('nist_')} {k:,}" for g, k in n.by_group.items())
            + " |"
        )
    return lines


def _schema_lines(facts: CardFacts) -> list[str]:
    if facts.corpus == "nist":
        total = sum(len(s.scalars) for s in facts.schemas)
        lines = [
            f"One JSON object a page, for whichever of the twenty 1988 form faces it is: "
            f"{len(facts.schemas)} schemas, {total:,} text fields in all, every value a string "
            "or null. The face's own prompt names it and lists its fields; the fields are "
            "the NIST tables' (`legible/schema/nist_fields.json`), check marks and signatures "
            "left out.",
            "",
            "| Face | Fields |",
            "|---|---:|",
        ]
        lines += [
            f"| {s.corpus.removeprefix('nist_')} | {len(s.scalars):,} |" for s in facts.schemas
        ]
        return lines
    schema = facts.schemas[0]
    lines = [
        "One JSON object a document, every value a string or null, in the compact form it was "
        'trained on (`{"advertiser":null}`, no spaces). '
        f"{schema.description}",
        "",
        "| Field | Kind | What it is |",
        "|---|---|---|",
    ]
    for f in schema.fields:
        if isinstance(f, FieldSpec):
            lines.append(f"| `{f.name}` | {f.kind.value} | {f.description} |")
        else:
            lines.append(f"| `{f.name}` | list | {f.description} Each entry has: |")
            lines += [
                f"| `{f.name}[].{g.name}` | {g.kind.value} | {g.description} |" for g in f.fields
            ]
    return lines


def _results_table(rows: Sequence[Measured]) -> list[str]:
    out = [
        "| Reader | Fields correct (95% CI) | Every field right | Invented fields "
        "| Answers that did not parse | Cost per 1,000 pages | Documents |",
        "|---|---|---|---|---|---|---:|",
    ]
    for m in rows:
        r = m.row
        n = f"{r.documents - r.missing}" + (f" of {r.documents}" if r.missing else "")
        out.append(
            f"| {r.label} | {_pct(r.accuracy)} | {_pct(r.all_right)} | {_pct(r.invented)} "
            f"| {_pct(m.unparsed) if m.unparsed is not None else ''} | {usd(r.per_thousand)} "
            f"| {n} |"
        )
    return out


def _gate_lines(facts: CardFacts) -> list[str]:
    if facts.gated_size != facts.config.size:
        other = "E2B" if facts.gated_size == "2b" else "E4B"
        return [
            f"Not gated. Project 03's gate compared the {other}, the better of the two sizes "
            "on dev, for this corpus (docs/gate.md); its decision is on that card."
        ]
    out = []
    for g in facts.gate:
        decided = g.counts.get("pass", 0) + g.counts.get("block", 0)
        if g.verdict == "PASS" and decided == 0:
            verdict = "no decision: every field under-powered at 3 points"
        else:
            verdict = g.verdict.lower()
        worst = "; ".join(f"`{s}` {d}" for s, d in g.blocks[:2])
        out.append(
            f"- Against {_model_name(g.baseline)}: **{verdict}** (fields pass, block, "
            f"under-powered: {g.counts.get('pass', 0)}, {g.counts.get('block', 0)}, "
            f"{g.counts.get('warn', 0)})" + (f"; worst: {worst}" if worst else "") + "."
        )
    if facts.corpus == "fara":
        out.append(
            "- The FARA decisions pool the three held-out-template E2B models, this one among "
            "them, over FARA's unseen-template test documents."
        )
    return out or ["The gate has not been run for this corpus."]


def render(facts: CardFacts) -> str:
    """The card, as Markdown with Hugging Face front matter. Plain ASCII throughout."""
    c, corpus = facts.config, facts.corpus
    lic, pub = LICENCES[corpus], PUBLICATION[corpus]
    me = facts.own[0]
    best = best_frontier(facts)
    held = ""
    if corpus == "fara":
        held = c.dataset.removeprefix("fara-unseen-").rsplit("-s", 1)[0]
        held = next((t for t in FARA_TEMPLATES if t.lower() == held), held)
    title = f"Gemma 4 {facts.size_name} fine-tuned to read {CORPUS_LABEL[corpus]}" + (
        f", {held.replace('_', ' ')} template held out" if held else ""
    )
    meta = yaml.safe_dump(front_matter(facts), sort_keys=False, width=1000)
    out: list[str] = ["---", meta.rstrip()]
    if not lic.hub_dataset:
        out.append(
            f"# {lic.name} is not on the Hugging Face Hub; its source is under Training data."
        )
    out += [
        "---",
        "",
        f"# {title}",
        "",
        f"A QLoRA adapter on `{c.base.repo}` that reads the page images of one "
        f"{'page' if corpus in {'cord', 'nist'} else 'document'} and writes its fields as "
        "JSON. Trained and measured in Forms That Read Themselves (package `legible`), which "
        "compares frontier vision models, fine-tuned small vision models and OCR pipelines on "
        "scanned forms with known answers. "
        f"Run `{facts.run_id}`. This card is written by `legible cards` from the run's "
        "records and graded reads; no number in it is typed by hand.",
        "",
    ]
    if not pub.publishable:
        out += [f"**Not for upload.** {pub.why}", ""]
    out += [
        "## What it reads and what it writes",
        "",
        "Input: the document's pages as images, in page order, then the instruction every "
        f"reader in the project is sent (`legible.prompt`, version {facts.prompt_version}), "
        "which describes each field and gives the JSON Schema. The adapter was trained on "
        "that instruction and nothing else.",
        "",
        *_schema_lines(facts),
        "",
        "## How it was trained",
        "",
        "Project 06's QLoRA recipe with a vision encoder (`legible/train/vision.py`): one user "
        "turn of page images then the instruction, one assistant turn of the truth's JSON, the "
        "loss on the answer's tokens only. Every training document is from the split's train "
        "part; a held-out document refuses the set (`legible/train/dataset.py`).",
        "",
        *_training_table(facts),
        "",
        "## Training data and its licences",
        "",
        f"**{lic.name}**, {lic.source}. Terms: {lic.terms}.",
        "",
        f"> {lic.quote}",
        "",
        f"Quoted from {lic.quoted_from} Attribution: {lic.attribution}",
        "",
        f"The adapter is released under {BASE_LICENCE}, the base model's licence. "
        f"Publication: {pub.why}",
        "",
        "## Results",
        "",
        f"On {facts.test_name}, read once, level 0, temperature 0, unconstrained. Field "
        "accuracy is VRDU's matchers, one grader for every reader; intervals are 95% bootstrap "
        f"over documents. The adapter is costed at {SELF_HOSTED_PRICE} over the measured wall "
        f"time of its read; the frontier models at {FRONTIER_PRICE}.",
        "",
        *_results_table(facts.own),
        "",
    ]
    if best is not None:
        mc = me.row.per_thousand
        bc = best.row.per_thousand
        ratio = (
            f", about 1/{bc.point / mc.point:.0f} of the cost"
            if mc is not None and bc is not None and mc.point > 0
            else ""
        )
        base = facts.own[1].row if len(facts.own) > 1 else None
        against_base = (
            f" Against its untuned base it reads {_points(base.accuracy, me.row.accuracy)}."
            if base is not None and _ok(base.accuracy) and _ok(me.row.accuracy)
            else ""
        )
        out += [
            f"The best frontier model on these documents is {_model_name(best.row.label)}, at "
            f"{_pct(best.row.accuracy)} of fields for {usd(bc)} a thousand pages. This adapter's "
            f"field accuracy differs from it by {_points(best.row.accuracy, me.row.accuracy)}, "
            f"at {usd(mc)} a thousand pages{ratio}.{against_base}",
            "",
        ]
    if facts.pooled:
        out += [
            "In the README's FARA table the three held-out-template models of this size are "
            f"pooled over the {facts.pooled[0].row.documents:,} unseen-template test documents:",
            "",
            *_results_table(facts.pooled),
            "",
        ]
    have = {s for s, _ in facts.seeds}
    seed_cells = [f"seed {s}, {_pct(r.accuracy)}{_partial(r)}" for s, r in facts.seeds]
    seed_cells += [f"seed {s} not yet read" for s in (1, 2) if s not in have]
    points = [r.accuracy.point for _, r in facts.seeds if r.accuracy is not None]
    spread = ""
    if len(points) == 2 and me.row.accuracy is not None:
        points.append(me.row.accuracy.point)
        spread = (
            f" The three seeds' point estimates span {100 * (max(points) - min(points)):.1f} "
            "points (their test sets differ where the split files do)."
        )
    out += [
        "Training variance: the same recipe at seeds 1 and 2, each on its own split's test "
        "set: " + "; ".join(seed_cells) + "." + spread,
        "",
    ]
    out += ["### The 03 release gate", "", *_gate_lines(facts), ""]

    # Failure modes.
    out += ["## Failure modes", ""]
    if facts.gap:
        lines = []
        for label, mixed, unseen in facts.gap:
            lines.append(
                f"{_model_name(label)} {_pct(mixed.accuracy)} on templates seen in training "
                f"and {_pct(unseen.accuracy)} on templates not seen "
                f"({_points(mixed.accuracy, unseen.accuracy)})"
            )
        _, mine_mixed, mine_unseen = facts.gap[0]
        hurt = (
            mine_mixed.accuracy is not None
            and mine_unseen.accuracy is not None
            and mine_unseen.accuracy.point < mine_mixed.accuracy.point
        )
        out += [
            "- **A form design it has not seen.** The README's two tables, templates seen in "
            "training and not, for this size and the best frontier model: "
            + "; ".join(lines)
            + "."
            + (
                " A fine-tune learns which box a value sits in on the templates it saw, and on "
                "a new one puts values in the wrong field or leaves them out."
                if hurt
                else ""
            ),
        ]
    else:
        out += [
            "- **A form design it has not seen.** Not measured on this corpus: "
            + (
                "NIST's twenty faces are fixed, and every face it reads it saw in training."
                if corpus == "nist"
                else "CORD's receipts have no template labels."
            )
            + " On FARA and DeepForm, where it was measured, the fine-tunes read worse on "
            "templates they did not see and the frontier models do not (the README's template "
            "gap tables); expect worse on a form unlike its training set.",
        ]
    if facts.curve_levels:
        me_curve = facts.curve.get(me.row.label, {})
        steps = ", ".join(
            f"level {lv} {_pct(me_curve[lv].accuracy)}{_partial(me_curve[lv])}"
            for lv in facts.curve_levels
            if lv in me_curve
        )
        others = [
            f"{_model_name(label)} "
            + ", ".join(
                f"level {lv} {_pct(r.accuracy)}{_partial(r)}" for lv, r in sorted(rows.items())
            )
            for label, rows in facts.curve.items()
            if label != me.row.label and rows
        ]
        out += [
            f"- **A bad scan.** On {facts.curve_pages}, degraded in the project's five "
            f"reproducible steps (docs/degradation.md): {steps}."
            + (" Beside it: " + "; ".join(others) + "." if others else ""),
        ]
    else:
        out += [
            "- **A bad scan.** Not measured on receipts, which are photographs rather than "
            "scans; how it fails under blur or glare is unknown. The README's NIST and VRDU "
            "curves show what the degradation steps do to the other fine-tunes.",
        ]
    conf = facts.confidence
    if conf is not None:
        if conf.sure_fields:
            miss = (
                f"; the commonest error there is {_MISS_WORDS[conf.sure_miss[0]]} "
                f"({conf.sure_miss[1]:,})"
                if conf.sure_miss
                else ""
            )
            sure = (
                f"Of its dev fields written at a token probability of {SURE} or more "
                f"({conf.sure_fields:,}), {_pct(conf.sure_right)} are right{miss}."
            )
        else:
            sure = f"None of its dev fields is written at a token probability of {SURE} or more."
        rev = ""
        if conf.review is not None:
            reached = math.isfinite(conf.review.threshold.value)
            rev = (
                f" At 99% accuracy it sends {_pct(conf.review.review_rate)} of its test fields "
                "to a person" + ("" if reached else ", since no threshold reached 99% on dev") + "."
            )
        out += [
            "- **Confidently wrong.** Its own token probability is not a reason to skip "
            f"review. {sure}{rev} "
            + (
                "docs/rejected.md reports this family's case: pooled over the three held-out "
                "templates, the E2B's surest FARA dev fields are nulls where the form carries a "
                "value. "
                if corpus == "fara" and c.size == "2b"
                else ""
            )
            + "The probability measures how sure the model is of its habit, not whether the "
            "page agrees (docs/review.md).",
        ]
    if len(points) == 3:
        out += [
            f"- **Training variance.** The same recipe at three seeds reads from "
            f"{100 * min(points):.1f}% to {100 * max(points):.1f}% of fields on test (above); "
            "a retrained copy is not guaranteed to read like this one.",
        ]
    gate_word = (
        "blocks"
        if any(g.verdict == "BLOCK" for g in facts.gate)
        else "cannot decide"
        if facts.gate
        else "has not decided"
    )
    gated = facts.gated_size == c.size
    other = "E2B" if facts.gated_size == "2b" else "E4B"
    subject = "" if gated or not facts.gate else f" for the {other}, the size it compared,"
    out += [
        f"- **Not non-inferior to the frontier.** Project 03's gate {gate_word}{subject} on "
        "this corpus at a 3-point margin per field (above). Do not take it as a drop-in for a "
        "frontier model's read.",
        f"- **Malformed answers.** {_pct(me.unparsed)} of its test answers did not parse as "
        "JSON. It is read freely: holding the fine-tunes to the schema's grammar was tried on "
        "dev and rejected, because it pushed them off their trained spacing and the DeepForm "
        "E2B then answered null for every field (docs/rejected.md). A caller must count a "
        "parse failure as a document to type by hand.",
        f"- **Invented fields.** {_pct(me.row.invented)} of scored fields carry a value where "
        "the form's box is blank.",
        "- **One instruction.** Trained on one prompt and one schema; another wording, another "
        "field list or another language is untested.",
    ]
    if corpus == "fara":
        out += [
            "- **Personal data.** The registration forms name individuals (registrants, signers, "
            "foreign principals). They are public records, but a model trained on "
            f"{facts.counts.documents:,} of them can write a name from its training forms onto "
            "a page that does not carry it.",
        ]
    out += [
        "",
        "## Intended use",
        "",
        f"Reading {CORPUS_LABEL[corpus]} of the kind it was trained on into JSON for a person "
        "to check, at a fraction of a frontier model's cost per page; and reproducing the "
        "measurements in this card. Plan on a person checking every field: no confidence "
        "measured in the project separates right fields from wrong ones well enough to skip "
        "review at 99% (the README's honest limitation).",
        "",
        "## Out of scope",
        "",
        "- Any decision about a person made on its output without a person checking it.",
        "- Handwriting, other form families, long multi-page documents, or a form whose type "
        "is unknown.",
        "- Unattended use on form designs it was not trained on, where it is worst.",
        "- Pages that are not public: it was measured on public records and datasets only.",
        "",
        "## Loading it",
        "",
        "```python",
        "from peft import PeftModel",
        "from transformers import AutoModelForImageTextToText, AutoProcessor",
        "",
        f'base = AutoModelForImageTextToText.from_pretrained("{c.base.repo}", '
        f'revision="{c.base.revision}")',
        'model = PeftModel.from_pretrained(base, "<this repository>")',
        'processor = AutoProcessor.from_pretrained("<this repository>")',
        f"processor.image_processor.max_soft_tokens = {c.visual_tokens}",
        "```",
        "",
        "Read it at temperature 0, with the prompt `legible.prompt.build_prompt` writes for "
        "its schema; the project served it merged into the bf16 base under vLLM "
        "(`legible serve merge`).",
        "",
    ]
    text = "\n".join(out)
    if not text.isascii():
        bad = sorted({ch for ch in text if not ch.isascii()})
        raise ValueError(f"the card for {facts.run_id} has non-ASCII characters: {bad}")
    return text


def read_front_matter(card: str) -> dict[str, Any]:
    """The YAML between a card's opening `---` lines."""
    if not card.startswith("---\n"):
        raise ValueError("the card has no front matter")
    head, sep, _ = card[4:].partition("\n---\n")
    if not sep:
        raise ValueError("the card's front matter is not closed")
    meta = yaml.safe_load(head)
    if not isinstance(meta, dict):
        raise ValueError("the card's front matter is not a mapping")
    return meta
