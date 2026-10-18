"""legible: the command line. Commands are added as the stages they run are built."""

from __future__ import annotations

import json
import os
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import TYPE_CHECKING, Literal

import typer
from PIL import Image

from legible import __version__
from legible.data.render import PageEntry
from legible.degrade import LEVELS, degrade, to_png

if TYPE_CHECKING:
    from legible.arms.read_run import RunSpec
    from legible.prompt import Prompt

app = typer.Typer(no_args_is_help=True, add_completion=False)
data_app = typer.Typer(no_args_is_help=True, help="Fetch, verify, render and split the corpora.")
app.add_typer(data_app, name="data")

#: Committed: page manifests and split summaries. Everything fetched or rendered lives under
#: the data root instead, which defaults to ./data and is moved with LEGIBLE_DATA (a synced
#: folder is no place for gigabytes of page images).
MANIFESTS = Path("manifests")


def data_root() -> Path:
    return Path(os.environ.get("LEGIBLE_DATA", "data"))


def manifest(corpus: str) -> Path:
    """A corpus's page manifest. NIST's faces (`nist_1040_1`) share one."""
    return MANIFESTS / f"{'nist' if corpus.startswith('nist') else corpus}-pages.jsonl"


Corpus = Literal["fara", "deepform", "cord", "nist"]


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
        return ["fara", "deepform", "cord", "nist"]
    if corpus not in {"fara", "deepform", "cord", "nist"}:
        raise typer.BadParameter("corpus is fara, deepform, cord, nist or all")
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
        if c == "nist":
            from legible.data.nist import fetch_sd2

            _, md5s = fetch_sd2(data_root() / "raw" / "nist")
            typer.echo(f"nist: archive verified; {len(md5s)} member checksums")
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
        if c == "nist":
            from legible.data import nist

            zip_path, md5s = nist.fetch_sd2(data_root() / "raw" / "nist")
            faces, nist_pages = [], []
            for face, nist_entry in nist.read_sd2(zip_path, md5s, pages_dir):
                faces.append(face)
                if nist_entry is not None:
                    nist_pages.append(nist_entry)
            rows = nist.split_rows(faces)
            nist.check_split(rows)
            write_manifest(
                MANIFESTS / "nist-pages.jsonl",
                nist_pages,
                source="NIST SD2 PNG bytes kept as published (300 ppi binary, not rendered)",
            )
            nist.write_splits(MANIFESTS / "nist-splits.json", rows)
            parts: dict[str, int] = {}
            for r in rows.values():
                parts[r.part] = parts.get(r.part, 0) + 1
            typer.echo(f"nist: {len(faces)} faces, {parts}")
            continue
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
                pool.submit(render_pdf, pdfs / d.doc_id, c, d.doc_id, pages_dir, d.frames)
                for d in docs
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
    """Write docs/audit.md from Peter's decisions on the committed sample. A recheck file
    beside the decisions (labels looked at again, on corrected pages) overrides them, by
    label."""
    from legible.data.audit import Label, read_decisions, report

    sample = [
        Label.model_validate({**x, "value": ""})
        for x in json.loads((MANIFESTS / "audit-sample.json").read_text(encoding="utf-8"))
    ]
    from legible.data.patches import patches_from, write_patches

    decided = read_decisions(decisions)
    recheck = decisions.with_name("recheck.json")
    rechecked = read_decisions(recheck) if recheck.exists() else []
    later = {d.label_id: d for d in rechecked}
    decided = [later.get(d.label_id, d) for d in decided]
    rows = report(sample, decided)
    fixes = patches_from(decided)
    write_patches(Path("legible/data/patches.json"), fixes)
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
    lines += [
        "",
        f"{len(rechecked)} labels were looked at again on 2026-10-16 (`docs/audit/recheck.json`), "
        "after their crops came out blank: the pages had been rendered in the PDF's orientation, "
        "not the benchmark's (docs/ocr.md). The recheck replaces the first decision.",
    ]
    lines += [
        "",
        f"{len(fixes)} labels marked wrong with the value the page shows are corrected by the",
        "loaders from `legible/data/patches.json`; each patched document names its patched fields.",
        "",
        "| Corpus | Document | Field | Corrected to |",
        "|---|---|---|---|",
    ]
    lines += [
        f"| {p.corpus} | {'(registration form)' if p.corpus == 'fara' else p.doc_id} | {p.key} | "
        f"{'(withheld)' if p.corpus == 'fara' and not p.key.endswith('date') else p.value} |"
        for p in fixes
    ]
    text = "\n".join(lines) + "\n"
    Path("docs/audit.md").write_text(text, encoding="utf-8", newline="\n")
    typer.echo(text)


