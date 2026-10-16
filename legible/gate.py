"""What the release gate (project 03) is handed: an eval spec and both sides' outcomes.

Non-inferiority of the best fine-tune against the best frontier arm is decided by the 03 gate,
not computed here, so the paired test, the power screen and Holm's adjustment are one
implementation across the portfolio (03's docs/gate-adapter.md; 06 is the first user). This
module writes the gate's three files from this project's grades:

    uv run gate compare --spec spec.yaml --baseline baseline.json \\
        --candidate candidate.json --ledger <this repository>/gate-runs/ledger.jsonl

**One spec per corpus, one suite per field, one outcome per document.** The gate's test takes
one right-or-wrong outcome per item, and the item has to be the document: the fields of one
form are correlated, so a suite of fields would pass correlated draws off as independent.
A scalar field's outcome is whether the document's value for it is right. A line-item column
(DeepForm's `line_item.sub_amount`, CORD's `menu.price`) has one outcome per document too:
whether every row's value in that column is right. That is stricter than row accuracy, and it
is the clerk's question (does this order's amounts column need correcting), asked of both
sides alike.

**Which documents a suite holds.** A document where the field is blank on the page and both
sides left it blank says nothing about either, and counting it as right for both would pull
every difference towards zero, which is the direction that makes non-inferiority easy. So a
suite holds the documents where the field was scored for either side: the truth has it, or
either side filled it. The two sides are written together for that reason.

**A call that failed is not an answer.** Its document is left out of every suite of that side
and counted as ungradeable, the gate's own rule. An answer that did not parse is an answer,
and is wrong.

**The margin is three points per suite** (PLAN.md section 5), the gate's default and 06's.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Final

from pydantic import BaseModel, ConfigDict

from legible.grade import DocGrade
from legible.schema import CorpusSchema, all_names

DELTA_POINTS: Final = 3.0


class SideMeta(BaseModel):
    """What the gate prints beside a side's outcomes: where it came from, what it cost."""

    model_config = ConfigDict(frozen=True)

    label: str
    run_id: str
    directory: str
    calls: int
    latency_p50_ms: float
    cost_usd: float
    uncosted_calls: int


def suite_key(path: str) -> str:
    """The gate's keys are lower case with dashes or underscores; `group.field` becomes
    `group-field`."""
    return path.lower().replace(".", "-")


def _scored(grade: DocGrade, path: str) -> bool:
    return any(o.path == path for o in grade.outcomes)


def _right(grade: DocGrade, path: str) -> bool:
    """Every scored outcome of this field (every row, for a column) is right. A field not
    scored at all was a correct abstention."""
    return all(o.correct for o in grade.outcomes if o.path == path)


def export(
    schema: CorpusSchema,
    baseline: Sequence[DocGrade],
    candidate: Sequence[DocGrade],
    *,
    baseline_meta: SideMeta,
    candidate_meta: SideMeta,
    baseline_failed: Sequence[str] = (),
    candidate_failed: Sequence[str] = (),
    name: str,
    delta_points: float = DELTA_POINTS,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """(spec, baseline side, candidate side) in the gate's shapes.

    Both sides must cover the same documents, graded or failed: the gate pairs by id, and a
    document one side never saw is a different comparison, not a missing item.
    """
    b = {g.doc_id: g for g in baseline}
    c = {g.doc_id: g for g in candidate}
    b_all = set(b) | set(baseline_failed)
    c_all = set(c) | set(candidate_failed)
    if b_all != c_all:
        raise ValueError(
            f"the sides cover different documents: {len(b_all - c_all)} only in the baseline, "
            f"{len(c_all - b_all)} only in the candidate"
        )
    if set(b) & set(baseline_failed) or set(c) & set(candidate_failed):
        raise ValueError("a document is both graded and failed on one side")
    paths = all_names(schema.fields)
    suites_b: dict[str, Any] = {}
    suites_c: dict[str, Any] = {}
    for path in paths:
        docs = sorted(d for d in set(b) & set(c) if _scored(b[d], path) or _scored(c[d], path))
        # A document only one side graded (the other failed) still counts for the side that
        # answered, when that side scored the field: the gate pairs and drops it itself.
        docs_b = docs + sorted(d for d in set(b) - set(c) if _scored(b[d], path))
        docs_c = docs + sorted(d for d in set(c) - set(b) if _scored(c[d], path))
        key = suite_key(path)
        suites_b[key] = _suite(
            key, {d: _right(b[d], path) for d in docs_b}, len(baseline_failed), baseline_meta
        )
        suites_c[key] = _suite(
            key, {d: _right(c[d], path) for d in docs_c}, len(candidate_failed), candidate_meta
        )
    return (
        spec(schema, name=name, delta_points=delta_points),
        _side(baseline_meta, suites_b),
        _side(candidate_meta, suites_c),
    )


def spec_name(schema: CorpusSchema, level: str) -> str:
    """`legible-fara-unseen`: one spec per corpus and split level."""
    return f"legible-{schema.corpus}-{level}"


def spec(schema: CorpusSchema, *, name: str, delta_points: float = DELTA_POINTS) -> dict[str, Any]:
    """The eval spec in the gate's `EvalSpec` shape: one `outcomes_file` suite per field."""
    return {
        "version": 1,
        "name": name,
        "delta_points": delta_points,
        "alpha": 0.05,
        "resamples": 2000,
        "seed": 0,
        "suites": [
            {"key": suite_key(p), "source": {"kind": "outcomes_file", "block": suite_key(p)}}
            for p in all_names(schema.fields)
        ],
    }


def _suite(key: str, outcomes: dict[str, bool], failed: int, meta: SideMeta) -> dict[str, Any]:
    return {
        "suite": key,
        "outcomes": outcomes,
        "ungradeable_items": failed,
        "calls": meta.calls,
        "latency_p50_ms": meta.latency_p50_ms,
        "cost_usd": meta.cost_usd,
        "uncosted_calls": meta.uncosted_calls,
    }


def _side(meta: SideMeta, suites: dict[str, Any]) -> dict[str, Any]:
    return {
        "label": meta.label,
        "source": {"run_id": meta.run_id, "directory": meta.directory},
        "suites": suites,
    }
