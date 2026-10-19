"""The README's result tables, computed from the stored runs; never typed in.

`legible report` grades every arm's test reads against the corpus truth, with the one grader,
and writes the tables between the README's result markers. Each number carries its 95%
bootstrap interval over documents; each cost carries the date of the price it was computed at.
An arm with no finished test run on a table's documents is printed as not yet measured, never
as a guess, and a run that read only some of a table's documents is reported on those and says
how many it lacks.

The tables:

- **Headline.** Per corpus, the split the plan reports on: FARA and DeepForm on VRDU's
  unseen-template split (seed 0; FARA's three held-out templates pooled), CORD on its test set,
  NIST on the 500 test faces every arm reads.
- **The template gap.** FARA and DeepForm on the unseen-template split beside the
  mixed-template split.
- **The degradation curve.** The 300 NIST curve pages at levels 0 to 4.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from legible.arms.frontier import Read, RunDir
from legible.arms.read_run import outputs
from legible.arms.rules_run import answer, read_run
from legible.bench.cost import Costed, GpuPrice, PriceKind, ledger_cost, ocr_usd_per_page
from legible.grade import DocGrade, grade_document, summarise
from legible.schema import CorpusSchema, Record
from legible.stats import Interval

START, END = "<!-- results:start -->", "<!-- results:end -->"

#: The CPU machine OCR is costed at: a RunPod cpu3c pod, US$0.48 an hour for 16 vCPU
#: (docs/ocr.md), so US$0.03 an hour for the one vCPU a page's Tesseract process uses.
OCR_PRICE = GpuPrice(
    gpu="RunPod cpu3c, one of 16 vCPU",
    provider="RunPod",
    kind=PriceKind.ON_DEMAND,
    usd_per_hour=0.48 / 16,
    checked=dt.date(2026, 10, 17),
    source="RunPod's create-pod response, costPerHr 0.48 for 16 vCPU",
)
PRICE_LIST_DATE = "2026-10-16"


@dataclass(frozen=True)
class Truth:
    schema: CorpusSchema
    record: Record
    alternatives: Mapping[str, Sequence[str]]
    text: str | None
    pages: int


@dataclass(frozen=True)
class Arm:
    """One reader as the tables name it. A fine-tune (arm B) has a model per training set,
    so its route depends on the table: `size` names which of the two it is."""

    label: str
    arm: str
    route: str | None
    size: str | None = None


ARMS: tuple[Arm, ...] = (
    Arm("A, Claude Sonnet 5.5 on the image", "a", "quality"),
    Arm("A, Claude Haiku 5.5 on the image", "a", "anchor"),
    Arm("A, GPT-6.1 Sol on the image", "a", "openai"),
    Arm("A, Gemini 3.8 Flash on the image", "a", "google"),
    Arm("D, Claude Sonnet 5.5 on the OCR text", "d", "quality"),
    Arm("E, OCR plus rules", "e", None),
    Arm("B, Gemma 4 E2B fine-tuned on the image", "b", None, size="2b"),
    Arm("B, Gemma 4 E4B fine-tuned on the image", "b", None, size="4b"),
    Arm("C, Gemma 4 E2B untuned on the image", "c", "2b-it"),
    Arm("C, Gemma 4 E4B untuned on the image", "c", "4b-it"),
)

#: The training sets whose fine-tunes read each table's documents, at seed 0 (the gate's).
TABLE_SETS: Mapping[str, tuple[str, ...]] = {
    "fara-unseen": (
        "fara-unseen-amendment-s0",
        "fara-unseen-dissemination_report-s0",
        "fara-unseen-short-form-s0",
    ),
    "deepform-unseen": ("deepform-unseen-s0",),
    "cord": ("cord",),
    "nist": ("nist",),
    "fara-mixed": ("fara-mixed-s0",),
    "deepform-mixed": ("deepform-mixed-s0",),
}

#: The serving pod's rate (docs/gpu-prices.md): a self-hosted page costs the GPU time it took,
#: from the wall time of each read pass at its concurrency.
SERVE_PRICE = GpuPrice(
    gpu="RTX 3090 24 GB",
    provider="RunPod",
    kind=PriceKind.ON_DEMAND,
    usd_per_hour=0.50,
    checked=dt.date(2026, 10, 18),
    source="RunPod's create-pod response, costPerHr 0.50",
)


@dataclass(frozen=True)
class Answers:
    """What one arm said about some documents, and what it cost."""

    outputs: Mapping[str, Any]
    usd: Mapping[str, float]
    ocr_seconds: Mapping[str, float]


def frontier_answers(dirs: Sequence[Path]) -> Answers:
    out: dict[str, Any] = {}
    usd: dict[str, float] = {}
    for d in dirs:
        if not (d / "run.json").exists():
            continue
        reads: dict[str, Read] = RunDir(d).reads()
        parsed = outputs(d)
        for doc, r in reads.items():
            out[doc] = parsed[doc]
            # A request the vendor never returned (status "missing") was never billed.
            usd[doc] = 0.0 if r.status == "missing" else float(r.cost_usd or 0.0)
            if r.cost_usd is None and r.status != "missing":
                raise ValueError(f"{d}: {doc} has no cost in the ledger")
    return Answers(outputs=out, usd=usd, ocr_seconds={})


def selfhosted_answers(dirs: Sequence[Path]) -> Answers:
    """A served model's reads, each costed at its pass's GPU seconds a document."""
    import json

    out: dict[str, Any] = {}
    usd: dict[str, float] = {}
    for d in dirs:
        if not (d / "run.json").exists():
            continue
        passes = (
            [
                json.loads(line)
                for line in (d / "throughput.jsonl").read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            if (d / "throughput.jsonl").exists()
            else []
        )
        reads = sum(p["reads"] for p in passes)
        per_doc = (
            sum(p["seconds"] for p in passes) / reads * SERVE_PRICE.usd_per_hour / 3600
            if reads
            else 0.0
        )
        parsed = outputs(d)
        for doc in RunDir(d).reads():
            out[doc] = parsed[doc]
            usd[doc] = per_doc
    return Answers(outputs=out, usd=usd, ocr_seconds={})


def rules_answers(files: Sequence[Path]) -> Answers:
    out: dict[str, Any] = {}
    secs: dict[str, float] = {}
    for f in files:
        if not f.exists():
            continue
        for r in read_run(f):
            out[r.doc_id] = answer(r)
            secs[r.doc_id] = r.ocr_seconds
    return Answers(outputs=out, usd={}, ocr_seconds=secs)


def with_ocr_cost(answers: Answers, ocr: Mapping[str, float]) -> Answers:
    """Arm D pays for the OCR it reads as well as the model call."""
    usd = {
        d: v + ocr_usd_per_page(OCR_PRICE, ocr[d]) if ocr.get(d) else v
        for d, v in answers.usd.items()
    }
    return Answers(outputs=answers.outputs, usd=usd, ocr_seconds=answers.ocr_seconds)


@dataclass(frozen=True)
class Row:
    label: str
    documents: int
    missing: int
    accuracy: Interval | None
    all_right: Interval | None
    invented: Interval | None
    per_thousand: Interval | None


def row(
    label: str, doc_ids: Sequence[str], truth: Mapping[str, Truth], answers: Answers | None
) -> Row:
    if answers is None or not any(d in answers.outputs for d in doc_ids):
        return Row(label, len(doc_ids), len(doc_ids), None, None, None, None)
    have = [d for d in doc_ids if d in answers.outputs]
    grades: list[DocGrade] = [
        grade_document(
            truth[d].schema,
            d,
            truth[d].record,
            answers.outputs[d],
            page_text=truth[d].text,
            alternatives=truth[d].alternatives,
        )
        for d in have
    ]
    s = summarise(grades)
    pages = {d: truth[d].pages for d in have}
    cost: Interval | None
    if answers.usd:
        reads = [Costed(doc_id=d, cost_usd=answers.usd[d]) for d in have]
        cost = ledger_cost(reads, pages).per_thousand_pages
    else:
        secs = [
            Costed(doc_id=d, cost_usd=ocr_usd_per_page(OCR_PRICE, answers.ocr_seconds[d]))
            for d in have
            if answers.ocr_seconds.get(d)
        ]
        cost = ledger_cost(secs, pages).per_thousand_pages if secs else None
    return Row(
        label,
        len(doc_ids),
        len(doc_ids) - len(have),
        s.accuracy,
        s.all_right,
        s.hallucination,
        cost,
    )


def pct(i: Interval | None) -> str:
    if i is None:
        return "not yet measured"
    return f"{100 * i.point:.1f}% ({100 * i.low:.1f} to {100 * i.high:.1f})"


def usd(i: Interval | None) -> str:
    if i is None:
        return ""
    return f"US${i.point:.2f} ({i.low:.2f} to {i.high:.2f})"


def table(title: str, rows: Sequence[Row]) -> list[str]:
    out = [
        f"**{title}**",
        "",
        "| Arm | Fields correct (95% CI) | Every field right | Invented fields "
        "| Cost per 1,000 pages | Documents |",
        "|---|---|---|---|---|---:|",
    ]
    for r in rows:
        n = f"{r.documents - r.missing}" + (f" of {r.documents}" if r.missing else "")
        if r.accuracy is None:
            n = "0"
        out.append(
            f"| {r.label} | {pct(r.accuracy)} | {pct(r.all_right) if r.all_right else ''} "
            f"| {pct(r.invented) if r.invented else ''} | {usd(r.per_thousand)} | {n} |"
        )
    return [*out, ""]


def curve(levels: Sequence[int], cells: Mapping[str, Mapping[int, Row]]) -> list[str]:
    out = [
        "| Arm | " + " | ".join(f"Level {lv}" for lv in levels) + " |",
        "|---|" + "---|" * len(levels),
    ]
    for label, by_level in cells.items():
        out.append(
            f"| {label} | "
            + " | ".join(pct(by_level[lv].accuracy) if lv in by_level else "" for lv in levels)
            + " |"
        )
    return [*out, ""]


def splice(readme: str, body: Sequence[str]) -> str:
    """The README with the text between the result markers replaced."""
    if START not in readme or END not in readme:
        raise ValueError(f"the README has no {START} ... {END} block")
    head, rest = readme.split(START, 1)
    _, tail = rest.split(END, 1)
    return head + START + "\n" + "\n".join(body) + "\n" + END + tail


Loader = Callable[[], Answers]


def run_dirs(root: Path, arm: Arm, corpora: Sequence[str], part: str, level: int) -> list[Path]:
    return [
        root / "runs" / f"arm-{arm.arm}" / str(arm.route) / "p1" / f"level{level}" / c / part
        for c in corpora
    ]


def answers_for(
    root: Path,
    arm: Arm,
    corpora: Sequence[str],
    part: str,
    level: int,
    rules_files: Sequence[Path],
    table: str = "",
) -> Answers | None:
    """An arm's answers on some corpora: frontier reads from their run directories (arm D
    charged for its OCR too), arm E from its rules runs, arms B and C from their served
    reads (B's model the one trained for the table)."""
    ocr = rules_answers(rules_files)
    if arm.arm == "e":
        return ocr if ocr.outputs else None
    if arm.arm in {"b", "c"}:
        from legible.train.recipe import chosen

        routes = (
            [chosen(arm.size, ds).run_id for ds in TABLE_SETS.get(table, ())]  # type: ignore[arg-type]
            if arm.arm == "b"
            else [str(arm.route)]
        )
        dirs = [
            root / "runs" / f"arm-{arm.arm}" / r / "p1" / f"level{level}" / c / part
            for r in routes
            for c in corpora
        ]
        found = selfhosted_answers(dirs)
        return found if found.outputs else None
    found = frontier_answers(run_dirs(root, arm, corpora, part, level))
    if not found.outputs:
        return None
    return with_ocr_cost(found, ocr.ocr_seconds) if arm.arm == "d" else found


def agreed_grades(
    doc_ids: Sequence[str], truth: Mapping[str, Truth], vision: Answers, text: Answers | None
) -> list[DocGrade]:
    """The vision read graded with each field's agreement with the text read as confidence.
    A document the text read lacks has no confidence, so all its fields go to review."""
    from legible.agreement import confidences

    out = []
    for d in doc_ids:
        if d not in vision.outputs:
            continue
        other = text.outputs.get(d) if text is not None else None
        conf = confidences(truth[d].schema, vision.outputs[d], other) if other is not None else {}
        out.append(
            grade_document(
                truth[d].schema,
                d,
                truth[d].record,
                vision.outputs[d],
                page_text=truth[d].text,
                alternatives=truth[d].alternatives,
                confidences=conf,
            )
        )
    return out


def review_table(rows: Sequence[tuple[str, Any]]) -> list[str]:
    """Rows of (corpus label, ReviewResult or None)."""
    import math

    out = [
        "| Corpus | Fields sent to a person (95% CI) | Accuracy of the fields accepted | "
        "Reached 99% on dev |",
        "|---|---|---|---|",
    ]
    for label, r in rows:
        if r is None:
            out.append(f"| {label} | not yet measured | | |")
            continue
        reached = math.isfinite(r.threshold.value)
        accepted = pct(r.accepted_accuracy) if reached else "none accepted"
        dev = (
            f"yes, {100 * r.threshold.dev_accepted_accuracy:.1f}% on dev"
            if reached
            else "no: fields the two reads agree on are right less than 99% of the time on "
            "dev, so every field goes to a person"
        )
        out.append(f"| {label} | {pct(r.review_rate)} | {accepted} | {dev} |")
    return [*out, ""]
