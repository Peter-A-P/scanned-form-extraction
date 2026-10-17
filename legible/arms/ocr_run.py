"""Running Tesseract over a corpus's pages, at a degradation level, resumably.

Each page's OCR is stored as JSON under the data root, `ocr/level{n}/<page path>.json`, so a
run that stops resumes where it stopped and the two arms that read OCR (D and E) read the same
words. A degraded page is made by legible.degrade on the way in and kept under
`degraded/level{n}/`, so the vision arms are sent the identical pixels.

Measured runs happen on the rented CPU machine, never the laptop; the stored page records the
Tesseract version and the seconds it took, which is where OCR's cost per page comes from.
"""

from __future__ import annotations

import hashlib
import os
from collections.abc import Sequence
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from PIL import Image

from legible.arms.ocr import PREPROCESS, OcrPage, ocr_page, tesseract_version
from legible.data.render import PageEntry
from legible.degrade import degrade, to_png


def page_image(root: Path, entry: PageEntry, level: int) -> Path:
    """The page at a level: the rendered page at 0, a degraded copy (made once) above."""
    source = root / "pages" / entry.path
    if level == 0:
        return source
    dest = root / "degraded" / f"level{level}" / entry.path
    if not dest.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        with Image.open(source) as img:
            dest.write_bytes(to_png(degrade(img, f"{entry.corpus}/{entry.path}", level)))
    return dest


def stored(root: Path, level: int, page_path: str) -> Path:
    return root / "ocr" / f"level{level}" / (page_path + ".json")


def _one(root: Path, entry: PageEntry, level: int, version: str) -> float:
    out = stored(root, level, entry.path)
    image = page_image(root, entry, level)
    sha = entry.sha256 if level == 0 else hashlib.sha256(image.read_bytes()).hexdigest()
    page = ocr_page(
        image,
        entry.path,
        sha,
        entry.width,
        entry.height,
        version=version,
        prep=PREPROCESS[entry.corpus],
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    partial = out.with_name(out.name + ".partial")
    partial.write_text(page.model_dump_json(), encoding="utf-8")
    partial.replace(out)
    return page.seconds


def run(
    root: Path, entries: Sequence[PageEntry], level: int, *, workers: int | None = None
) -> tuple[int, float]:
    """OCR every page not already stored. Returns (pages read, seconds summed)."""
    version = tesseract_version()
    todo = [e for e in entries if not _current(root, level, e)]
    workers = workers or max(1, (os.cpu_count() or 2) - 1)
    total = 0.0
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for seconds in pool.map(
            _one, [root] * len(todo), todo, [level] * len(todo), [version] * len(todo)
        ):
            total += seconds
    return len(todo), total


def _current(root: Path, level: int, entry: PageEntry) -> bool:
    """Stored OCR exists and, at level 0, is of the page as now rendered."""
    path = stored(root, level, entry.path)
    if not path.exists():
        return False
    try:
        page = OcrPage.model_validate_json(path.read_text(encoding="utf-8"))
    except ValueError:
        return False
    if page.preprocess != PREPROCESS[entry.corpus]:
        return False
    return level != 0 or page.page_sha256 == entry.sha256


def load(root: Path, level: int, page_path: str) -> OcrPage:
    return OcrPage.model_validate_json(stored(root, level, page_path).read_text(encoding="utf-8"))
