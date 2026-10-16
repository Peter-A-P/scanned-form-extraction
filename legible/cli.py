"""legible: the command line. Commands are added as the stages they run are built."""

from __future__ import annotations

import os
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Literal

import typer
from PIL import Image

from legible import __version__
from legible.degrade import LEVELS, degrade, to_png

app = typer.Typer(no_args_is_help=True, add_completion=False)
data_app = typer.Typer(no_args_is_help=True, help="Fetch, verify, render and split the corpora.")
app.add_typer(data_app, name="data")

#: Committed: page manifests and split summaries. Everything fetched or rendered lives under
#: the data root instead, which defaults to ./data and is moved with LEGIBLE_DATA (a synced
#: folder is no place for gigabytes of page images).
MANIFESTS = Path("manifests")


def data_root() -> Path:
    return Path(os.environ.get("LEGIBLE_DATA", "data"))


Corpus = Literal["fara", "deepform", "cord"]


@app.callback()
def _root() -> None:
    """Forms That Read Themselves."""


@app.command()
def version() -> None:
    """Print the package version."""
    typer.echo(__version__)


@app.command("degrade")
def degrade_page(
    page: Path = typer.Argument(..., exists=True, dir_okay=False, help="A 300 dpi page image."),
    out: Path = typer.Argument(..., help="Where to write the degraded PNG."),
    level: int = typer.Option(..., min=0, max=len(LEVELS) - 1, help="Degradation level, 0 to 4."),
    page_id: str = typer.Option(..., help="The page's manifest id; it seeds the random draws."),
) -> None:
    """Degrade one page to a level, reproducibly."""
    with Image.open(page) as image:
        out.write_bytes(to_png(degrade(image, page_id, level)))


def _corpora(corpus: str) -> list[Corpus]:
    if corpus == "all":
        return ["fara", "deepform", "cord"]
    if corpus not in {"fara", "deepform", "cord"}:
        raise typer.BadParameter("corpus is fara, deepform, cord or all")
    return [corpus]  # type: ignore[list-item]


@data_app.command("fetch")
def data_fetch(corpus: str = typer.Argument("all", help="fara, deepform, cord or all.")) -> None:
    """Fetch a corpus at its pinned commit, verifying every file."""
    from legible.data.cord import fetch_shards
    from legible.data.fetch import load_checksums
    from legible.data.vrdu import DIRECTORY, fetch_files

    raw = data_root() / "raw" / "vrdu"
    files = load_checksums("vrdu").files
    for c in _corpora(corpus):
        if c == "cord":
            fetch_shards(data_root() / "raw" / "cord")
            typer.echo("cord: verified")
            continue
        prefix = DIRECTORY[c] + "/"
        paths = sorted(p for p in files if p.startswith(prefix))
        typer.echo(f"{c}: {len(paths)} files")
        fetch_files(paths, raw)
        typer.echo(f"{c}: verified")


@data_app.command("build")
def data_build(corpus: str = typer.Argument("all", help="fara, deepform, cord or all.")) -> None:
    """Parse truth, check the headline splits, render pages and write the manifests."""
    from legible.data.cord import read_shard, shard_split
    from legible.data.fetch import load_checksums
    from legible.data.render import render_pdf, write_manifest
    from legible.data.splits_report import write_splits
    from legible.data.vrdu import (
        DIRECTORY,
        check_split,
        check_templates,
        headline_split_files,
        read_dataset,
        read_split,
    )

    raw = data_root() / "raw" / "vrdu"
    pages_dir = data_root() / "pages"
    for c in _corpora(corpus):
        if c == "cord":
            cord_raw = data_root() / "raw" / "cord"
            counts: dict[str, int] = {}
            pages = []
            seen: set[str] = set()
            for shard in sorted(load_checksums("cord").files):
                for doc, entry in read_shard(cord_raw / shard, pages_dir):
                    if doc.doc_id in seen:
                        raise ValueError(f"cord: {doc.doc_id} appears twice")
                    seen.add(doc.doc_id)
                    counts[shard_split(shard)] = counts.get(shard_split(shard), 0) + 1
                    if entry is not None:
                        pages.append(entry)
            write_manifest(MANIFESTS / "cord-pages.jsonl", pages)
            typer.echo(f"cord: {counts}")
            continue
        docs = list(read_dataset(c, raw))
        known = {d.doc_id for d in docs}
        splits = [
            read_split(c, raw / p)
            for level in ("unseen", "mixed")
            for p in headline_split_files(c, level)  # type: ignore[arg-type]
        ]
        for s in splits:
            check_split(s, known)
            check_templates(s)
        # One process per core: rendering is CPU-bound and the documents are independent.
        entries = []
        pdfs = raw / DIRECTORY[c] / "main" / "pdfs"
        with ProcessPoolExecutor(max_workers=max(1, (os.cpu_count() or 2) - 1)) as pool:
            futures = [
                pool.submit(render_pdf, pdfs / d.doc_id, c, d.doc_id, pages_dir) for d in docs
            ]
            for i, future in enumerate(futures, 1):
                entries += future.result()
                if i % 200 == 0:
                    typer.echo(f"{c}: rendered {i} of {len(docs)} documents")
        n = write_manifest(MANIFESTS / f"{c}-pages.jsonl", entries)
        write_splits(MANIFESTS / f"{c}-splits.json", c, docs, splits)
        typer.echo(f"{c}: {len(docs)} documents, {n} pages, {len(splits)} headline split files")


def main() -> None:
    app()
