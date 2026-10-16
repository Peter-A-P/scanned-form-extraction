"""Rasterising documents to 300 dpi pages, and the manifest that records each page.

Every arm reads the same pixels: the vision arms are sent these pages, the OCR arms run
Tesseract on them, and degradation starts from them. The manifest records each page's
sha256, size and the renderer's version, and is committed; the pages are not. A rebuild on
another machine either reproduces the hashes or says which pages differ.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Iterator
from pathlib import Path

import pymupdf
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


def page_path(corpus: str, doc_id: str, page: int) -> str:
    """Where a page lives under data/pages, relative to it."""
    stem = Path(doc_id).stem
    return f"{corpus}/{stem}/p{page:02d}.png"


def render_pdf(pdf: Path, corpus: str, doc_id: str, pages_dir: Path) -> list[PageEntry]:
    """Every page of a PDF at 300 dpi, greyscale-or-colour as printed, as PNG."""
    entries = []
    with pymupdf.open(pdf) as document:
        for index, page in enumerate(document):
            pixmap = page.get_pixmap(dpi=SOURCE_DPI, alpha=False)
            data = pixmap.tobytes("png")
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
                    width=pixmap.width,
                    height=pixmap.height,
                    sha256=hashlib.sha256(data).hexdigest(),
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