@app.command("calibrate")
def calibrate_levels(
    out: Path = typer.Option(Path("docs/degradation.md")),
) -> None:
    """Write docs/degradation.md: what each level does to OCR on the NIST curve pages, from
    the OCR stored at every level."""
    from legible.calibrate import calibrate, table
    from legible.data import nist
    from legible.data.render import read_manifest

    wanted = part_docs("nist", "curve")
    entries = sorted(
        (e for e in read_manifest(manifest("nist")) if e.doc_id in wanted), key=lambda e: e.doc_id
    )
    zip_path, md5s = nist.fetch_sd2(data_root() / "raw" / "nist")
    truths = {
        d.doc_id: d.truth for d, _ in nist.read_sd2(zip_path, md5s, None) if d.doc_id in wanted
    }
    rows = calibrate(data_root(), entries, truths)
    from legible.arms.ocr_run import load

    version = load(data_root(), 0, entries[0].path).tesseract
    lines = [
        "# Degradation: what each level does to reading",
        "",
        "Written by `legible calibrate` from the OCR stored at every level; do not edit. "
        "The method is in `legible/calibrate.py`; the levels are `LEVELS` in `legible/degrade.py`.",
        "",
        f"{len(entries)} NIST SD2 pages (the curve pages, `manifests/nist-splits.json`), {version}, "
        "run on the measuring machine (docs/ocr.md). Each cell is the mean over pages with its "
        "95% bootstrap interval.",
        "",
        *table(rows),
        "",
    ]
    out.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    typer.echo("\n".join(lines))


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


ocr_app = typer.Typer(no_args_is_help=True, help="Tesseract over a corpus's pages.")
app.add_typer(ocr_app, name="ocr")


def part_docs(corpus: str, part: str) -> set[str]:
    """The documents of a split part, over every headline split file: VRDU's train, valid
    (dev) or test unions; CORD's own split; NIST's split by submission, where test is the 500
    pages every arm reads, and `nist_<face>` is one face's share."""
    from legible.data.render import read_manifest

    if corpus.startswith("nist"):
        from legible.data.nist import read_splits

        rows = read_splits(MANIFESTS / "nist-splits.json")
        face = corpus[len("nist_") :] if corpus != "nist" else None
        return {
            d
            for d, r in rows.items()
            if (face is None or r.face.lower() == face)
            and (r.arm_test if part == "test" else r.curve if part == "curve" else r.part == part)
        }
    if corpus == "cord":
        return {
            e.doc_id
            for e in read_manifest(MANIFESTS / "cord-pages.jsonl")
            if e.doc_id.startswith(part)
        }
    from legible.data.vrdu import headline_split_files, read_split

    raw = data_root() / "raw" / "vrdu"
    attr = {"train": "train", "dev": "valid", "test": "test"}[part]
    out: set[str] = set()
    for level in ("unseen", "mixed"):
        for p in headline_split_files(corpus, level):  # type: ignore[arg-type]
            out.update(getattr(read_split(corpus, raw / p), attr))  # type: ignore[arg-type]
    return out


@ocr_app.command("run")
def ocr_run(
    corpus: str = typer.Argument(..., help="fara, deepform or cord."),
    part: str = typer.Option("test", help="train, dev or test."),
    level: int = typer.Option(0, min=0, max=len(LEVELS) - 1),
    limit: int | None = typer.Option(None, help="At most this many documents, by id order."),
    workers: int | None = typer.Option(None),
) -> None:
    """OCR a split part's pages at a degradation level; resumes where it stopped."""
    from legible.arms.ocr_run import run
    from legible.data.render import read_manifest

    docs = sorted(part_docs(corpus, part))[:limit]
    wanted = set(docs)
    entries = [e for e in read_manifest(manifest(corpus)) if e.doc_id in wanted]
    pages, seconds = run(data_root(), entries, level, workers=workers)
    typer.echo(
        f"{corpus} {part} level {level}: {len(docs)} documents, {pages} pages read, {seconds:.0f} s"
    )


