"""Rasterising documents to 300 dpi pages, and the manifest that records each page.

Every arm reads the same pixels: the vision arms are sent these pages, the OCR arms run
Tesseract on them, and degradation starts from them. The manifest records each page's
sha256, size and the renderer's version, and is committed; the pages are not. A rebuild on
another machine either reproduces the hashes or says which pages differ.
"""

from __future__ import annotations

import hashlib
import io
import json
from collections.abc import Iterable, Iterator, Sequence
from pathlib import Path

import pymupdf
from PIL import Image
from pydantic import BaseModel, ConfigDict

from legible.degrade import SOURCE_DPI


class PageEntry(BaseModel):
    """One rendered page."""

    model_config = ConfigDict(frozen=True)

    corpus: str
    doc_id: str
    page: int
    path: str
    width: int
    height: int
    sha256: str
    #: Degrees the rendered page was turned (counter-clockwise) to match the benchmark's own
    #: reading frame; see `orient`.
    rotation: int = 0


def page_path(corpus: str, doc_id: str, page: int) -> str:
    """Where a page lives under data/pages, relative to it."""
    stem = Path(doc_id).stem
    return f"{corpus}/{stem}/p{page:02d}.png"


class Frame(BaseModel):
    """The benchmark's own view of a page: whether its OCR saw it landscape, and where its
    tokens were (normalised boxes), so a page scanned sideways can be turned to match."""

    model_config = ConfigDict(frozen=True)

    landscape: bool
    boxes: tuple[tuple[float, float, float, float], ...]


def _ink(img: Image.Image, boxes: Sequence[tuple[float, float, float, float]]) -> float:
    """Mean darkness inside the boxes: where the benchmark saw words, the right orientation
    has ink."""
    grey = img.convert("L")
    w, h = grey.size
    total = 0.0
    for x1, y1, x2, y2 in boxes:
        region = grey.crop(
            (
                int(x1 * w),
                int(y1 * h),
                max(int(x1 * w) + 1, int(x2 * w)),
                max(int(y1 * h) + 1, int(y2 * h)),
            )
        )
        hist = region.histogram()
        n = sum(hist) or 1
        total += 1 - sum(i * c for i, c in enumerate(hist)) / (255 * n)
    return total / max(1, len(boxes))


def orient(data: bytes, frame: Frame) -> tuple[bytes, int]:
    """The page turned to the benchmark's orientation, and by how much.

    Fifteen DeepForm documents are portrait PDFs of landscape scans: the PDF says portrait,
    VRDU's OCR read them landscape, and its boxes are in that frame. Such a page is turned
    90 or 270 degrees, whichever puts more ink inside the benchmark's token boxes. A page
    whose orientation already agrees is returned untouched (a 180-degree scan would not be
    caught, and none was seen).
    """
    with Image.open(io.BytesIO(data)) as img:
        if (img.width > img.height) == frame.landscape or not frame.boxes:
            return data, 0
        best = max((90, 270), key=lambda angle: _ink(img.rotate(angle, expand=True), frame.boxes))
        out = io.BytesIO()
        img.rotate(best, expand=True).save(out, format="PNG")
        return out.getvalue(), best


def render_pdf(
    pdf: Path, corpus: str, doc_id: str, pages_dir: Path, frames: Sequence[Frame] | None = None
) -> list[PageEntry]:
    """Every page of a PDF at 300 dpi, greyscale-or-colour as printed, as PNG, turned to the
    benchmark's frame where `frames` says it reads the page the other way round."""
    entries = []
    with pymupdf.open(pdf) as document:
        for index, page in enumerate(document):
            pixmap = page.get_pixmap(dpi=SOURCE_DPI, alpha=False)
            data = pixmap.tobytes("png")
            rotation = 0
            width, height = pixmap.width, pixmap.height
            if frames is not None and index < len(frames):
                data, rotation = orient(data, frames[index])
                if rotation:
                    width, height = height, width
            rel = page_path(corpus, doc_id, index)
            dest = pages_dir / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
            entries.append(
                PageEntry(
                    corpus=corpus,
                    doc_id=doc_id,
                    page=index,
                    path=rel,
                    width=width,
                    height=height,
                    sha256=hashlib.sha256(data).hexdigest(),
                    rotation=rotation,
                )
            )
    return entries


def renderer() -> str:
    """The renderer and its version, recorded in the manifest header."""
    return f"pymupdf {pymupdf.VersionBind} (MuPDF {pymupdf.VersionFitz}) at {SOURCE_DPI} dpi"


def write_manifest(path: Path, entries: Iterable[PageEntry], source: str | None = None) -> int:
    """One JSON line per page, sorted, after a header line naming the renderer, or for a
    corpus that is not rendered (CORD's photographs), where its pages came from."""
    rows = sorted(entries, key=lambda e: (e.doc_id, e.page))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps({"renderer": source or renderer(), "pages": len(rows)}) + "\n")
        for e in rows:
            f.write(e.model_dump_json() + "\n")
    return len(rows)


def read_manifest(path: Path) -> Iterator[PageEntry]:
    with path.open(encoding="utf-8") as f:
        next(f)
        for line in f:
            yield PageEntry.model_validate_json(line)
