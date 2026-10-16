"""Tesseract, its words with positions, and the positioned text arm D reads.

Tesseract is a system binary, run as a subprocess with TSV output: one row per word with its
box and confidence. Nothing here needs a Python binding, so the version that read a page is
whatever `tesseract --version` says, and every run records it.

Arm D's language model is given the page as positioned text: each OCR line on its own line,
each word at the column its left edge sits at, so that a value printed beside its label stays
beside it. That is the layout most OCR pipelines already produce, and it is where the plan's
first Rule C candidate is tested: whether that text carries what the image does.

Word accuracy, the unit the degradation levels are calibrated in, is one minus the word error
rate: word-level edit distance against the reference text over the reference's length.
"""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Sequence
from pathlib import Path

from pydantic import BaseModel, ConfigDict

#: Tesseract's page segmentation mode 3 (fully automatic, no OSD) and its default engine.
PSM = 3


class Word(BaseModel):
    model_config = ConfigDict(frozen=True)

    text: str
    left: int
    top: int
    width: int
    height: int
    conf: float
    block: int
    par: int
    line: int


class TesseractMissing(RuntimeError):
    """The tesseract binary is not on PATH."""


def tesseract_version() -> str:
    exe = shutil.which("tesseract")
    if exe is None:
        raise TesseractMissing("tesseract is not installed; it runs on the measurement machine")
    out = subprocess.run([exe, "--version"], capture_output=True, text=True, check=True)
    return (out.stdout or out.stderr).splitlines()[0].strip()


def parse_tsv(tsv: str) -> list[Word]:
    """Words from Tesseract's TSV output. Rows that are not words (level below 5) and empty
    words are dropped."""
    lines = tsv.splitlines()
    if not lines:
        return []
    header = lines[0].split("\t")
    col = {name: i for i, name in enumerate(header)}
    words = []
    for row in lines[1:]:
        cells = row.split("\t")
        if len(cells) < len(header) or cells[col["level"]] != "5":
            continue
        text = cells[col["text"]].strip()
        if not text:
            continue
        words.append(
            Word(
                text=text,
                left=int(cells[col["left"]]),
                top=int(cells[col["top"]]),
                width=int(cells[col["width"]]),
                height=int(cells[col["height"]]),
                conf=float(cells[col["conf"]]),
                block=int(cells[col["block_num"]]),
                par=int(cells[col["par_num"]]),
                line=int(cells[col["line_num"]]),
            )
        )
    return words


def run_tesseract(image: Path, *, lang: str = "eng") -> list[Word]:
    exe = shutil.which("tesseract")
    if exe is None:
        raise TesseractMissing("tesseract is not installed; it runs on the measurement machine")
    out = subprocess.run(
        [exe, str(image), "stdout", "-l", lang, "--psm", str(PSM), "tsv"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    return parse_tsv(out.stdout)


def positioned_text(words: Sequence[Word], page_width: int, *, columns: int = 160) -> str:
    """The page as lines of text with each word at its left edge's column.

    Lines are Tesseract's own (block, paragraph, line), ordered top to bottom by their first
    word; a word that would overlap the previous one on its line is pushed one space right.
    """
    lines: dict[tuple[int, int, int], list[Word]] = {}
    for w in words:
        lines.setdefault((w.block, w.par, w.line), []).append(w)
    ordered = sorted(
        lines.values(), key=lambda ws: (min(w.top for w in ws), min(w.left for w in ws))
    )
    out = []
    for ws in ordered:
        row = ""
        for w in sorted(ws, key=lambda w: w.left):
            column = round(w.left / page_width * columns) if page_width else 0
            if len(row) >= column:
                row += " " if row else ""
            else:
                row += " " * (column - len(row))
            row += w.text
        out.append(row.rstrip())
    return "\n".join(out)


def word_accuracy(hypothesis: Sequence[str], reference: Sequence[str]) -> float:
    """1 - word error rate. Can be negative when the hypothesis is much longer than the
    reference, as WER can exceed one; reported as computed."""
    if not reference:
        return 1.0 if not hypothesis else 0.0
    previous = list(range(len(hypothesis) + 1))
    for i, r in enumerate(reference, 1):
        current = [i]
        for j, h in enumerate(hypothesis, 1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (r != h)))
        previous = current
    return 1 - previous[-1] / len(reference)
