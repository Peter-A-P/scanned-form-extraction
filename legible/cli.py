"""legible: the command line. Commands are added as the stages they run are built."""

from __future__ import annotations

import json
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
            write_manifest(
                MANIFESTS / "cord-pages.jsonl",
                pages,
                source="CORD v2 parquet images, PNG bytes kept as published (not rendered)",
            )
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


@data_app.command("audit")
def data_audit() -> None:
    """Draw the 200-label audit sample and write the local worksheet (never published)."""
    from legible.data.audit import crop, flat_values, labels_of, sample, worksheet
    from legible.data.cord import read_shard
    from legible.data.fetch import load_checksums
    from legible.data.render import page_path
    from legible.data.vrdu import read_dataset

    raw = data_root() / "raw"
    pages = data_root() / "pages"
    labels = []
    for c in ("fara", "deepform"):
        for d in read_dataset(c, raw / "vrdu"):
            labels += labels_of(c, d.doc_id, d.boxes, flat_values(d.truth))
    for shard in sorted(load_checksums("cord").files):
        for doc, _ in read_shard(raw / "cord" / shard, None):
            labels += labels_of("cord", doc.doc_id, doc.boxes, flat_values(doc.truth))
    chosen = sample(labels)
    crops = {
        x.label_id: crop((pages / page_path(x.corpus, x.doc_id, x.box[0])).read_bytes(), x.box)
        for x in chosen
    }
    out = data_root() / "audit" / "worksheet.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(worksheet(chosen, crops), encoding="utf-8")
    (MANIFESTS / "audit-sample.json").write_text(
        # Ids and boxes only: the values come with the fetched corpus, and a registration
        # form's names are not redistributed here (docs/data.md).
        json.dumps([x.model_dump(mode="json", exclude={"value"}) for x in chosen], indent=1) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    typer.echo(f"{len(chosen)} labels; worksheet at {out}")


@data_app.command("audit-report")
def data_audit_report(
    decisions: Path = typer.Argument(
        Path("docs/audit/decisions.json"), exists=True, dir_okay=False
    ),
) -> None:
    """Write docs/audit.md from Peter's decisions on the committed sample."""
    from legible.data.audit import Label, read_decisions, report

    sample = [
        Label.model_validate({**x, "value": ""})
        for x in json.loads((MANIFESTS / "audit-sample.json").read_text(encoding="utf-8"))
    ]
    rows = report(sample, read_decisions(decisions))
    lines = [
        "# Label audit",
        "",
        "Written by `legible data audit-report` from `docs/audit/decisions.json`; do not edit.",
        "",
        "| Corpus | Labels | Audited | Disagreement (95% CI) | Unreadable |",
        "|---|---|---:|---|---:|",
    ]
    lines += [
        f"| {r.corpus} | {r.stratum} | {r.audited} | {r.disagreement} | {r.unreadable} |"
        for r in rows
    ]
    text = "\n".join(lines) + "\n"
    Path("docs/audit.md").write_text(text, encoding="utf-8", newline="\n")
    typer.echo(text)


gate_app = typer.Typer(no_args_is_help=True, help="Files for the 03 release gate.")
app.add_typer(gate_app, name="gate")

#: The comparisons the gate decides: each VRDU corpus on its unseen-template headline and on
#: the mixed-template gap, and CORD on its test set.
GATE_LEVELS: dict[str, tuple[str, ...]] = {
    "fara": ("unseen", "mixed"),
    "deepform": ("unseen", "mixed"),
    "cord": ("test",),
}


@gate_app.command("specs")
def gate_specs(
    out: Path = typer.Option(Path("gate-runs/specs"), help="Where to write them."),
) -> None:
    """Write the gate's eval spec for every corpus and level. Committed; they change only
    when a schema does."""
    import yaml

    from legible.gate import spec, spec_name
    from legible.schema.corpora import SCHEMAS

    out.mkdir(parents=True, exist_ok=True)
    for corpus, levels in GATE_LEVELS.items():
        for level in levels:
            schema = SCHEMAS[corpus]
            name = spec_name(schema, level)
            body = yaml.safe_dump(spec(schema, name=name), sort_keys=False)
            header = (
                f"# The 03 gate's eval spec for {corpus}, {level}: one suite per field, one\n"
                "# outcome per document, a three-point margin (legible/gate.py). Written by\n"
                "# `legible gate specs` from the schema; do not edit.\n"
            )
            (out / f"{name}.yaml").write_text(header + body, encoding="utf-8", newline="\n")
            typer.echo(f"{name}: {len(spec(schema, name=name)['suites'])} suites")


def main() -> None:
    app()