rules_app = typer.Typer(no_args_is_help=True, help="Arm E: OCR plus rules.")
app.add_typer(rules_app, name="rules")


@rules_app.command("learn-nist")
def rules_learn_nist() -> None:
    """Learn NIST's face templates and field zones from the training pages' stored OCR and
    answer files, and write legible/arms/nist_zones.json (committed)."""
    from legible.arms.ocr_run import load
    from legible.arms.zonal import FaceRules, learn_face, save
    from legible.data import nist
    from legible.data.render import read_manifest
    from legible.schema import Record

    train = part_docs("nist", "train")
    entries = {e.doc_id: e for e in read_manifest(manifest("nist")) if e.doc_id in train}
    zip_path, md5s = nist.fetch_sd2(data_root() / "raw" / "nist")
    by_face: dict[str, list[tuple[str, Record]]] = {}
    for d, _ in nist.read_sd2(zip_path, md5s, None):
        if d.doc_id in entries:
            by_face.setdefault(d.face, []).append((d.doc_id, d.truth))
    rules: dict[str, FaceRules] = {}
    for face, docs in sorted(by_face.items()):
        faces = ((load(data_root(), 0, entries[d].path), t) for d, t in docs)
        r = rules[face] = learn_face(face, faces)
        typer.echo(
            f"{face}: {len(docs)} pages, {len(r.template_words)} words, {len(r.zones)} zones"
        )
    save(rules)


@rules_app.command("run")
def rules_run(
    corpus: str = typer.Argument(..., help="fara, deepform, cord or nist."),
    part: str = typer.Option("dev", help="dev or test (NIST also curve). Test is run once."),
    level: int = typer.Option(0, min=0, max=len(LEVELS) - 1),
) -> None:
    """Answer every document of a part from its stored OCR, one run per split file (NIST:
    one run per part, with the zones learned from its training pages)."""
    from legible.arms.rules_run import rule_sets_for, run, run_nist
    from legible.data.render import read_manifest
    from legible.data.vrdu import headline_split_files, read_split

    pages: dict[str, list[PageEntry]] = {}
    for e in read_manifest(manifest(corpus)):
        pages.setdefault(e.doc_id, []).append(e)
    out_dir = data_root() / "runs" / "arm-e" / f"level{level}" / corpus
    if corpus == "nist":
        nist_docs = sorted(part_docs("nist", part))
        n = run_nist(data_root(), nist_docs, pages, level, out_dir / f"{part}.jsonl")
        typer.echo(f"nist {part} level {level}: {n} faces")
        return
    if corpus == "cord":
        docs = sorted(part_docs("cord", part))
        n = run(
            data_root(),
            corpus,
            docs,
            pages,
            rule_sets_for("cord", None),
            level,
            out_dir / f"{part}.jsonl",
        )
        typer.echo(f"cord {part}: {n} documents")
        return
    raw = data_root() / "raw" / "vrdu"
    attr = {"dev": "valid", "test": "test"}[part]
    for split_level in ("unseen", "mixed"):
        for p in headline_split_files(corpus, split_level):  # type: ignore[arg-type]
            split = read_split(corpus, raw / p)  # type: ignore[arg-type]
            docs = list(getattr(split, attr))
            out = out_dir / f"{Path(p).stem}-{part}.jsonl"
            n = run(data_root(), corpus, docs, pages, rule_sets_for(corpus, split), level, out)
            typer.echo(f"{Path(p).stem} {part}: {n} documents")


read_app = typer.Typer(
    no_args_is_help=True,
    help="Arms A and D: a frontier model reads the page images (a) or the OCR text (d).",
)
app.add_typer(read_app, name="read")

GATEWAY_CONFIG = Path("boundary.yaml")


def _route(name: str) -> tuple[str, str]:
    """(vendor, model) for a route in boundary.yaml, the one place models are named."""
    import yaml

    routes = yaml.safe_load(GATEWAY_CONFIG.read_text(encoding="utf-8"))["routes"]
    if name not in routes:
        raise typer.BadParameter(f"no route {name!r} in {GATEWAY_CONFIG}")
    return routes[name]["provider"], routes[name]["model"]


