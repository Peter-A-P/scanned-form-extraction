"""Tesseract, its words with positions, and the positioned text arm D reads.

Tesseract is a system binary, run as a subprocess with TSV output: one row per word with its
box and confidence. Nothing here needs a Python binding, so the version that read a page is
whatever `tesseract --version` says, and every run records it.

Arm D's language model is given the page as positioned text: each OCR line on its own line,
each word at the column its left edge sits at, so that a value printed beside its label stays
beside it. That is the layout most OCR pipelines already produce, and it is where the plan's
first candidate for a rejected approach is tested: whether that text carries what the image does.

Word accuracy, the unit the degradation levels are calibrated in, is one minus the word error
rate: word-level edit distance against the reference text over the reference's length.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
from collections.abc import Sequence
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter
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


#: Where the Windows installer puts it, which it does not add to PATH.
_WINDOWS_DEFAULT = Path("C:/Program Files/Tesseract-OCR/tesseract.exe")


def tesseract_exe() -> str:
    """The binary: LEGIBLE_TESSERACT if set, else PATH, else the Windows installer's place."""
    configured = os.environ.get("LEGIBLE_TESSERACT")
    if configured:
        return configured
    found = shutil.which("tesseract")
    if found is not None:
        return found
    if _WINDOWS_DEFAULT.exists():
        return str(_WINDOWS_DEFAULT)
    raise TesseractMissing("tesseract is not installed; it runs on the measurement machine")


def tesseract_version() -> str:
    exe = tesseract_exe()
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
    exe = tesseract_exe()
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


class OcrPage(BaseModel):
    """One page's OCR, as stored: the words, the page size, the Tesseract that read it and
    how long it took. One process per page and one thread per process (OMP_THREAD_LIMIT=1),
    so the wall time is the CPU time OCR's cost per page is computed from."""

    model_config = ConfigDict(frozen=True)

    page_path: str
    #: The sha256 of the page image read, so OCR of a page since re-rendered is not reused.
    page_sha256: str
    width: int
    height: int
    tesseract: str
    preprocess: Preprocess
    seconds: float
    words: tuple[Word, ...]


class Preprocess(BaseModel):
    """What is done to a page before Tesseract sees it, per corpus, chosen on training pages.

    Scans (VRDU) go in as rendered at 300 dpi with automatic page segmentation. CORD's
    receipts are phone photographs of dot-matrix and thermal print at about 100 dpi, under
    uneven light; as they are, Tesseract read no words at all from the first training receipt
    tried. So they are scaled up twice, median-filtered, binarised against the local mean (so a
    shadow does not swallow a column) and read as one uniform block, which keeps an item and
    its price on one line. Any OCR pipeline that reads receipts does something of this kind;
    leaving it out would measure a straw man.
    """

    model_config = ConfigDict(frozen=True)

    scale: float = 1.0
    #: Local-mean binarisation window (pixels, after scaling) and offset; 0 for none.
    window: int = 0
    offset: float = 0.0
    median: int = 0
    psm: int = PSM


SCANS = Preprocess()
PHOTOS = Preprocess(scale=2.0, window=51, offset=10.0, median=3, psm=6)
PREPROCESS: dict[str, Preprocess] = {
    "fara": SCANS,
    "deepform": SCANS,
    "cord": PHOTOS,
    # 300 ppi binary scans, like the VRDU pages: nothing to add.
    "nist": SCANS,
}


def binarise(img: Image.Image, window: int, offset: float) -> Image.Image:
    """Black where a pixel is darker than the mean of the window around it, less `offset`."""
    a = np.asarray(img.convert("L"), dtype=np.float64)
    ii = np.pad(a, ((1, 0), (1, 0))).cumsum(0).cumsum(1)
    h, w = a.shape
    r = window // 2
    y0 = np.clip(np.arange(h) - r, 0, h)
    y1 = np.clip(np.arange(h) + r + 1, 0, h)
    x0 = np.clip(np.arange(w) - r, 0, w)
    x1 = np.clip(np.arange(w) + r + 1, 0, w)
    total = ii[y1][:, x1] - ii[y0][:, x1] - ii[y1][:, x0] + ii[y0][:, x0]
    mean = total / ((y1 - y0)[:, None] * (x1 - x0)[None, :])
    return Image.fromarray(np.where(a < mean - offset, 0, 255).astype(np.uint8))


def prepare(image: Path, prep: Preprocess) -> Image.Image:
    with Image.open(image) as img:
        page = img.convert("L")
    if prep.scale != 1.0:
        page = page.resize(
            (round(page.width * prep.scale), round(page.height * prep.scale)),
            Image.Resampling.LANCZOS,
        )
    if prep.median:
        page = page.filter(ImageFilter.MedianFilter(prep.median))
    if prep.window:
        page = binarise(page, prep.window, prep.offset)
    return page


def ocr_page(
    image: Path,
    page_path: str,
    page_sha256: str,
    width: int,
    height: int,
    *,
    version: str,
    prep: Preprocess = SCANS,
) -> OcrPage:
    """One page through the preprocessing and Tesseract. Word boxes are returned in the
    page's own pixels, whatever scale Tesseract read it at."""
    exe = tesseract_exe()
    env = dict(os.environ, OMP_THREAD_LIMIT="1")
    start = time.perf_counter()
    with tempfile.TemporaryDirectory() as tmp:
        source = image
        if prep != SCANS:
            source = Path(tmp) / "page.png"
            prepare(image, prep).save(source)
        out = subprocess.run(
            [exe, str(source), "stdout", "-l", "eng", "--psm", str(prep.psm), "tsv"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
            env=env,
        )
    seconds = time.perf_counter() - start
    words = parse_tsv(out.stdout)
    if prep.scale != 1.0:
        k = 1 / prep.scale
        words = [
            w.model_copy(
                update={
                    "left": round(w.left * k),
                    "top": round(w.top * k),
                    "width": round(w.width * k),
                    "height": round(w.height * k),
                }
            )
            for w in words
        ]
    return OcrPage(
        page_path=page_path,
        page_sha256=page_sha256,
        width=width,
        height=height,
        tesseract=version,
        preprocess=prep,
        seconds=seconds,
        words=tuple(words),
    )


OcrPage.model_rebuild()
