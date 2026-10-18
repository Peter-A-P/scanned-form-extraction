"""A frontier read's confidence: whether a second, independent read of the page agrees.

The frontier models are asked for no confidence (PLAN.md section 2.6). Instead each field of
the vision read (arm A) is scored 1 when the OCR-text read of the same page by the same model
(arm D) gives the same value under the field's own matcher, and 0 when it does not. Both
leaving a field empty is agreement. It costs nothing extra, because both arms are run anyway,
and it is the confidence a review queue built on these pipelines would actually have.

For a repeated group, a cell of the vision read agrees when the OCR-text read has the same
value in the same column of any of its rows: the two reads need not list rows in the same
order, and the grader pairs rows by content too.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from legible.grade import values_match
from legible.schema import CorpusSchema, FieldSpec


def _text(value: object) -> str | None:
    if value is None or isinstance(value, bool | list | dict):
        return None
    text = str(value).strip()
    return text or None


def _same(spec: FieldSpec, a: str | None, b: str | None) -> bool:
    if a is None or b is None:
        return a is None and b is None
    return values_match(spec, a, b)


def confidences(
    schema: CorpusSchema, vision: Mapping[str, Any] | None, text: Mapping[str, Any] | None
) -> dict[str, float]:
    """Per-field confidence for the vision read, keyed as `grade_document` takes them."""
    if vision is None:
        return {}
    other = text or {}
    out: dict[str, float] = {}
    for f in schema.scalars:
        out[f.name] = float(_same(f, _text(vision.get(f.name)), _text(other.get(f.name))))
    for group in schema.groups:
        rows = vision.get(group.name)
        theirs = other.get(group.name)
        their_rows = (
            [r for r in theirs if isinstance(r, Mapping)] if isinstance(theirs, list) else []
        )
        if not isinstance(rows, list):
            continue
        for j, item in enumerate(rows):
            mine = item if isinstance(item, Mapping) else {}
            for g in group.fields:
                v = _text(mine.get(g.name))
                agree = (
                    any(_same(g, v, _text(r.get(g.name))) for r in their_rows)
                    if v is not None
                    else not any(_text(r.get(g.name)) for r in their_rows)
                )
                out[f"{group.name}[{j}].{g.name}"] = float(agree)
    return out