def _read_run(
    arm: str, corpus: str, part: str, level: int, route: str, prompt_version: int
) -> tuple[RunSpec, Prompt, list[str], Path]:
    from legible.arms.read_run import RunSpec, max_tokens_for, prompt_for, require_dev, run_dir

    if arm not in {"a", "d"}:
        raise typer.BadParameter("arm is a (page images) or d (OCR text)")
    if part not in {"dev", "test"}:
        raise typer.BadParameter("part is dev or test")
    vendor, model = _route(route)
    spec = RunSpec(
        arm=arm,
        corpus=corpus,
        part=part,
        level=level,
        route=route,
        vendor=vendor,
        model=model,
        prompt_version=prompt_version,
        max_tokens=max_tokens_for(corpus, vendor),  # type: ignore[arg-type]
    )
    prompt = prompt_for(corpus, prompt_version, spec.arm)
    require_dev(data_root(), spec, sorted(part_docs(corpus, "dev")), prompt)
    return spec, prompt, sorted(part_docs(corpus, part)), run_dir(data_root(), spec)


@read_app.command("submit")
def read_submit(
    corpus: str = typer.Argument(..., help="fara, deepform or cord."),
    arm: str = typer.Option(..., help="a (page images) or d (OCR text)."),
    part: str = typer.Option("dev", help="dev or test. Test needs a finished dev run first."),
    level: int = typer.Option(0, min=0, max=len(LEVELS) - 1),
    route: str = typer.Option("quality", help="A route in boundary.yaml."),
    prompt_version: int = typer.Option(1, min=1),
    limit: int | None = typer.Option(None, help="Dev only: at most this many documents."),
    sync: bool = typer.Option(False, help="One call per document instead of batches."),
) -> None:
    """Send every document of a part not yet read or submitted, through the gateway."""
    from boundary import Gateway

    from legible.arms.frontier import run_sync
    from legible.arms.read_run import open_run, requests_for, submit
    from legible.data.render import read_manifest

    spec, prompt, docs, path = _read_run(arm, corpus, part, level, route, prompt_version)
    if limit is not None:
        if part == "test":
            raise typer.BadParameter("a test run reads every test document, once")
        docs = docs[:limit]
    pages: dict[str, list[PageEntry]] = {}
    for e in read_manifest(manifest(corpus)):
        pages.setdefault(e.doc_id, []).append(e)
    run = open_run(path, spec, prompt)
    gateway = Gateway.from_config(GATEWAY_CONFIG, project="legible")
    if sync:
        have = set(run.reads()) | {d for ids in run.batches().values() for d in ids}
        requests = requests_for(
            data_root(), spec, prompt, [d for d in docs if d not in have], pages
        )
        n = run_sync(gateway, requests, run, purpose=spec.purpose, run_id=spec.run_id)
        typer.echo(f"{spec.run_id}: {n} documents read")
        return
    n, batches = submit(gateway, data_root(), spec, prompt, run, docs, pages)
    typer.echo(f"{spec.run_id}: {n} documents in {batches} new batches")


@read_app.command("collect")
def read_collect(
    corpus: str = typer.Argument(..., help="fara, deepform or cord."),
    arm: str = typer.Option(..., help="a or d."),
    part: str = typer.Option("dev"),
    level: int = typer.Option(0, min=0, max=len(LEVELS) - 1),
    route: str = typer.Option("quality"),
    prompt_version: int = typer.Option(1, min=1),
    wait: float = typer.Option(0.0, help="Seconds to wait for a batch still running."),
) -> None:
    """Collect every submitted batch that has finished; say what the run holds."""
    from boundary import BatchNotReady, Gateway

    from legible.arms.frontier import collect_batches
    from legible.arms.read_run import describe, open_run

    spec, prompt, _, path = _read_run(arm, corpus, part, level, route, prompt_version)
    run = open_run(path, spec, prompt)
    gateway = Gateway.from_config(GATEWAY_CONFIG, project="legible")
    try:
        added = collect_batches(gateway, run, wait_s=wait)
    except BatchNotReady as e:
        typer.echo(f"{spec.run_id}: a batch is still running ({e})")
        added = 0
    typer.echo(f"{spec.run_id}: {added} reads added; {json.dumps(describe(path))}")


def main() -> None:
    app()
