"""What each degradation level does to reading, measured once on NIST's clean pages.

The parameters in `legible.degrade` say what a level does to the pixels; this says what it
does to OCR, so that "level 3" names a word accuracy rather than a blur radius. Two numbers
per level, over the 300 NIST curve pages (the same pages every arm reads at every level), each
the mean over pages with its 95% bootstrap interval:

- **Word accuracy against the clean read**: one minus the word error rate of Tesseract on the
  degraded page, with Tesseract on the same page at level 0 as the reference. The form's own
  printed text is most of a page's words, so this is the loss the degradation causes, not
  Tesseract's error on the form.
- **Field words recovered**: the share of the words in the page's truth values (NIST's answer
  file, by construction) that appear among Tesseract's words, letters and digits only, counted
  with multiplicity. This one is absolute: it says how much of what is to be extracted the
  OCR still sees.

Arithmetic on stored OCR (`legible.arms.ocr_run`): the OCR itself was run, and timed, on the
measuring machine; this only counts.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from legible.arms.ocr import OcrPage, word_accuracy
from legible.arms.ocr_run import load
from legible.data.render import PageEntry
from legible.degrade import LEVELS
from legible.schema import Record
from legible.stats import Interval, mean_ci

_TOKEN = re.compile(r"[A-Za-z0-9]+")


def tokens(text: str) -> list[str]:
    return _TOKEN.findall(text)


def page_words(page: OcrPage) -> list[str]:
    return [t for w in page.words for t in tokens(w.text)]


def field_recall(truth: Record, page: OcrPage) -> float | None:
    """Share of the truth values' words found among the page's OCR words, or None when the
    page has no text fields filled."""
    want = Counter(t for v in truth.values() if isinstance(v, str) for t in tokens(v))
    if not want:
        return None
    have = Counter(page_words(page))
    return sum(min(n, have[t]) for t, n in want.items()) / sum(want.values())


class LevelRow(BaseModel):
    model_config = ConfigDict(frozen=True)

    level: int
    pages: int
    word_accuracy: Interval
    field_recall: Interval


def calibrate(
    root: Path, entries: Sequence[PageEntry], truths: Mapping[str, Record]
) -> list[LevelRow]:
    """One row per level over the given pages, from their stored OCR at every level."""
    clean = {e.doc_id: load(root, 0, e.path) for e in entries}
    rows = []
    for level in LEVELS:
        acc: list[float] = []
        recall: list[float] = []
        for e in entries:
            page = clean[e.doc_id] if level.level == 0 else load(root, level.level, e.path)
            acc.append(word_accuracy(page_words(page), page_words(clean[e.doc_id])))
            r = field_recall(truths[e.doc_id], page)
            if r is not None:
                recall.append(r)
        rows.append(
            LevelRow(
                level=level.level,
                pages=len(entries),
                word_accuracy=mean_ci(acc),
                field_recall=mean_ci(recall),
            )
        )
    return rows


def _pct(i: Interval) -> str:
    return f"{100 * i.point:.1f}% ({100 * i.low:.1f} to {100 * i.high:.1f})"


def table(rows: Sequence[LevelRow]) -> list[str]:
    params = {lv.level: lv for lv in LEVELS}
    out = [
        "| Level | Resolution | Blur | Skew up to | Noise | JPEG quality "
        "| Word accuracy against the clean read | Field words recovered |",
        "|---:|---:|---:|---:|---:|---:|---|---|",
    ]
    for r in rows:
        p = params[r.level]
        jpeg = str(p.jpeg_quality) if p.jpeg_quality is not None else "none"
        out.append(
            f"| {r.level} | {p.dpi} dpi | {p.blur} px | {p.skew} degrees | {100 * p.noise:.1f}% "
            f"| {jpeg} | {_pct(r.word_accuracy)} | {_pct(r.field_recall)} |"
        )
    return out
