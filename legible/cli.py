"""legible: the command line. Commands are added as the stages they run are built."""

from __future__ import annotations

import json
import os
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

import typer
from PIL import Image

from legible import __version__
from legible.data.render import PageEntry
from legible.degrade import LEVELS, degrade, to_png

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from legible.arms.read_run import RunSpec
    from legible.bench.run import LoadRun
    from legible.prompt import Prompt
    from legible.report import Results, Row, Truth
    from legible.schema import CorpusSchema
    from legible.stats import Interval

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


@data_app.command("subsets")
def data_subsets() -> None:
    """Draw the ceiling, repeat and VRDU-curve test subsets into manifests/subsets.json."""
    from legible.data.render import read_manifest
    from legible.data.subsets import build, write
    from legible.data.vrdu import headline_split_files, read_split

    raw = data_root() / "raw" / "vrdu"
    pages: dict[str, int] = {}
    for c in ("fara", "deepform", "cord", "nist"):
        for e in read_manifest(manifest(c)):
            pages[e.doc_id] = pages.get(e.doc_id, 0) + 1
    tests: dict[str, list[str]] = {}
    for c in ("fara", "deepform"):
        files = [f for f in headline_split_files(c, "unseen") if f.endswith("SD_0.json")]  # type: ignore[arg-type]
        splits = [read_split(c, raw / f) for f in files]  # type: ignore[arg-type]
        tests[c] = sorted({d for sp in splits for d in sp.test})
    tests["cord"] = sorted(part_docs("cord", "test"))
    tests["nist"] = sorted(part_docs("nist", "test"))
    subsets = build(tests, pages)
    write(MANIFESTS / "subsets.json", subsets)
    for name, per in subsets.items():
        typer.echo(
            f"{name}: "
            + ", ".join(
                f"{c} {len(ds)} docs {sum(pages[d] for d in ds)} pages" for c, ds in per.items()
            )
        )


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


def _truths() -> dict[str, Truth]:
    """Every document's truth, by document id, across the four corpora."""
    from legible.data import nist
    from legible.data.cord import read_shard
    from legible.data.fetch import load_checksums
    from legible.data.vrdu import read_dataset
    from legible.report import Truth
    from legible.schema.corpora import SCHEMAS

    raw = data_root() / "raw"
    truth: dict[str, Truth] = {}
    for c in ("fara", "deepform"):
        for d in read_dataset(c, raw / "vrdu"):
            truth[d.doc_id] = Truth(SCHEMAS[c], d.truth, d.alternatives, d.text, d.pages)
    for shard in sorted(load_checksums("cord").files):
        for cd, _ in read_shard(raw / "cord" / shard, None):
            truth[cd.doc_id] = Truth(SCHEMAS["cord"], cd.truth, cd.alternatives, None, 1)
    zip_path, md5s = nist.fetch_sd2(raw / "nist")
    for nd, _ in nist.read_sd2(zip_path, md5s, None):
        truth[nd.doc_id] = Truth(SCHEMAS[nd.corpus], nd.truth, {}, None, 1)
    return truth


def _vrdu_ids(corpus: str, level: str, attr: str) -> list[str]:
    """A VRDU corpus's documents of one part (`valid` or `test`) over its seed-0 split files
    at a template level: FARA's three held-out templates pooled."""
    from legible.data.vrdu import headline_split_files, read_split

    raw = data_root() / "raw" / "vrdu"
    files = [f for f in headline_split_files(corpus, level) if f.endswith("SD_0.json")]  # type: ignore[arg-type]
    splits = [read_split(corpus, raw / f) for f in files]  # type: ignore[arg-type]
    return sorted({d for sp in splits for d in getattr(sp, attr)})


def _vrdu_rules(corpus: str, level: str) -> list[Path]:
    """Arm E's level-0 test runs of a VRDU corpus, one per seed-0 split file."""
    from legible.data.vrdu import headline_split_files

    files = [f for f in headline_split_files(corpus, level) if f.endswith("SD_0.json")]  # type: ignore[arg-type]
    return [
        data_root() / "runs" / "arm-e" / "level0" / corpus / f"{Path(f).stem}-test.jsonl"
        for f in files
    ]


def _results(truth: dict[str, Truth]) -> Results:
    """Every arm graded on the stored runs, for the README's tables and the demo site: the
    headline and template-gap tables, the degradation curves and the review rates."""
    from legible.report import (
        AGREEMENT_MISS,
        ARMS,
        TABLE_SETS,
        TOKEN_MISS,
        Curve,
        Results,
        ReviewTable,
        Table,
        agreed_grades,
        answers_for,
        arms_in,
        row,
        token_grades,
    )
    from legible.review import review
    from legible.schema.corpora import NIST_SCHEMAS
    from legible.train.recipe import chosen

    root = data_root()
    e_dir = root / "runs" / "arm-e"

    def vrdu_rows(corpus: str, level: str) -> list[Row]:
        docs = _vrdu_ids(corpus, level, "test")
        rules = _vrdu_rules(corpus, level)
        return [
            row(
                a.label,
                docs,
                truth,
                answers_for(root, a, [corpus], "test", 0, rules, f"{corpus}-{level}"),
            )
            for a in arms_in(f"{corpus}-{level}")
        ]

    nist_faces = sorted(NIST_SCHEMAS)
    nist_test = sorted(part_docs("nist", "test"))
    cord_test = sorted(part_docs("cord", "test"))
    tables = [
        Table(
            "fara-unseen",
            "FARA registration forms, templates never seen in training (headline)",
            vrdu_rows("fara", "unseen"),
        ),
        Table(
            "deepform-unseen",
            "DeepForm ad-buy forms, templates never seen in training (headline)",
            vrdu_rows("deepform", "unseen"),
        ),
        Table(
            "cord",
            "CORD receipts, test set",
            [
                row(
                    a.label,
                    cord_test,
                    truth,
                    answers_for(
                        root,
                        a,
                        ["cord"],
                        "test",
                        0,
                        [e_dir / "level0" / "cord" / "test.jsonl"],
                        "cord",
                    ),
                )
                for a in arms_in("cord")
            ],
        ),
        Table(
            "nist",
            "NIST tax forms, 500 test faces",
            [
                row(
                    a.label,
                    nist_test,
                    truth,
                    answers_for(
                        root,
                        a,
                        nist_faces,
                        "test",
                        0,
                        [e_dir / "level0" / "nist" / "test.jsonl"],
                        "nist",
                    ),
                )
                for a in arms_in("nist")
            ],
        ),
        Table(
            "fara-mixed",
            "FARA, templates seen in training (the gap beside the headline)",
            vrdu_rows("fara", "mixed"),
        ),
        Table(
            "deepform-mixed",
            "DeepForm, templates seen in training (the gap beside the headline)",
            vrdu_rows("deepform", "mixed"),
        ),
    ]
    curve_docs = sorted(part_docs("nist", "curve"))
    cells: dict[str, dict[int, Row]] = {}
    for a in arms_in("nist"):
        cells[a.label] = {}
        for lv in range(5):
            part = "test" if lv == 0 else "curve"
            rules = [e_dir / f"level{lv}" / "nist" / f"{part}.jsonl"]
            found = answers_for(root, a, nist_faces, part, lv, rules, "nist")
            if found is not None:
                cells[a.label][lv] = row(a.label, curve_docs, truth, found)
    curves = [
        Curve(
            "nist",
            "NIST, the 300 curve pages at each degradation level",
            "(fields correct; what each level does to OCR is in "
            "[docs/degradation.md](docs/degradation.md))",
            (0, 1, 2, 3, 4),
            len(curve_docs),
            cells,
        )
    ]
    for c, name in (("fara", "FARA"), ("deepform", "DeepForm")):
        sub = sorted(part_docs(c, "vrdu_curve"))
        vcells: dict[str, dict[int, Row]] = {}
        for a in arms_in(f"{c}-curve"):
            vcells[a.label] = {}
            for lv in (0, 2, 4):
                # Level 0 is the subset's share of the test reads; 2 and 4 the subset itself.
                part = "test" if lv == 0 else "vrdu_curve"
                rules = (
                    _vrdu_rules(c, "unseen")
                    if lv == 0
                    else [
                        f.parents[2] / f"level{lv}" / c / f.name.replace("-test", "-vrdu_curve")
                        for f in _vrdu_rules(c, "unseen")
                    ]
                )
                found = answers_for(root, a, [c], part, lv, rules, f"{c}-unseen")
                if found is not None:
                    vcells[a.label][lv] = row(a.label, sub, truth, found)
        curves.append(
            Curve(
                c,
                f"{name}, the {len(sub)} unseen-template test documents of the VRDU curve "
                "subset at levels 0, 2 and 4",
                "(fields correct; real scans beside the NIST curve)",
                (0, 2, 4),
                len(sub),
                vcells,
            )
        )

    sonnet_a, sonnet_d = ARMS[0], ARMS[4]

    def review_for(corpora: list[str], dev: list[str], test: list[str]) -> object:
        parts = {}
        for part, ids in (("dev", dev), ("test", test)):
            va = answers_for(root, sonnet_a, corpora, part, 0, [])
            vd = answers_for(root, sonnet_d, corpora, part, 0, [])
            if va is None or vd is None:
                return None
            parts[part] = agreed_grades(ids, truth, va, vd)
        return review(parts["dev"], parts["test"])

    reviews = [
        ReviewTable(
            "Review at 99%: Sonnet 5.5 on the image, each field checked against Sonnet 5.5 on "
            "the OCR text.",
            "A field is accepted when the two reads agree; the threshold is chosen on dev and "
            "applied once to test (legible/review.py, legible/agreement.py).",
            [
                (
                    "FARA, unseen templates",
                    review_for(
                        ["fara"],
                        _vrdu_ids("fara", "unseen", "valid"),
                        _vrdu_ids("fara", "unseen", "test"),
                    ),
                ),
                (
                    "DeepForm, unseen templates",
                    review_for(
                        ["deepform"],
                        _vrdu_ids("deepform", "unseen", "valid"),
                        _vrdu_ids("deepform", "unseen", "test"),
                    ),
                ),
                ("CORD", review_for(["cord"], sorted(part_docs("cord", "dev")), cord_test)),
                ("NIST", review_for(nist_faces, sorted(part_docs("nist", "dev")), nist_test)),
            ],
            AGREEMENT_MISS,
        )
    ]

    def token_review(
        size: Literal["2b", "4b"], table: str, corpora: list[str], dev: list[str], test: list[str]
    ) -> object:
        parts = {}
        for part, ids in (("dev", dev), ("test", test)):
            dirs = [
                root
                / "runs"
                / "arm-b"
                / f"{chosen(size, ds).run_id}@logprobs"
                / "p1"
                / "level0"
                / c
                / part
                for ds in TABLE_SETS[table]
                for c in corpora
            ]
            graded = token_grades(ids, truth, dirs)
            if graded is None:
                return None
            parts[part] = graded
        return review(parts["dev"], parts["test"])

    sizes: tuple[tuple[Literal["2b", "4b"], str], ...] = (("2b", "E2B"), ("4b", "E4B"))
    for size, name in sizes:
        reviews.append(
            ReviewTable(
                f"Review at 99%: Gemma 4 {name} fine-tuned (seed 0), each field's confidence "
                "the lowest probability among the tokens of its value.",
                "Read a second time with log-probabilities for this table (PLAN.md 2.6); the "
                "threshold is chosen on that dev read and applied once to its test read "
                "(legible/tokenconf.py).",
                [
                    (
                        "FARA, unseen templates",
                        token_review(
                            size,
                            "fara-unseen",
                            ["fara"],
                            _vrdu_ids("fara", "unseen", "valid"),
                            _vrdu_ids("fara", "unseen", "test"),
                        ),
                    ),
                    (
                        "DeepForm, unseen templates",
                        token_review(
                            size,
                            "deepform-unseen",
                            ["deepform"],
                            _vrdu_ids("deepform", "unseen", "valid"),
                            _vrdu_ids("deepform", "unseen", "test"),
                        ),
                    ),
                    (
                        "CORD",
                        token_review(
                            size, "cord", ["cord"], sorted(part_docs("cord", "dev")), cord_test
                        ),
                    ),
                    (
                        "NIST",
                        token_review(
                            size, "nist", nist_faces, sorted(part_docs("nist", "dev")), nist_test
                        ),
                    ),
                ],
                TOKEN_MISS,
            )
        )
    return Results(tables=tables, curves=curves, reviews=reviews)


@app.command("report")
def report_command(readme: Path = typer.Option(Path("README.md"))) -> None:
    """Grade every arm's stored test reads and write the README's result tables."""
    from legible.report import (
        ARMS,
        PRICE_LIST_DATE,
        answers_for,
        curve,
        gate_table,
        read_gate,
        review_table,
        splice,
        table,
        verifier_cell,
    )
    from legible.schema.corpora import NIST_SCHEMAS

    root = data_root()
    truth = _truths()
    results = _results(truth)
    body = [
        "Test sets, read once per arm, level 0 unless stated. Field accuracy is VRDU's own "
        "matchers, one grader for every arm; intervals are 95% bootstrap over documents. "
        f"Frontier cost is the gateway ledger's at the {PRICE_LIST_DATE} price list, batch "
        "rate; OCR is costed at US$0.03 per vCPU-hour (RunPod, 2026-10-17). Written by "
        "`legible report`; do not edit.",
        "",
    ]
    for t in results.tables:
        body += table(t.title, t.rows)
    for cv in results.curves:
        body += [f"**{cv.title}** {cv.note}", "", *curve(cv.levels, cv.cells)]
    e_dir = root / "runs" / "arm-e"
    nist_faces = sorted(NIST_SCHEMAS)
    nist_test = sorted(part_docs("nist", "test"))
    fara_test = _vrdu_ids("fara", "unseen", "test")
    fara_rules = _vrdu_rules("fara", "unseen")
    nist_rules = [e_dir / "level0" / "nist" / "test.jsonl"]
    body += [
        "**The verifier on test: the share of wrong fields its rules flag, over every field and "
        "over the fields a rule reads, and the share of right fields flagged** "
        "(legible/verify_rules.py; each rule kept only where the training truth obeys it on 99% "
        "of documents, docs/verify-rules.md). FARA has one rule, a registration number's "
        "digits; NIST the 1988 forms' sums. No rule held for DeepForm's dates or CORD's "
        "arithmetic, so neither has a verifier.",
        "",
        "| Arm | FARA, unseen templates | NIST |",
        "|---|---|---|",
    ]
    for a in ARMS:
        fa = answers_for(root, a, ["fara"], "test", 0, fara_rules, "fara-unseen")
        na = answers_for(root, a, nist_faces, "test", 0, nist_rules, "nist")
        body.append(
            f"| {a.label} | {verifier_cell(fara_test, truth, fa)} "
            f"| {verifier_cell(nist_test, truth, na)} |"
        )
    body.append("")
    gate_dir = Path("gate-runs")
    order = [f"legible-{c}-{lv}" for c, levels in GATE_RUNS.items() for lv in levels]
    decisions = sorted(
        (read_gate(p) for p in gate_dir.glob("*/decision.txt")),
        key=lambda r: (
            next((i for i, o in enumerate(order) if r.name.startswith(o + "-")), 99),
            r.name.endswith("anchor"),
        ),
    )
    body += [
        "**Non-inferiority through the 03 gate** (docs/gate.md): the fine-tune with the better "
        "dev accuracy against the frontier vision model with the best, and against the cost "
        "anchor, one suite per field, one outcome per document, a 3-point margin, Holm's "
        "adjustment across the decided fields. A field the test set holds too few documents of "
        "to resolve 3 points is under-powered and not decided.",
        "",
        *(
            gate_table(
                decisions,
                {
                    "legible-fara-unseen": "FARA, unseen templates",
                    "legible-fara-mixed": "FARA, mixed templates",
                    "legible-deepform-unseen": "DeepForm, unseen templates",
                    "legible-deepform-mixed": "DeepForm, mixed templates",
                    "legible-cord-test": "CORD",
                    "legible-nist-test": "NIST",
                },
            )
            if decisions
            else ["Not yet run.", ""]
        ),
    ]
    for rv in results.reviews:
        body += [f"**{rv.title}** {rv.note}", "", *review_table(rv.rows, rv.miss)]
    body += _subsets_section(root, truth)
    body += _ablations_section(_ablations(root, truth))
    headline_keys = ("fara-unseen", "deepform-unseen", "cord", "nist")
    body += _serving_section(
        root, {t.key.split("-")[0]: t.rows for t in results.tables if t.key in headline_keys}
    )
    body += [
        "Arms B and C read through vLLM on an RTX 3090 at temperature 0, unconstrained (held "
        "to the schema's grammar, the fine-tunes left their trained format: docs/training.md), "
        "and are costed at the GPU's US$0.50 an hour on RunPod (2026-10-18) over the measured "
        "wall time of each read pass. "
        "B's row is seed 0, the model trained for that table's split; seeds 1 and 2 are "
        "the training variance. Latency is the fine-tunes' alone: the frontier models were "
        "read in batches, whose only latency is the batch's (docs/serving.md).",
    ]
    builds = [
        json.loads(p.read_text("utf-8")).get("model", {}).get("trainingHours")
        for p in (root / "docintel" / "meta").glob("*-build.json")
    ]
    hours = sum(h for h in builds if isinstance(h, (int, float)))
    if builds:
        body[-1] += (
            f" Arm F is costed per page at Azure's prices read 2026-10-24, through the gateway; "
            f"its {len(builds)} custom models took {hours:.2f} training hours, US$"
            f"{max(0.0, hours - 10) * 3:.2f} past the ten free a month at US$3 an hour, which, "
            "like arm B's training, is not in the cost per page (docs/docintel.md)."
        )
    text = readme.read_text(encoding="utf-8")
    readme.write_text(splice(text, body), encoding="utf-8", newline="\n")
    typer.echo("\n".join(body))


@dataclass(frozen=True)
class _Subset:
    """One corpus's row of the ceiling or the noise floor: the documents, the two reads'
    accuracy and cost, and for the noise floor the share of fields whose outcome changed."""

    corpus: str
    documents: int
    missing: int
    first: Row
    second: Row
    changed: Interval | None = None


def _subsets(root: Path, truth: Mapping[str, Truth]) -> tuple[list[_Subset], list[_Subset]]:
    """The ceiling (Opus 5.5 first, Sonnet 5.5 second, on the ceiling subset) and the noise
    floor (Sonnet 5.5's first and second reads of the repeat subset), per corpus."""
    from legible.grade import grade_document
    from legible.report import ARMS, Arm, answers_for, row
    from legible.schema.corpora import NIST_SCHEMAS
    from legible.stats import ratio_ci

    sonnet = ARMS[0]
    opus = Arm("A, Claude Opus 5.5 on the image", "a", "ceiling")
    nist_faces = sorted(NIST_SCHEMAS)
    corpora = (("fara", "FARA", ["fara"]), ("deepform", "DeepForm", ["deepform"]),
               ("cord", "CORD", ["cord"]), ("nist", "NIST", nist_faces))  # fmt: skip
    ceiling: list[_Subset] = []
    for family, name, cs in corpora:
        docs = sorted(part_docs(family, "ceiling"))
        o = answers_for(root, opus, cs, "ceiling", 0, [])
        q = answers_for(root, sonnet, cs, "test", 0, [])
        ro, rq = row(opus.label, docs, truth, o), row(sonnet.label, docs, truth, q)
        ceiling.append(_Subset(name, len(docs), ro.missing, ro, rq))
    noise: list[_Subset] = []
    for family, name, cs in corpora:
        docs = sorted(part_docs(family, "repeat"))
        first = answers_for(root, sonnet, cs, "test", 0, [])
        second = answers_for(root, sonnet, cs, "repeat", 0, [])
        r1, r2 = row(sonnet.label, docs, truth, first), row(sonnet.label, docs, truth, second)
        changed: list[float] = []
        fields: list[float] = []
        for d in docs:
            if first is None or second is None or d not in first.outputs or d not in second.outputs:
                continue
            t = truth[d]
            g1, g2 = (
                grade_document(t.schema, d, t.record, a.outputs[d], page_text=t.text,
                               alternatives=t.alternatives)
                for a in (first, second)
            )  # fmt: skip
            o1 = {(o.path, o.index): o.correct for o in g1.outcomes}
            o2 = {(o.path, o.index): o.correct for o in g2.outcomes}
            keys = set(o1) | set(o2)
            changed.append(float(sum(o1.get(k) != o2.get(k) for k in keys)))
            fields.append(float(len(keys)))
        flip = ratio_ci(changed, fields) if fields else None
        noise.append(_Subset(name, len(fields), 0, r1, r2, flip))
    return ceiling, noise


def _subsets_section(root: Path, truth: Mapping[str, Truth]) -> list[str]:
    """The ceiling and the noise floor (legible/data/subsets.py): Opus 5.5 beside Sonnet 5.5
    on the ceiling subset, and Sonnet 5.5's second read of the repeat subset beside its first,
    with the share of fields whose outcome changed between them."""
    from legible.report import pct, usd

    ceiling, noise = _subsets(root, truth)
    out = [
        "**The ceiling: Claude Opus 5.5, the dearest Anthropic model, on a subset of the "
        "headline test documents, beside Sonnet 5.5's reads of the same documents** "
        "(legible/data/subsets.py; batch rate; fields correct with 95% CI over documents).",
        "",
        "| Corpus | Documents | Opus 5.5 | Sonnet 5.5 | Opus cost per 1,000 pages | Sonnet cost |",
        "|---|---:|---|---|---|---|",
    ]
    for c in ceiling:
        have = c.documents - c.missing
        n = f"{have}" + (f" of {c.documents}" if c.missing else "")
        out.append(
            f"| {c.corpus} | {n} | {pct(c.first.accuracy)} | {pct(c.second.accuracy)} "
            f"| {usd(c.first.per_thousand)} | {usd(c.second.per_thousand)} |"
        )
    out += [
        "",
        "**The noise floor: Sonnet 5.5 reading the repeat subset a second time**, the same "
        "request at the vendor's default sampling, days after the first. A difference between "
        "two arms smaller than the share of fields one arm changes on itself is not a "
        "difference.",
        "",
        "| Corpus | Documents | First read | Second read | Fields whose outcome changed |",
        "|---|---:|---|---|---|",
    ]
    for c in noise:
        flip = pct(c.changed) if c.changed is not None else "not yet measured"
        out.append(
            f"| {c.corpus} | {c.documents} | {pct(c.first.accuracy)} | {pct(c.second.accuracy)} "
            f"| {flip} |"
        )
    return [*out, ""]


#: The corpus a load-tested fine-tune's run id names, and how the tables call it.
_BENCH_CORPORA = {
    "fara": "FARA",
    "deepform": "DeepForm",
    "cord": "CORD",
    "nist": "NIST",
}


#: Where an ablation is read: name, documents, corpora, part, level and table.
_Where = tuple[str, list[str], list[str], str, int, str]


@dataclass(frozen=True)
class _AblationSet:
    """One set of documents an ablation is read on: the recipe it changes first, then each
    change with its paired difference from it."""

    name: str
    documents: int
    rows: list[Row]
    deltas: list[Interval | None]


@dataclass(frozen=True)
class _Ablation:
    key: str
    title: str
    columns: list[str]
    sets: list[_AblationSet]


def _ablations(root: Path, truth: Mapping[str, Truth]) -> list[_Ablation]:
    """The three ablations (legible/train/ablate.py) on the documents each answers about,
    every change against the seed-0 E2B whose recipe it changes."""
    from legible.report import ARMS, Arm, answers_for, delta, row
    from legible.schema.corpora import NIST_SCHEMAS
    from legible.train.ablate import MULTI

    e2b = next(a for a in ARMS if a.arm == "b" and a.size == "2b")
    faces = sorted(NIST_SCHEMAS)
    fara_u, deep_u = _vrdu_ids("fara", "unseen", "test"), _vrdu_ids("deepform", "unseen", "test")
    cord = sorted(part_docs("cord", "test"))
    nist = sorted(part_docs("nist", "test"))
    nist_curve = sorted(part_docs("nist", "curve"))
    tokens: list[_Where] = [
        ("FARA, unseen templates", fara_u, ["fara"], "test", 0, "fara-unseen"),
        ("DeepForm, unseen templates", deep_u, ["deepform"], "test", 0, "deepform-unseen"),
        ("CORD", cord, ["cord"], "test", 0, "cord"),
        ("NIST", nist, faces, "test", 0, "nist"),
        *((f"NIST curve, level {lv}", nist_curve, faces, "curve", lv, "nist") for lv in (2, 3, 4)),
        *(
            (
                f"{name}, VRDU curve subset, level 4",
                sorted(part_docs(c, "vrdu_curve")),
                [c],
                "vrdu_curve",
                4,
                f"{c}-unseen",
            )
            for c, name in (("fara", "FARA"), ("deepform", "DeepForm"))
        ),
    ]
    clean: list[_Where] = [
        ("CORD", cord, ["cord"], "test", 0, "cord"),
        ("NIST", nist, faces, "test", 0, "nist"),
    ]
    multi: list[_Where] = [
        (
            "FARA, mixed templates",
            _vrdu_ids("fara", "mixed", "test"),
            ["fara"],
            "test",
            0,
            "fara-mixed",
        ),
        (
            "DeepForm, mixed templates",
            _vrdu_ids("deepform", "mixed", "test"),
            ["deepform"],
            "test",
            0,
            "deepform-mixed",
        ),
        *clean,
    ]

    def variant(label: str, **kw: Any) -> Arm:
        changes = tuple(kw.pop("changes", {}).items())
        return Arm(label, "b", None, size="2b", changes=changes, **kw)

    specs = [
        (
            "visual-tokens",
            "Visual tokens: E2B at 560 a page against the headline's 1,120",
            [variant("E2B, 560 visual tokens", changes={"visual_tokens": 560})],
            tokens,
            "E2B, 1,120 visual tokens",
        ),
        (
            "volume",
            "Data volume: E2B on half and a quarter of the training documents",
            [variant(f"E2B, {n} documents", changes={"volume": n}) for n in (400, 200)],
            clean,
            "E2B, 800 documents",
        ),
        (
            "multi-corpus",
            "One model for every corpus against one per corpus, E2B",
            [variant("E2B, one model for every corpus", dataset=MULTI)],
            multi,
            "E2B, one model per corpus",
        ),
    ]
    out: list[_Ablation] = []
    for key, title, variants, wheres, ref_label in specs:
        sets: list[_AblationSet] = []
        for name, docs, cs, part, lv, tbl in wheres:
            ref = answers_for(root, e2b, cs, part, lv, [], tbl)
            rows = [row(ref_label, docs, truth, ref)]
            deltas: list[Interval | None] = [None]
            for v in variants:
                got = answers_for(root, v, cs, part, lv, [], tbl)
                rows.append(row(v.label, docs, truth, got))
                deltas.append(delta(docs, truth, got, ref))
            sets.append(_AblationSet(name, len(docs), rows, deltas))
        out.append(_Ablation(key, title, [ref_label, *(v.label for v in variants)], sets))
    return out


def _ablations_section(ablations: Sequence[_Ablation]) -> list[str]:
    """The ablation tables: fields correct for the recipe and each change, the change's paired
    difference with its interval, and the cost a page where the change is about cost."""
    from legible.report import pct, usd

    def signed(i: Interval | None) -> str:
        if i is None:
            return ""
        return f"{100 * i.point:+.1f} ({100 * i.low:+.1f} to {100 * i.high:+.1f})"

    out = [
        "**The ablations** (legible/train/ablate.py, PLAN.md 2.3): each change to the recipe "
        "trained on E2B at seed 0 and read like the headline models, against the seed-0 E2B "
        "it changes; the difference is paired over the documents both read, in points of "
        "fields correct, with its 95% interval.",
        "",
    ]
    for a in ablations:
        head = ["Documents", a.columns[0]]
        for c in a.columns[1:]:
            head += [c, "Difference"]
        costs = a.key == "visual-tokens"
        if costs:
            head += [f"Cost per 1,000 pages, {c.split(', ')[-1]}" for c in a.columns]
        out += [
            f"*{a.title}*",
            "",
            "| Set | " + " | ".join(head) + " |",
            "|---|---:|" + "---|" * (len(head) - 1),
        ]
        for s in a.sets:
            cells = [str(s.documents), pct(s.rows[0].accuracy)]
            for r, d in zip(s.rows[1:], s.deltas[1:], strict=True):
                cells += [pct(r.accuracy), signed(d)]
            if costs:
                cells += [usd(r.per_thousand) for r in s.rows]
            out.append(f"| {s.name} | " + " | ".join(cells) + " |")
        out.append("")
    return out


def _serving_section(root: Path, headline: Mapping[str, Sequence[Row]]) -> list[str]:
    """The load test's latency table and, per corpus, the break-even of the fine-tune the gate
    compared (the better on dev) against each frontier vision model (legible/bench/tables.py)."""
    from legible.bench.run import read as read_load
    from legible.bench.tables import breakeven_table, latency_table
    from legible.report import ARMS

    runs: dict[str, LoadRun] = {}
    for p in sorted((root / "bench").glob("*/bench.json")):
        runs[p.parent.name] = read_load(p.parent)
    if not runs:
        return ["**Latency and break-even**: not yet measured.", ""]

    def corpus_of(model: str) -> str:
        return model.split("-")[1]

    def label(model: str) -> str:
        size = "E2B" if model.startswith("2b") else "E4B"
        extra = " (amendment template)" if corpus_of(model) == "fara" else ""
        return f"{size}, {_BENCH_CORPORA[corpus_of(model)]}{extra}"

    ordered = sorted(runs, key=lambda m: (list(_BENCH_CORPORA).index(corpus_of(m)), m))
    any_run = runs[ordered[0]]
    out = [
        "**Latency and throughput of the fine-tunes**, one served at a time on one "
        f"{any_run.price.gpu} (US${any_run.price.usd_per_hour:.2f} an hour, "
        f"{any_run.price.provider}, {any_run.price.checked.isoformat()}), read through the "
        "gateway by 06's closed-loop client on the model's own test documents at level 0, the "
        "accuracy runs' requests cycled in order (docs/serving.md). A read is one document, "
        "every page of it; latency is per read, intervals are 95% bootstrap over reads, and "
        "the first 30 seconds of each level are discarded. The throughput interval resamples "
        "reads with the window fixed, as 06's does, so it has no width where every read is "
        "one page and none failed.",
        "",
        *latency_table([(label(m), runs[m]) for m in ordered]),
    ]
    frontier = [a for a in ARMS if a.arm in {"a", "f"}]
    gate_sizes = {
        p.name.split("-")[1]: p.name.split("-")[3]
        for p in Path("gate-runs").glob("legible-*-vs-best")
        if p.name.split("-")[2] in {"unseen", "test"}
    }
    for corpus, name in _BENCH_CORPORA.items():
        size = gate_sizes.get(corpus)
        model = next(
            (m for m in ordered if corpus_of(m) == corpus and m.startswith(size or "")), None
        )
        if model is None or size is None:
            continue
        rows = {r.label: r for r in headline.get(corpus, [])}
        api = [
            (
                a.label.removeprefix("A, ").removeprefix("F, ").removesuffix(" on the image"),
                r.per_thousand.point / 1000,
            )
            for a in frontier
            if (r := rows.get(a.label)) is not None and r.per_thousand is not None
        ]
        out += [
            f"**Break-even, {name}: pages a month at which renting the card for the {label(model)} "
            "fine-tune costs no more than paying each frontier model, or Azure Document Intelligence, by the page**, over the "
            "share of the month the card is kept busy (10% to 90%). 06's arithmetic (legible/"
            "bench/breakeven.py): whole cards rented all month, each frontier model at its "
            "headline test cost from the ledger. Below the utilisation given it never breaks "
            "even; above it the volume holds while one card carries it. It says nothing "
            "about accuracy, which the tables above do.",
            "",
            *breakeven_table(runs[model], api),
        ]
    return out


@app.command("site")
def site_command(
    out: Path = typer.Option(Path("site/out"), help="Where the site is written."),
    serve: bool = typer.Option(
        False, "--serve", help="Serve the built site with its host's headers; build nothing."
    ),
    port: int = typer.Option(8016, help="The port --serve listens on."),
    data_only: bool = typer.Option(
        False,
        "--data-only",
        help="Rewrite the site's files and its results and story into a built site, keeping "
        "its pages: for working on the front page without re-drawing every page.",
    ),
) -> None:
    """Write the demo site (PLAN.md 2.8, docs/site.md): the front page's findings and charts,
    from the runs `legible report` reads, and a handful of NIST, CORD and DeepForm test pages
    with each arm's graded reads drawn on them at each degradation level. FARA is in the
    charts only."""
    import datetime as dt

    from legible.arms.ocr_run import load
    from legible.arms.zonal import load_rules
    from legible.data.cord import read_shard
    from legible.data.fetch import load_checksums
    from legible.data.render import read_manifest
    from legible.data.vrdu import read_dataset
    from legible.report import ARMS, answers_for
    from legible.schema.corpora import NIST_SCHEMAS
    from legible.site import build

    if serve:
        build.serve(out, port)
        return
    root, raw = data_root(), data_root() / "raw"
    e_dir = root / "runs" / "arm-e"
    truth = _truths()
    results = _results(truth)
    if data_only:
        if not (out / "data" / "index.json").exists():
            raise typer.BadParameter(f"{out} has no pages yet; run legible site first")
        build.copy_assets(out)
        build.dump(out / "data" / "results.json", build.results_json(results))
        build.dump(out / "data" / "story.json", _story(root, truth))
        build.check_output(out)
        typer.echo(f"{out}: results and story rewritten, {build.size_of(out) / 1e6:.1f} MB")
        return
    if out.exists():
        import shutil

        shutil.rmtree(out)
    build.copy_assets(out)

    nist_faces = sorted(NIST_SCHEMAS)
    deepform_rules = _vrdu_rules("deepform", "unseen")
    # Per corpus: the pages, the levels they are shown at, and each level's reads (corpora
    # read, split part, arm E's runs, the report's table key), as the report's rows read them.
    plan: dict[
        str, tuple[list[str], tuple[int, ...], dict[int, tuple[list[str], str, list[Path], str]]]
    ] = {
        "nist": (
            build.choose(part_docs("nist", "curve")),
            (0, 1, 2, 3, 4),
            {
                lv: (
                    nist_faces,
                    "test" if lv == 0 else "curve",
                    [e_dir / f"level{lv}" / "nist" / f"{'test' if lv == 0 else 'curve'}.jsonl"],
                    "nist",
                )
                for lv in range(5)
            },
        ),
        "cord": (
            build.choose(part_docs("cord", "test")),
            (0,),
            {0: (["cord"], "test", [e_dir / "level0" / "cord" / "test.jsonl"], "cord")},
        ),
        "deepform": (
            build.choose(
                part_docs("deepform", "vrdu_curve") & set(_vrdu_ids("deepform", "unseen", "test"))
            ),
            (0, 2, 4),
            {
                lv: (
                    ["deepform"],
                    "test" if lv == 0 else "vrdu_curve",
                    deepform_rules
                    if lv == 0
                    else [
                        f.parents[2]
                        / f"level{lv}"
                        / "deepform"
                        / f.name.replace("-test", "-vrdu_curve")
                        for f in deepform_rules
                    ],
                    "deepform-unseen",
                )
                for lv in (0, 2, 4)
            },
        ),
    }
    wanted = {d for docs, _, _ in plan.values() for d in docs}
    boxes: dict[str, dict[str, build.Box]] = {}
    for d in read_dataset("deepform", raw / "vrdu"):
        if d.doc_id in wanted:
            boxes[d.doc_id] = dict(d.boxes)
    for shard in sorted(load_checksums("cord").files):
        for cd, _ in read_shard(raw / "cord" / shard, None):
            if cd.doc_id in wanted:
                boxes[cd.doc_id] = dict(cd.boxes)
    rules = load_rules()
    by_face = {k.lower(): v for k, v in rules.items()}

    index: dict[str, list[dict[str, object]]] = {}
    for corpus, (docs, levels, how) in plan.items():
        entries: dict[str, list[PageEntry]] = {}
        for e in read_manifest(manifest(corpus)):
            if e.doc_id in docs:
                entries.setdefault(e.doc_id, []).append(e)
        reads: dict[int, dict[str, dict[str, object] | None]] = {}
        for lv in levels:
            corpora, part, rules_files, table_key = how[lv]
            reads[lv] = {}
            for a in ARMS:
                found = answers_for(root, a, corpora, part, lv, rules_files, table_key)
                reads[lv][a.label] = (
                    {d: found.outputs[d] for d in docs if d in found.outputs} if found else None
                )
        index[corpus] = []
        for doc in docs:
            pages = sorted(entries[doc], key=lambda e: e.page)
            if corpus == "nist":
                face = truth[doc].schema.corpus[len("nist_") :]
                boxes[doc] = build.nist_boxes(load(root, 0, pages[0].path), by_face[face])
            images = build.write_images(root, pages, levels, out)
            record = build.page_record(
                corpus=corpus,
                doc_id=doc,
                entries=pages,
                truth=truth[doc],
                boxes=boxes.get(doc, {}),
                levels=levels,
                reads=reads,
                images=images,
            )
            build.dump(out / "data" / "pages" / f"{record['id']}.json", record)
            index[corpus].append({"id": record["id"], "doc": doc, "pages": len(pages)})
            typer.echo(f"{corpus} {doc}: {len(pages)} pages, levels {list(levels)}")
    build.dump(
        out / "data" / "index.json",
        {
            "built": dt.date.today().isoformat(),
            "arms": [{"label": a.label, "arm": a.arm} for a in ARMS],
            "pages": index,
        },
    )
    build.dump(out / "data" / "results.json", build.results_json(results))
    build.dump(out / "data" / "story.json", _story(root, truth))
    build.check_output(out)
    typer.echo(f"{out}: {build.size_of(out) / 1e6:.1f} MB")


#: Where `legible site` and `legible cards` find the headline adapters' training records,
#: under the data root: `models/<run id>/run.json`, copied from beside each adapter on the
#: volume (docs/site.md).
TRAINING_RECORDS = Path("models")


def _story(root: Path, truth: Mapping[str, Truth]) -> dict[str, object]:
    """What the front page tells around the tables (legible/site/build.py): the load test, the
    training records, the gate, the ceiling and noise floor, arm F's training and the pages
    read in all."""
    from legible.bench.run import read as read_load
    from legible.data.render import read_manifest
    from legible.report import DOCINTEL_PRICE_DATE, PRICE_LIST_DATE, SERVE_PRICE, read_gate
    from legible.site import build

    runs = {
        p.parent.name: read_load(p.parent) for p in sorted((root / "bench").glob("*/bench.json"))
    }
    gated = {
        p.name.split("-")[1]: p.name.split("-")[3]
        for p in Path("gate-runs").glob("legible-*-vs-best")
        if p.name.split("-")[2] in {"unseen", "test"}
    }
    records = [
        json.loads(p.read_text(encoding="utf-8"))
        for p in sorted((root / TRAINING_RECORDS).glob("*/run.json"))
    ]
    decisions = [read_gate(p) for p in sorted(Path("gate-runs").glob("*/decision.txt"))]
    ceiling, noise = _subsets(root, truth)
    pages: dict[tuple[str, str], int] = {}
    for corpus in ("cord", "deepform", "fara", "nist"):
        for e in read_manifest(manifest(corpus)):
            pages[(corpus, e.doc_id)] = pages.get((corpus, e.doc_id), 0) + 1
    builds = [
        json.loads(p.read_text("utf-8")).get("model", {}).get("trainingHours")
        for p in (root / "docintel" / "meta").glob("*-build.json")
    ]
    hours = sum(h for h in builds if isinstance(h, (int, float)))
    return {
        "read": build.pages_read(root / "runs", pages),
        "corpora": {
            "documents": len(pages),
            "pages": sum(pages.values()),
            "by_corpus": {
                c: {
                    "documents": sum(1 for k in pages if k[0] == c),
                    "pages": sum(n for k, n in pages.items() if k[0] == c),
                }
                for c in ("fara", "deepform", "cord", "nist")
            },
        },
        "prices": {
            "frontier": PRICE_LIST_DATE,
            "docintel": DOCINTEL_PRICE_DATE,
            "serve_gpu": SERVE_PRICE.gpu,
            "serve_usd_per_hour": SERVE_PRICE.usd_per_hour,
            "serve_checked": SERVE_PRICE.checked.isoformat(),
        },
        "serving": build.serving_json(runs, gated),
        "training": build.training_json(records),
        "gate": build.gate_json(decisions),
        "ceiling": build.subset_json(ceiling),
        "noise": build.subset_json(noise),
        "docintel_training": {
            "models": len(builds),
            "hours": hours,
            "usd": max(0.0, hours - 10) * 3,
        },
    }


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


def _gate_parts(corpus: str, level: str) -> tuple[list[str], str, list[str], list[str]]:
    """(corpora read, the report's table key, dev documents, test documents) for one gate
    comparison. NIST's twenty faces are read as twenty corpora and gated as one."""
    from legible.data.vrdu import headline_split_files, read_split
    from legible.schema.corpora import NIST_SCHEMAS

    if corpus == "nist":
        return (
            sorted(NIST_SCHEMAS),
            "nist",
            sorted(part_docs("nist", "dev")),
            sorted(part_docs("nist", "test")),
        )
    if corpus == "cord":
        return ["cord"], "cord", sorted(part_docs("cord", "dev")), sorted(part_docs("cord", "test"))
    raw = data_root() / "raw" / "vrdu"
    files = [f for f in headline_split_files(corpus, level) if f.endswith("SD_0.json")]  # type: ignore[arg-type]
    splits = [read_split(corpus, raw / f) for f in files]  # type: ignore[arg-type]
    return (
        [corpus],
        f"{corpus}-{level}",
        sorted({d for sp in splits for d in sp.valid}),
        sorted({d for sp in splits for d in sp.test}),
    )


#: Every comparison the gate decides, NIST's twenty faces as one.
GATE_RUNS: dict[str, tuple[str, ...]] = {**GATE_LEVELS, "nist": ("test",)}


@gate_app.command("export")
def gate_export(
    out: Path = typer.Option(Path("gate-runs"), help="One directory per comparison under it."),
) -> None:
    """Write the gate's spec and both sides for every corpus: the fine-tune and the frontier
    vision model with the best field accuracy on dev, the fine-tune also against the cost
    anchor. Run the gate on each directory afterwards (docs/gate.md)."""
    import json
    import statistics

    import yaml

    from legible.arms.frontier import Read, RunDir
    from legible.gate import SideMeta, export, spec, spec_name, suite_key
    from legible.grade import DocGrade, grade_document, summarise
    from legible.report import ARMS, Arm, answers_for, arm_dirs
    from legible.schema.corpora import NIST_SCHEMAS, SCHEMAS

    root = data_root()
    truth = _truths()
    schemas = {**SCHEMAS, **NIST_SCHEMAS}
    frontier = [a for a in ARMS if a.arm == "a"]
    tuned = [a for a in ARMS if a.arm == "b"]
    anchor = next(a for a in ARMS if a.route == "anchor")

    def side(
        arm: Arm, corpora: list[str], table: str, part: str, docs: list[str]
    ) -> tuple[dict[str, list[DocGrade]], dict[str, list[str]], SideMeta]:
        """Grades and failed documents per corpus, and what the side cost."""
        answers = answers_for(root, arm, corpora, part, 0, [], table)
        reads: dict[str, Read] = {}
        dirs = arm_dirs(root, arm, corpora, part, 0, table)
        for d in dirs:
            if (d / "run.json").exists():
                reads.update(RunDir(d).reads())
        grades: dict[str, list[DocGrade]] = {}
        failed: dict[str, list[str]] = {}
        for doc in docs:
            c = truth[doc].schema.corpus
            r = reads.get(doc)
            if r is None or r.text is None or answers is None or doc not in answers.outputs:
                failed.setdefault(c, []).append(doc)
                continue
            grades.setdefault(c, []).append(
                grade_document(
                    truth[doc].schema,
                    doc,
                    truth[doc].record,
                    answers.outputs[doc],
                    page_text=truth[doc].text,
                    alternatives=truth[doc].alternatives,
                )
            )
        latencies = [r.latency_ms for r in reads.values() if r.latency_ms is not None]
        cost = sum((answers.usd.get(d, 0.0) for d in docs), 0.0) if answers else 0.0
        meta = SideMeta(
            label=arm.label,
            run_id=f"{arm.arm}-{arm.route or arm.size}-{table}-{part}",
            directory=str(dirs[0].parent.parent.relative_to(root).as_posix()) if dirs else "",
            calls=sum(1 for d in docs if d in reads),
            # A batch read's latency is the batch's, not the page's (docs/models.md).
            latency_p50_ms=statistics.median(latencies) if latencies and arm.arm != "a" else 0.0,
            cost_usd=round(cost, 4),
            uncosted_calls=0,
        )
        return grades, failed, meta

    def dev_accuracy(arm: Arm, corpora: list[str], table: str, dev: list[str]) -> float:
        grades, _, _ = side(arm, corpora, table, "dev", dev)
        flat = [g for gs in grades.values() for g in gs]
        return summarise(flat).accuracy.point if flat else -1.0

    for corpus, levels in GATE_RUNS.items():
        for level in levels:
            corpora, table, dev, test = _gate_parts(corpus, level)
            best_a = max(frontier, key=lambda a: dev_accuracy(a, corpora, table, dev))
            best_b = max(tuned, key=lambda a: dev_accuracy(a, corpora, table, dev))
            baselines = [best_a] if best_a == anchor else [best_a, anchor]
            name = (
                f"legible-nist-{level}" if corpus == "nist" else spec_name(schemas[corpus], level)
            )
            for base in baselines:
                b_grades, b_failed, b_meta = side(base, corpora, table, "test", test)
                c_grades, c_failed, c_meta = side(best_b, corpora, table, "test", test)
                faces = sorted(set(b_grades) | set(c_grades) | set(b_failed) | set(c_failed))
                suites: list[dict[str, object]] = []
                sides: tuple[dict[str, object], dict[str, object]] = ({}, {})
                for face in faces:
                    s, sb, sc = export(
                        schemas[face],
                        b_grades.get(face, []),
                        c_grades.get(face, []),
                        baseline_meta=b_meta,
                        candidate_meta=c_meta,
                        baseline_failed=b_failed.get(face, []),
                        candidate_failed=c_failed.get(face, []),
                        name=name,
                    )
                    # NIST's faces share line numbers, so each face's suites carry its name.
                    prefix = f"{suite_key(face)}-" if corpus == "nist" else ""
                    for su in s["suites"]:
                        k = prefix + su["key"]
                        suites.append({"key": k, "source": {"kind": "outcomes_file", "block": k}})
                    for target, got in zip(sides, (sb, sc), strict=True):
                        target.setdefault("label", got["label"])
                        target.setdefault("source", got["source"])
                        merged = target.setdefault("suites", {})
                        assert isinstance(merged, dict)
                        for k, v in got["suites"].items():
                            merged[prefix + k] = {**v, "suite": prefix + k}
                body = spec(schemas[faces[0]], name=name)
                body["suites"] = suites
                d = out / f"{name}-{best_b.size}-vs-{'anchor' if base == anchor else 'best'}"
                d.mkdir(parents=True, exist_ok=True)
                header = (
                    f"# The 03 gate's spec for {corpus} {level}: {best_b.label} against "
                    f"{base.label}, the best on dev. Written by `legible gate export`; do not "
                    "edit.\n"
                )
                (d / "spec.yaml").write_text(
                    header + yaml.safe_dump(body, sort_keys=False), encoding="utf-8", newline="\n"
                )
                for fname, content in zip(("baseline.json", "candidate.json"), sides, strict=True):
                    (d / fname).write_text(
                        json.dumps(content, indent=1, sort_keys=True) + "\n",
                        encoding="utf-8",
                        newline="\n",
                    )
                typer.echo(f"{d}: {best_b.label} against {base.label}, {len(suites)} suites")


ocr_app = typer.Typer(no_args_is_help=True, help="Tesseract over a corpus's pages.")
app.add_typer(ocr_app, name="ocr")


#: Test subsets (legible/data/subsets.py): read as parts of their own, each once.
SUBSETS = ("ceiling", "repeat", "vrdu_curve")


def part_docs(corpus: str, part: str) -> set[str]:
    """The documents of a split part, over every headline split file: VRDU's train, valid
    (dev) or test unions; CORD's own split; NIST's split by submission, where test is the 500
    pages every arm reads, and `nist_<face>` is one face's share."""
    from legible.data.render import read_manifest

    if part in SUBSETS:
        from legible.data.subsets import read

        family = "nist" if corpus.startswith("nist") else corpus
        chosen = set(read(MANIFESTS / "subsets.json")[part].get(family, []))
        if corpus.startswith("nist_"):
            return chosen & part_docs(corpus, "test")
        return chosen
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
    part: str = typer.Option(
        "dev", help="dev or test (NIST also curve, FARA and DeepForm vrdu_curve). Test is run once."
    ),
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
    if part == "vrdu_curve":
        # The subset is the seed-0 unseen-template test documents; each is read with the rules
        # of the split file it is a test document of, as at level 0.
        subset = part_docs(corpus, "vrdu_curve")
        for p in headline_split_files(corpus, "unseen"):  # type: ignore[arg-type]
            if not p.endswith("SD_0.json"):
                continue
            split = read_split(corpus, raw / p)  # type: ignore[arg-type]
            docs = [d for d in split.test if d in subset]
            out = out_dir / f"{Path(p).stem}-{part}.jsonl"
            n = run(data_root(), corpus, docs, pages, rule_sets_for(corpus, split), level, out)
            typer.echo(f"{Path(p).stem} {part} level {level}: {n} documents")
        return
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


def _route(name: str, config: Path = GATEWAY_CONFIG) -> tuple[str, str]:
    """(vendor, model) for a route in the gateway configuration, the one place models are
    named (boundary.yaml, or the served one legible/serve.py writes for arms B and C)."""
    import yaml

    routes = yaml.safe_load(config.read_text(encoding="utf-8"))["routes"]
    if name not in routes:
        raise typer.BadParameter(f"no route {name!r} in {config}")
    return routes[name]["provider"], routes[name]["model"]


def _read_run(
    arm: str,
    corpus: str,
    part: str,
    level: int,
    route: str,
    prompt_version: int,
    config: Path = GATEWAY_CONFIG,
    split: str | None = None,
    logprobs: bool = False,
    require: bool = True,
) -> tuple[RunSpec, Prompt, list[str], Path]:
    from legible.arms.read_run import (
        RunSpec,
        max_tokens_for,
        prompt_for,
        require_dev,
        run_dir,
        structured_for,
        temperature_for,
    )

    if arm not in {"a", "b", "c", "d"}:
        raise typer.BadParameter("arm is a, b or c (page images) or d (OCR text)")
    if part not in {"dev", "test", *SUBSETS} and not (
        part == "curve" and corpus.startswith("nist")
    ):
        raise typer.BadParameter("part is dev, test, a subset, or curve for NIST")
    vendor, model = _route(route, config)
    if logprobs and vendor != "selfhosted":
        raise typer.BadParameter("log-probabilities are asked of a self-hosted server only")
    spec = RunSpec(
        arm=arm,
        corpus=corpus,
        part=part,
        level=level,
        route=route,
        vendor=vendor,
        model=model,
        prompt_version=prompt_version,
        max_tokens=max_tokens_for(corpus, vendor, part),  # type: ignore[arg-type]
        structured=structured_for(vendor),  # type: ignore[arg-type]
        temperature=temperature_for(vendor),  # type: ignore[arg-type]
        logprobs=logprobs,
    )
    prompt = prompt_for(corpus, prompt_version, spec.arm)
    dev, docs = sorted(part_docs(corpus, "dev")), sorted(part_docs(corpus, part))
    if split is not None:
        # A model trained on one split file's training part reads that file's own dev and
        # test documents and no others.
        from legible.data.vrdu import DIRECTORY, read_split

        split_path = data_root() / "raw" / "vrdu" / DIRECTORY[corpus] / "few_shot-splits"  # type: ignore[index]
        sp = read_split(corpus, split_path / f"{split}.json")  # type: ignore[arg-type]
        dev = sorted(set(dev) & set(sp.valid))
        docs = sorted(set(docs) & set(sp.valid if part == "dev" else sp.test))
    if require:
        require_dev(data_root(), spec, dev, prompt)
    return spec, prompt, docs, run_dir(data_root(), spec)


@read_app.command("submit")
def read_submit(
    corpus: str = typer.Argument(..., help="fara, deepform or cord."),
    arm: str = typer.Option(..., help="a (page images) or d (OCR text)."),
    part: str = typer.Option("dev", help="dev or test. Test needs a finished dev run first."),
    level: int = typer.Option(0, min=0, max=len(LEVELS) - 1),
    route: str = typer.Option("quality", help="A route in boundary.yaml."),
    prompt_version: int = typer.Option(1, min=1),
    limit: int | None = typer.Option(None, help="Dev only: at most this many documents."),
    split: str | None = typer.Option(
        None,
        help="VRDU only: just this split file's part (its name without .json), for a model "
        "trained on that file's training part.",
    ),
    sync: bool = typer.Option(False, help="One call per document instead of batches."),
    concurrency: int = typer.Option(
        0, help="Self-hosted: this many calls in flight (arms B and C), timed for throughput."
    ),
    gateway_config: Path = typer.Option(GATEWAY_CONFIG, help="The gateway configuration."),
    logprobs: bool = typer.Option(
        False,
        help="Self-hosted: keep each answer token's log-probability, the fine-tuned arm's "
        "confidence; such a run is kept apart from the plain one.",
    ),
) -> None:
    """Send every document of a part not yet read or submitted, through the gateway."""
    from boundary import Gateway

    from legible.arms.frontier import run_sync
    from legible.arms.read_run import open_run, requests_for, submit
    from legible.data.render import read_manifest

    spec, prompt, docs, path = _read_run(
        arm, corpus, part, level, route, prompt_version, gateway_config, split, logprobs
    )
    if limit is not None:
        if part != "dev":
            raise typer.BadParameter("a test run reads every test document, once")
        docs = docs[:limit]

    pages: dict[str, list[PageEntry]] = {}
    for e in read_manifest(manifest(corpus)):
        pages.setdefault(e.doc_id, []).append(e)
    run = open_run(path, spec, prompt)
    gateway = Gateway.from_config(gateway_config, project="legible")
    if concurrency:
        from legible.arms.frontier import run_concurrent

        have = set(run.reads())
        requests = requests_for(
            data_root(), spec, prompt, [d for d in docs if d not in have], pages
        )
        n, seconds = run_concurrent(
            gateway,
            requests,
            run,
            purpose=spec.purpose,
            run_id=spec.run_id,
            concurrency=concurrency,
        )
        # The wall time of this pass beside the run, for the throughput a page is costed at.
        with (path / "throughput.jsonl").open("a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps({"reads": n, "seconds": seconds, "concurrency": concurrency}) + "\n")
        typer.echo(f"{spec.run_id}: {n} documents in {seconds:.0f} s at {concurrency} in flight")
        return
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


@read_app.command("retry-missing")
def read_retry_missing(
    corpus: str = typer.Argument(...),
    arm: str = typer.Option(..., help="a or d."),
    part: str = typer.Option(..., help="curve or a subset; never dev or test."),
    level: int = typer.Option(0, min=0, max=len(LEVELS) - 1),
    route: str = typer.Option("quality"),
    prompt_version: int = typer.Option(1, min=1),
) -> None:
    """Set aside the reads the vendor never answered, so the next submit asks again. Dev and
    test are refused: their unanswered reads stay graded as unread, as reported since the
    first test run (docs/models.md)."""
    from legible.arms.read_run import open_run

    if part in {"dev", "test"}:
        raise typer.BadParameter("dev and test keep their unanswered reads as unread")
    spec, prompt, _, path = _read_run(arm, corpus, part, level, route, prompt_version)
    gone = open_run(path, spec, prompt).set_aside_missing()
    typer.echo(f"{spec.run_id}: {len(gone)} unanswered reads set aside")


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


train_app = typer.Typer(no_args_is_help=True, help="Arm B: QLoRA on the page images.")
app.add_typer(train_app, name="train")


def _training_sets() -> dict[str, tuple[str, list[str], set[str]]]:
    """Every training set the headline needs: name to (schema key, train documents, held-out
    documents). FARA's unseen level is one set per held-out template and seed, DeepForm's one
    per seed, the mixed level one per corpus and seed, CORD and NIST one each."""
    from legible.data.vrdu import headline_split_files, read_split

    raw = data_root() / "raw" / "vrdu"
    out: dict[str, tuple[str, list[str], set[str]]] = {}
    for c in ("fara", "deepform"):
        for level in ("unseen", "mixed"):
            for f in headline_split_files(c, level):
                sp = read_split(c, raw / f)
                template = f"-{sp.template.lower().replace(' ', '_')}" if sp.template else ""
                name = f"{c}-{level}{template}-s{sp.seed}"
                out[name] = (c, list(sp.train), set(sp.valid) | set(sp.test))
    held = part_docs("cord", "dev") | part_docs("cord", "test")
    out["cord"] = ("cord", sorted(part_docs("cord", "train")), held)
    for face in sorted(k for k in _nist_keys()):
        held = part_docs(face, "dev") | part_docs(face, "test")
        out[face] = (face, sorted(_nist_part(face, "train")), held)
    return out


def _nist_keys() -> list[str]:
    from legible.schema.corpora import NIST_SCHEMAS

    return sorted(NIST_SCHEMAS)


def _nist_part(face: str, part: str) -> set[str]:
    from legible.data.nist import read_splits

    rows = read_splits(MANIFESTS / "nist-splits.json")
    return {d for d, r in rows.items() if f"nist_{r.face.lower()}" == face and r.part == part}


@train_app.command("sets")
def train_sets() -> None:
    """Write every training set under the data root's train/ directory."""
    from legible.data.cord import read_shard
    from legible.data.fetch import load_checksums
    from legible.data.render import read_manifest
    from legible.data.vrdu import read_dataset
    from legible.schema.corpora import SCHEMAS
    from legible.train.dataset import write_training_set

    raw = data_root() / "raw"
    truth: dict[str, object] = {}
    for c in ("fara", "deepform"):
        for d in read_dataset(c, raw / "vrdu"):
            truth[d.doc_id] = d.truth
    for shard in sorted(load_checksums("cord").files):
        for cd, _ in read_shard(raw / "cord" / shard, None):
            truth[cd.doc_id] = cd.truth
    from legible.data import nist

    zip_path, md5s = nist.fetch_sd2(raw / "nist")
    for nd, _ in nist.read_sd2(zip_path, md5s, None):
        truth[nd.doc_id] = nd.truth
    pages: dict[str, list[str]] = {}
    for c in ("fara", "deepform", "cord", "nist"):
        for e in sorted(read_manifest(manifest(c)), key=lambda e: e.page):
            pages.setdefault(e.doc_id, []).append(e.path)
    for name, (key, docs, held) in _training_sets().items():
        n = write_training_set(
            data_root() / "train" / f"{name}.jsonl",
            SCHEMAS[key],
            name,
            ((d, truth[d], pages[d]) for d in docs),  # type: ignore[misc]
            held_out=held,
        )
        typer.echo(f"{name}: {n} documents")


@train_app.command("run")
def train_run(
    dataset: str = typer.Argument(..., help="A training set name, as `train sets` wrote it."),
    size: str = typer.Option(..., help="2b or 4b."),
    seed: int = typer.Option(0),
    visual_tokens: int | None = typer.Option(None, help="Default: the corpus's (recipe.py)."),
    volume: int | None = typer.Option(None, help="Train on the first n documents only."),
    save_steps: int = typer.Option(25, help="Steps between checkpoints (a smoke run: 1)."),
    checkpoint_uri: str | None = typer.Option(None, help="s3://<volume>/checkpoints"),
    s3_datacenter: str | None = typer.Option(None),
) -> None:
    """One fine-tune on the rented card, resuming from its newest checkpoint."""
    from legible.schema.corpora import SCHEMAS
    from legible.train.ablate import MULTI, MULTI_SETS
    from legible.train.checkpoint import CheckpointStore, runpod_s3
    from legible.train.dataset import TrainingHeader, read_training_set
    from legible.train.recipe import VOLUME_FOR, chosen
    from legible.train.vision import Example, describe, train

    def interleaved(es: list[Example]) -> list[Example]:
        # A fixed order by document, so a step sees every form and a volume cut takes some
        # of each.
        import hashlib

        return sorted(es, key=lambda e: hashlib.sha256(e[1].doc_id.encode()).hexdigest())

    headers: list[TrainingHeader] = []

    def load(name: str) -> list[Example]:
        # "nist" is the twenty faces' sets read as one: one model for the form family, each
        # face asked with its own prompt.
        if name == "nist":
            return interleaved([e for face in _nist_keys() for e in load(face)])
        path = data_root() / "train" / f"{name}.jsonl"
        with path.open(encoding="utf-8") as f:
            key = TrainingHeader.model_validate_json(f.readline()).corpus
        header, rows = read_training_set(path, SCHEMAS[key])
        headers.append(header)
        return [(header.instruction, r) for r in rows]

    if dataset == MULTI:
        # Every corpus in one run, each as its specialist saw it (NIST cut to the same 800
        # faces), then interleaved.
        examples: list[Example] = []
        for name in MULTI_SETS:
            got = load(name)
            examples += got[: VOLUME_FOR[name]] if name in VOLUME_FOR else got
        examples = interleaved(examples)
    else:
        examples = load(dataset)
    config = chosen(
        size,  # type: ignore[arg-type]
        dataset,
        seed=seed,
        **({"visual_tokens": visual_tokens} if visual_tokens else {}),
        **({"volume": volume} if volume else {}),
        save_steps=save_steps,
    )
    out = data_root() / "models" / config.run_id
    syncer = (
        runpod_s3(f"{checkpoint_uri}/{config.run_id}", s3_datacenter)
        if checkpoint_uri and s3_datacenter
        else None
    )
    record = train(
        config,
        headers,
        examples,
        data_root() / "pages",
        out_dir=out,
        store=CheckpointStore(out, syncer, keep=2),
    )
    typer.echo(describe(record))


@train_app.command("ablations")
def train_ablations() -> None:
    """The ablation runs (legible/train/ablate.py), one a line: run id, kind, training set,
    visual tokens and volume ("-" for all), as `ops/ablate-queue.sh` reads them."""
    from legible.train.ablate import ablations

    for a in ablations():
        c = a.config
        typer.echo(f"{c.run_id} {a.kind} {c.dataset} {c.visual_tokens} {c.volume or '-'}")


serve_app = typer.Typer(no_args_is_help=True, help="Arms B and C behind vLLM.")
app.add_typer(serve_app, name="serve")


@serve_app.command("merge")
def serve_merge(run_id: str = typer.Argument(..., help="A finished run under models/.")) -> None:
    """Merge a run's adapter into its bf16 base, checked on its first training example."""
    from PIL import Image

    from legible.schema.corpora import SCHEMAS
    from legible.serve import merge
    from legible.train.dataset import read_training_set
    from legible.train.vision import Collator, load_processor, read_record

    out = data_root() / "models" / run_id
    record = read_record(out)
    header = record.datasets[0]
    _, rows = read_training_set(
        data_root() / "train" / f"{header.split_file}.jsonl", SCHEMAS[header.corpus]
    )
    processor = load_processor(record.config)

    def load_page(rel: str) -> object:
        with Image.open(data_root() / "pages" / rel) as img:
            return img.convert("RGB")

    # The check examples: the four shortest answers among the first 50 training documents,
    # so their logits fit beside a 4B on 24 GB (a DeepForm order's 7,500-token answer did not).
    import itertools

    shortest = sorted(itertools.islice(rows, 50), key=lambda r: len(r.target))[:4]
    collator = Collator(processor, load_page, record.config.max_seq_len)
    check = [collator.example((header.instruction, r)) for r in shortest]
    done = merge(out / "adapter", data_root() / "merged" / run_id, check)
    typer.echo(done.model_dump_json())


@serve_app.command("argv")
def serve_argv(
    model: str = typer.Argument(..., help="A merged run id, or `2b-it` / `4b-it` for arm C."),
    max_images: int = typer.Option(12),
    visual_tokens: int = typer.Option(1120),
    port: int = typer.Option(8000),
) -> None:
    """Print the `vllm serve` command line for a model, one argument a line."""
    from legible.serve import vllm_argv
    from legible.train.recipe import BASES

    if model.endswith("-it"):
        base = BASES[model.removesuffix("-it")]  # type: ignore[index]
        argv = vllm_argv(
            base.instruct_repo,
            model,
            visual_tokens=visual_tokens,
            max_images=max_images,
            port=port,
            revision=base.instruct_revision,
        )
    else:
        argv = vllm_argv(
            str(data_root() / "merged" / model),
            model,
            visual_tokens=visual_tokens,
            max_images=max_images,
            port=port,
        )
    typer.echo("\n".join(argv))


@serve_app.command("headline")
def serve_headline() -> None:
    """The run ids of the seed-0 fine-tunes behind the headline tables and the review rate
    (FARA and DeepForm unseen templates, CORD, NIST), one a line, both sizes."""
    from legible.report import TABLE_SETS
    from legible.train.recipe import chosen

    tables = ("fara-unseen", "deepform-unseen", "cord", "nist")
    sizes: tuple[Literal["2b", "4b"], ...] = ("2b", "4b")
    typer.echo(
        "\n".join(chosen(s, ds).run_id for s in sizes for t in tables for ds in TABLE_SETS[t])
    )


@serve_app.command("reads")
def serve_reads(
    dataset: str = typer.Argument(..., help="The training set a model learned."),
    run_id: str | None = typer.Option(None, help="The model; an ablation may owe fewer reads."),
) -> None:
    """The reads a model trained on this set owes: one `corpus split part level` a line
    ("-" for no split file), dev before test. A VRDU model reads its own split file's dev
    and test documents, and the seed-0 unseen-template model its test documents in the VRDU
    curve subset at levels 2 and 4; CORD's its test set; NIST's the twenty faces' dev, test
    and curve. The multi-corpus model reads each of its sets' dev and test; an ablation that
    asks about clean pages reads level 0 only (legible/train/ablate.py)."""
    from legible.train.ablate import find

    lines = _owed_reads(dataset)
    run = find(run_id) if run_id else None
    if run is not None and run.level0_only:
        lines = [x for x in lines if x.split()[2] in {"dev", "test"} and x.split()[3] == "0"]
    typer.echo("\n".join(lines))


def _owed_reads(dataset: str) -> list[str]:
    """`serve reads`, as a list."""
    from legible.data.vrdu import headline_split_files, read_split
    from legible.train.ablate import MULTI, MULTI_SETS

    if dataset == MULTI:
        return [x for name in MULTI_SETS for x in _owed_reads(name)]
    lines: list[str] = []
    if dataset.startswith(("fara-", "deepform-")):
        corpus = dataset.split("-")[0]
        raw = data_root() / "raw" / "vrdu"
        for level in ("unseen", "mixed"):
            for f in headline_split_files(corpus, level):  # type: ignore[arg-type]
                sp = read_split(corpus, raw / f)  # type: ignore[arg-type]
                template = f"-{sp.template.lower().replace(' ', '_')}" if sp.template else ""
                if f"{corpus}-{level}{template}-s{sp.seed}" == dataset:
                    stem = Path(f).stem
                    lines += [f"{corpus} {stem} dev 0", f"{corpus} {stem} test 0"]
                    if level == "unseen" and sp.seed == 0:
                        # The headline model also reads its share of the VRDU curve subset.
                        lines += [f"{corpus} {stem} vrdu_curve {lv}" for lv in (2, 4)]
    elif dataset == "cord":
        lines += ["cord - dev 0", "cord - test 0"]
    elif dataset == "nist":
        faces = _nist_keys()
        lines += [f"{c} - dev 0" for c in faces] + [f"{c} - test 0" for c in faces]
        lines += [f"{c} - curve {lv}" for lv in (1, 2, 3, 4) for c in faces]
    if not lines:
        raise typer.BadParameter(f"no reads known for {dataset}")
    return lines


@serve_app.command("config")
def serve_config(
    served_name: str = typer.Argument(...),
    out: Path = typer.Option(Path("boundary-served.yaml")),
    port: int = typer.Option(8000),
) -> None:
    """Write the gateway configuration with the served model as a route of its own name."""
    import yaml

    from legible.serve import gateway_config

    base = yaml.safe_load(GATEWAY_CONFIG.read_text(encoding="utf-8"))
    out.write_text(yaml.safe_dump(gateway_config(base, served_name, port)), encoding="utf-8")
    typer.echo(f"{out}: route {served_name}")


docintel_app = typer.Typer(
    no_args_is_help=True, help="Arm F: Azure AI Document Intelligence (legible/arms/docintel.py)."
)
app.add_typer(docintel_app, name="docintel")

#: The training sets arm F builds a custom model for: FARA's three unseen-template splits and
#: DeepForm's at seed 0, and NIST's twenty faces. CORD is read by the prebuilt receipt model.
DOCINTEL_ROUTE_CORD = "docintel-receipt"


def _docintel_sets() -> list[str]:
    from legible.report import TABLE_SETS

    return [*TABLE_SETS["fara-unseen"], *TABLE_SETS["deepform-unseen"], *_nist_keys()]


def _docintel_training(dataset: str) -> tuple[CorpusSchema, dict[str, list[Path]], dict[str, Any]]:
    """A training set's schema, its first documents by id (`TRAIN_DOCS`) as page images, and
    their truth records."""
    from legible.arms.docintel import TRAIN_DOCS
    from legible.schema.corpora import NIST_SCHEMAS, SCHEMAS
    from legible.train.dataset import read_training_set

    schemas = {**SCHEMAS, **NIST_SCHEMAS}
    path = data_root() / "train" / f"{dataset}.jsonl"
    corpus = json.loads(path.read_text(encoding="utf-8").split("\n", 1)[0])["corpus"]
    schema = schemas[corpus]
    _, rows = read_training_set(path, schema)
    n = TRAIN_DOCS["nist" if corpus.startswith("nist") else corpus]
    chosen = sorted(rows, key=lambda r: r.doc_id)[:n]
    images = {r.doc_id: [data_root() / "pages" / p for p in r.pages] for r in chosen}
    truth = {r.doc_id: json.loads(r.target) for r in chosen}
    return schema, images, truth


def _docintel_gateway() -> Any:
    from boundary import Gateway

    return Gateway.from_config(GATEWAY_CONFIG, project="legible")


@docintel_app.command("layout")
def docintel_layout(
    dataset: str = typer.Argument(..., help="A training set, or `all` for every one."),
    collect: bool = typer.Option(False, help="Collect finished readings instead of sending."),
) -> None:
    """Read a training set's documents with the layout model, the words its labels are drawn
    on; billed per page through the gateway."""
    from legible.arms.docintel_run import collect_layout, submit_layout

    gateway = _docintel_gateway()
    for ds in _docintel_sets() if dataset == "all" else [dataset]:
        if collect:
            stored, running = collect_layout(gateway, data_root(), ds)
            typer.echo(f"{ds}: {stored} layout readings stored, {running} still running")
        else:
            _, images, _ = _docintel_training(ds)
            n = submit_layout(gateway, data_root(), ds, images, run_id=f"arm-f-layout-{ds}")
            typer.echo(f"{ds}: {n} of {len(images)} documents sent to the layout model")


@docintel_app.command("prepare")
def docintel_prepare(dataset: str = typer.Argument(..., help="A training set, or `all`.")) -> None:
    """Write a training set as the service reads it, labels drawn from the truth on the
    layout reading's words, and say how many values were found."""
    from legible.arms.docintel_run import write_set

    for ds in _docintel_sets() if dataset == "all" else [dataset]:
        schema, images, truth = _docintel_training(ds)
        cov = write_set(data_root(), ds, schema, images, truth)
        share = cov["labelled"] / cov["values"] if cov["values"] else 0.0
        typer.echo(
            f"{ds}: {cov['documents']} documents, {cov['labelled']} of {cov['values']} "
            f"values labelled ({share:.1%})"
        )


#: Where arm F's training sets are uploaded for the service to build from (rg-portfolio,
#: East US, created 2026-10-24). The account key is read from the Azure CLI's login.
DOCINTEL_STORAGE = "legibledocinteltrain"
DOCINTEL_CONTAINER = "train"


def _az(*args: str) -> str:
    import subprocess

    out = subprocess.run(
        ["az", *args], capture_output=True, text=True, check=True, shell=os.name == "nt"
    )
    return out.stdout.strip()


@docintel_app.command("upload")
def docintel_upload(dataset: str = typer.Argument(..., help="A training set, or `all`.")) -> None:
    """Copy prepared training sets to the storage container the service builds from."""
    from legible.arms.docintel_run import set_dir

    key = _az(
        "storage", "account", "keys", "list", "--account-name", DOCINTEL_STORAGE,
        "--query", "[0].value", "-o", "tsv",
    )  # fmt: skip
    auth = ["--account-name", DOCINTEL_STORAGE, "--account-key", key]
    _az("storage", "container", "create", "--name", DOCINTEL_CONTAINER, *auth)
    for ds in _docintel_sets() if dataset == "all" else [dataset]:
        _az(
            "storage", "blob", "upload-batch", "--destination", DOCINTEL_CONTAINER,
            "--destination-path", ds, "--source", str(set_dir(data_root(), ds)),
            "--overwrite", "--only-show-errors", *auth,
        )  # fmt: skip
        typer.echo(f"{ds}: uploaded")


@docintel_app.command("build")
def docintel_build(
    dataset: str = typer.Argument(..., help="A training set, or `all`."),
    max_hours: float = typer.Option(1.0, help="The build's training-hour ceiling."),
    collect: bool = typer.Option(False, help="Record finished builds instead of starting."),
) -> None:
    """Ask the service to build each training set's custom neural model, or record the builds
    that have finished, with the training hours the service reports. Building is not a call
    through the gateway: it reads no page and is billed, past ten free hours a month, by the
    hour (docs/docintel.md)."""
    import datetime as dt

    import httpx
    from boundary.env import find_dotenv, load_dotenv

    from legible.arms.docintel import model_id
    from legible.arms.docintel_run import meta_path

    env = find_dotenv(Path.cwd(), GATEWAY_CONFIG.resolve().parent)
    if env is not None:
        load_dotenv(env)
    endpoint = os.environ["AZURE_DOCINTEL_ENDPOINT"].rstrip("/")
    headers = {"ocp-apim-subscription-key": os.environ["AZURE_DOCINTEL_KEY"]}
    version = "api-version=2024-11-30"
    for ds in _docintel_sets() if dataset == "all" else [dataset]:
        record_path = meta_path(data_root(), ds, "build")
        record = json.loads(record_path.read_text("utf-8")) if record_path.exists() else {}
        if collect:
            if "model" in record or "operation" not in record:
                continue
            r = httpx.get(record["operation"], headers=headers, timeout=60)
            r.raise_for_status()
            op = r.json()
            if op.get("status") in {"notStarted", "running"}:
                typer.echo(f"{ds}: still building ({op.get('percentCompleted', 0)}%)")
                continue
            if op.get("status") != "succeeded":
                raise RuntimeError(f"{ds}: build {op.get('status')}: {op.get('error')}")
            m = httpx.get(
                f"{endpoint}/documentintelligence/documentModels/{model_id(ds)}?{version}",
                headers=headers,
                timeout=60,
            )
            m.raise_for_status()
            info = m.json()
            record["model"] = {
                k: info.get(k)
                for k in ("modelId", "createdDateTime", "trainingHours", "apiVersion")
            }
            record_path.write_text(json.dumps(record, indent=1), encoding="utf-8")
            typer.echo(f"{ds}: built, {info.get('trainingHours')} training hours")
            continue
        if "operation" in record:
            typer.echo(f"{ds}: already started")
            continue
        expiry = (dt.datetime.now(dt.UTC) + dt.timedelta(days=2)).strftime("%Y-%m-%dT%H:%MZ")
        key = _az(
            "storage", "account", "keys", "list", "--account-name", DOCINTEL_STORAGE,
            "--query", "[0].value", "-o", "tsv",
        )  # fmt: skip
        sas = _az(
            "storage", "container", "generate-sas", "--name", DOCINTEL_CONTAINER,
            "--account-name", DOCINTEL_STORAGE, "--account-key", key,
            "--permissions", "rl", "--expiry", expiry, "--https-only", "-o", "tsv",
        )  # fmt: skip
        url = f"https://{DOCINTEL_STORAGE}.blob.core.windows.net/{DOCINTEL_CONTAINER}?{sas}"
        body = {
            "modelId": model_id(ds),
            "description": f"legible arm F, trained on {ds}",
            "buildMode": "neural",
            "azureBlobSource": {"containerUrl": url, "prefix": f"{ds}/"},
            "maxTrainingHours": max_hours,
        }
        r = httpx.post(
            f"{endpoint}/documentintelligence/documentModels:build?{version}",
            headers=headers,
            json=body,
            timeout=120,
        )
        if r.status_code != 202:
            raise RuntimeError(f"{ds}: build refused, {r.status_code} {r.text[:300]}")
        record = {
            "operation": r.headers["operation-location"],
            "started": dt.datetime.now(dt.UTC).isoformat(),
        }
        record_path.parent.mkdir(parents=True, exist_ok=True)
        record_path.write_text(json.dumps(record, indent=1), encoding="utf-8")
        typer.echo(f"{ds}: build started")


@docintel_app.command("read")
def docintel_read(
    dataset: str = typer.Argument(
        ..., help="A training set (its model reads that split's or face's documents), or cord."
    ),
    part: str = typer.Option("test", help="test, or curve for a NIST face."),
    level: int = typer.Option(0, min=0, max=len(LEVELS) - 1),
    collect: bool = typer.Option(False, help="Collect finished reads instead of sending."),
) -> None:
    """Send a part's documents to the model, one a batch, or collect what has finished. A
    custom model reads only the documents its split holds out (NIST: its face's)."""
    from legible.arms.docintel import custom_model, model_id, receipt_record, to_record
    from legible.arms.docintel_run import collect_reads, doc_images, open_read_run, submit_reads
    from legible.data.render import read_manifest
    from legible.schema.corpora import NIST_SCHEMAS, SCHEMAS

    schemas = {**SCHEMAS, **NIST_SCHEMAS}
    if dataset == "cord":
        corpus, route, model = "cord", DOCINTEL_ROUTE_CORD, DOCINTEL_ROUTE_CORD
        docs = sorted(part_docs("cord", part))
    elif dataset.startswith("nist_"):
        corpus, route, model = dataset, model_id(dataset), custom_model(dataset)
        docs = sorted(part_docs(dataset, part))
    else:
        if part != "test" or level != 0:
            raise typer.BadParameter("a VRDU model reads its split's test documents at level 0")
        line = next(x for x in _owed_reads(dataset) if x.split()[2] == "test")
        corpus, split = line.split()[:2]
        _, _, docs, _ = _read_run(
            "a", corpus, "test", 0, "quality", 1, GATEWAY_CONFIG, split, require=False
        )
        route, model = model_id(dataset), custom_model(dataset)
    schema = schemas[corpus]
    convert = (
        (lambda a: receipt_record(schema, a))
        if dataset == "cord"
        else (lambda a: to_record(schema, a))
    )
    path = data_root() / "runs" / "arm-f" / route / "p1" / f"level{level}" / corpus / part
    run = open_read_run(
        path,
        {"arm": "f", "corpus": corpus, "part": part, "level": level, "model": model,
         "dataset": dataset},
    )  # fmt: skip
    gateway = _docintel_gateway()
    if collect:
        stored, running = collect_reads(gateway, run, convert)
        typer.echo(f"{route} {corpus} {part} level {level}: {stored} stored, {running} running")
        return
    pages: dict[str, list[PageEntry]] = {}
    for e in read_manifest(manifest(corpus)):
        pages.setdefault(e.doc_id, []).append(e)
    n = submit_reads(
        gateway,
        run,
        model,
        doc_images(data_root(), level, pages, docs),
        run_id=f"arm-f-{route}-{corpus}-{part}-level{level}",
    )
    typer.echo(f"{route} {corpus} {part} level {level}: {n} of {len(docs)} documents sent")


bench_app = typer.Typer(
    no_args_is_help=True, help="The load test of a served model: latency and throughput."
)
app.add_typer(bench_app, name="bench")


@bench_app.command("run")
def bench_run(
    model: str = typer.Argument(..., help="The served route: a fine-tune's run id."),
    gpu: str = typer.Option(..., help="The card, as the provider names it."),
    usd_per_hour: float = typer.Option(..., help="The rate the provider returned for the pod."),
    checked: str = typer.Option(..., help="The date that rate was read, YYYY-MM-DD."),
    provider: str = typer.Option("RunPod Secure Cloud"),
    source: str = typer.Option("RunPod API costPerHr at pod creation"),
    gateway_config: Path = typer.Option(Path("boundary-served.yaml")),
    levels: str = typer.Option("1,8,32", help="Reads in flight, comma-separated."),
    warmup: float = typer.Option(30.0, help="Seconds at the start of each level discarded."),
) -> None:
    """Load-test a served fine-tune on its own test documents at level 0: the requests its
    accuracy reads sent, cycled in order, at each concurrency in turn (legible/bench/run.py).
    The record is rewritten to data/bench/<model>/bench.json after every level."""
    import datetime as dt

    from boundary import ChatRequest, Gateway

    from legible.arms.read_run import request_for
    from legible.bench.client import LevelResult
    from legible.bench.cost import GpuPrice, PriceKind
    from legible.bench.run import pages_per_second, sweep
    from legible.data.render import read_manifest

    record = json.loads((data_root() / "models" / model / "run.json").read_text("utf-8"))
    requests: list[tuple[ChatRequest, int]] = []
    corpora: set[str] = set()
    for line in _owed_reads(record["config"]["dataset"]):
        corpus, split, part, level = line.split()
        if part != "test" or level != "0":
            continue
        spec, prompt, docs, _ = _read_run(
            "b", corpus, "test", 0, model, 1, gateway_config,
            None if split == "-" else split, require=False,
        )  # fmt: skip
        pages: dict[str, list[PageEntry]] = {}
        for e in read_manifest(manifest(corpus)):
            pages.setdefault(e.doc_id, []).append(e)
        corpora.add(corpus.split("_")[0])
        requests += [
            (request_for(data_root(), spec, prompt, pages[d]), len(pages[d])) for d in docs
        ]
    price = GpuPrice(
        gpu=gpu,
        provider=provider,
        kind=PriceKind.ON_DEMAND,
        usd_per_hour=usd_per_hour,
        checked=dt.date.fromisoformat(checked),
        source=source,
    )

    def said(level: LevelResult) -> None:
        s = level.summary
        if s is None:
            typer.echo(f"{model} c={level.concurrency}: every read failed")
            return
        rate = pages_per_second(level, warmup_seconds=warmup)
        typer.echo(
            f"{model} c={level.concurrency}: e2e p50 {s.e2e_p50_ms}, p99 {s.e2e_p99_ms}, "
            f"{rate:.3f} pages/s, {s.errors} errors, {level.retried} retried"
        )

    done = sweep(
        Gateway.from_config(gateway_config, project="legible"),
        requests,
        model=model,
        corpus="+".join(sorted(corpora)),
        price=price,
        out_dir=data_root() / "bench" / model,
        levels=[int(x) for x in levels.split(",")],
        warmup_seconds=warmup,
        on_level=said,
    )
    typer.echo(f"{model}: {len(done.levels)} levels over {done.documents} documents")


#: The README table each headline training set's reads belong to, and the gate spec that
#: decided it.
_CARD_TABLE: dict[str, tuple[str, str]] = {
    "fara-unseen": ("fara-unseen", "legible-fara-unseen"),
    "deepform-unseen": ("deepform-unseen", "legible-deepform-unseen"),
    "cord": ("cord", "legible-cord-test"),
    "nist": ("nist", "legible-nist-test"),
}


def _vrdu_split(dataset: str) -> tuple[str, list[str], list[str]]:
    """A VRDU training set's split file stem, and its valid and test documents."""
    from legible.data.vrdu import headline_split_files, read_split

    corpus = dataset.split("-")[0]
    raw = data_root() / "raw" / "vrdu"
    for level in ("unseen", "mixed"):
        for f in headline_split_files(corpus, level):  # type: ignore[arg-type]
            sp = read_split(corpus, raw / f)  # type: ignore[arg-type]
            template = f"-{sp.template.lower().replace(' ', '_')}" if sp.template else ""
            if f"{corpus}-{level}{template}-s{sp.seed}" == dataset:
                return Path(f).stem, sorted(sp.valid), sorted(sp.test)
    raise typer.BadParameter(f"no split file for {dataset}")


@app.command("cards")
def cards_command(
    out: Path = typer.Option(Path("docs/cards")),
    records: Path | None = typer.Option(
        None, help="Where finished runs' run.json live. Default: the data root's models/."
    ),
) -> None:
    """Write a model card for each seed-0 headline adapter from its records and graded reads."""
    import math

    from legible.cards import (
        CardFacts,
        Measured,
        confidence,
        render,
        training_counts,
    )
    from legible.grade import grade_document, summarise
    from legible.report import (
        ARMS,
        TABLE_SETS,
        Answers,
        answers_for,
        read_gate,
        row,
        selfhosted_answers,
        token_grades,
    )
    from legible.review import review
    from legible.schema.corpora import NIST_SCHEMAS, SCHEMAS
    from legible.train.dataset import read_training_set
    from legible.train.recipe import TrainConfig, chosen
    from legible.train.vision import read_record

    root = data_root()
    record_root = records or root / "models"
    truth = _truths()
    nist_faces = sorted(NIST_SCHEMAS)
    frontier = [a for a in ARMS if a.arm == "a"]
    gates = [read_gate(p) for p in sorted(Path("gate-runs").glob("*/decision.txt"))]

    def unparsed(ids: list[str], answers: Answers | None) -> Interval | None:
        if answers is None:
            return None
        grades = [
            grade_document(
                truth[d].schema,
                d,
                truth[d].record,
                answers.outputs[d],
                page_text=truth[d].text,
                alternatives=truth[d].alternatives,
            )
            for d in ids
            if d in answers.outputs
        ]
        return summarise(grades).unparsed if grades else None

    def run_answers(run_id: str, corpora: list[str], part: str, level: int) -> Answers | None:
        dirs = [
            root / "runs" / "arm-b" / run_id / "p1" / f"level{level}" / c / part for c in corpora
        ]
        found = selfhosted_answers(dirs)
        return found if found.outputs else None

    def measured(label: str, ids: list[str], answers: Answers | None) -> Measured:
        return Measured(row(label, ids, truth, answers), unparsed(ids, answers))

    out.mkdir(parents=True, exist_ok=True)
    written = []
    for table, (readme_table, gate_spec) in _CARD_TABLE.items():
        for size, name in (("2b", "E2B"), ("4b", "E4B")):
            b_arm = next(a for a in ARMS if a.arm == "b" and a.size == size)
            c_arm = next(a for a in ARMS if a.arm == "c" and a.route == f"{size}-it")
            for dataset in TABLE_SETS[table]:
                config: TrainConfig = chosen(size, dataset)  # type: ignore[arg-type]
                run_id = config.run_id
                corpus = "nist" if dataset == "nist" else dataset.split("-")[0]
                corpora = nist_faces if corpus == "nist" else [corpus]
                set_names = nist_faces if corpus == "nist" else [dataset]
                sets = []
                for s in set_names:
                    path = root / "train" / f"{s}.jsonl"
                    key = s if corpus == "nist" else corpus
                    header, rows = read_training_set(path, SCHEMAS[key])
                    sets.append((header, list(rows)))
                counts = training_counts(config, sets)
                record = (
                    read_record(record_root / run_id)
                    if (record_root / run_id / "run.json").exists()
                    else None
                )
                if corpus in {"fara", "deepform"}:
                    stem, dev, test = _vrdu_split(dataset)
                    test_name = (
                        f"the {len(test)} test documents of VRDU's split file `{stem}`, "
                        "templates never seen in training"
                    )
                elif corpus == "cord":
                    dev, test = sorted(part_docs("cord", "dev")), sorted(part_docs("cord", "test"))
                    test_name = f"CORD's {len(test)} test receipts"
                else:
                    dev, test = sorted(part_docs("nist", "dev")), sorted(part_docs("nist", "test"))
                    test_name = f"the {len(test)} NIST test faces every reader reads"
                mine = run_answers(run_id, corpora, "test", 0)
                own = [
                    measured(f"B, Gemma 4 {name} fine-tuned (this adapter)", test, mine),
                    measured(c_arm.label, test, answers_for(root, c_arm, corpora, "test", 0, [])),
                    *(
                        measured(a.label, test, answers_for(root, a, corpora, "test", 0, []))
                        for a in frontier
                    ),
                ]
                frontier_own = [m for m in own if m.row.label.startswith("A,") and m.row.accuracy]
                best = max(
                    frontier_own,
                    key=lambda m: m.row.accuracy.point if m.row.accuracy else 0.0,
                    default=None,
                )
                best_arm = next((a for a in frontier if best and a.label == best.row.label), None)

                def vrdu_union(c: str, level: str) -> list[str]:
                    from legible.data.vrdu import headline_split_files, read_split

                    files = [
                        f
                        for f in headline_split_files(c, level)  # type: ignore[arg-type]
                        if f.endswith("SD_0.json")
                    ]
                    return sorted(
                        {
                            d
                            for f in files
                            for d in read_split(c, root / "raw" / "vrdu" / f).test  # type: ignore[arg-type]
                        }
                    )

                pooled: list[Measured] = []
                gap: list[tuple[str, Row, Row]] = []
                if corpus in {"fara", "deepform"}:
                    unseen_docs, mixed_docs = (
                        vrdu_union(corpus, "unseen"),
                        vrdu_union(corpus, "mixed"),
                    )
                    readers = [b_arm] + ([best_arm] if best_arm else [])
                    for a in readers:
                        unseen_answers = answers_for(
                            root, a, [corpus], "test", 0, [], f"{corpus}-unseen"
                        )
                        u = row(a.label, unseen_docs, truth, unseen_answers)
                        m = row(
                            a.label,
                            mixed_docs,
                            truth,
                            answers_for(root, a, [corpus], "test", 0, [], f"{corpus}-mixed"),
                        )
                        if u.accuracy and m.accuracy:
                            gap.append((a.label, m, u))
                        if corpus == "fara":
                            pooled.append(Measured(u, unparsed(unseen_docs, unseen_answers)))
                levels: tuple[int, ...] = ()
                curve_pages = ""
                curve: dict[str, dict[int, Row]] = {}
                if corpus == "nist":
                    levels = (0, 1, 2, 3, 4)
                    docs = sorted(part_docs("nist", "curve"))
                    curve_pages = f"NIST's {len(docs)} curve pages"
                    me_label = own[0].row.label
                    curve[me_label] = {}
                    for lv in levels:
                        found = run_answers(run_id, corpora, "test" if lv == 0 else "curve", lv)
                        if found is not None:
                            curve[me_label][lv] = row(me_label, docs, truth, found)
                    if best_arm is not None:
                        curve[best_arm.label] = {}
                        for lv in levels:
                            fa = answers_for(
                                root, best_arm, corpora, "test" if lv == 0 else "curve", lv, []
                            )
                            if fa is not None:
                                curve[best_arm.label][lv] = row(best_arm.label, docs, truth, fa)
                elif corpus in {"fara", "deepform"}:
                    levels = (0, 2, 4)
                    docs = sorted(part_docs(corpus, "vrdu_curve") & set(test))
                    curve_pages = (
                        f"the {len(docs)} of its test documents in the VRDU curve subset, real "
                        "scans"
                    )
                    me_label = own[0].row.label
                    curve[me_label] = {}
                    for lv in levels:
                        found = run_answers(
                            run_id, corpora, "test" if lv == 0 else "vrdu_curve", lv
                        )
                        if found is not None:
                            curve[me_label][lv] = row(me_label, docs, truth, found)
                seeds = []
                for seed in (1, 2):
                    other = (
                        dataset.removesuffix("-s0") + f"-s{seed}"
                        if dataset.endswith("-s0")
                        else dataset
                    )
                    if corpus in {"fara", "deepform"}:
                        _, _, other_test = _vrdu_split(other)
                    else:
                        other_test = test
                    oid = chosen(size, other, seed=seed).run_id  # type: ignore[arg-type]
                    r = row(f"seed {seed}", other_test, truth, run_answers(oid, corpora, "test", 0))
                    if r.accuracy:
                        seeds.append((seed, r))
                gate = [g for g in gates if g.name.startswith(gate_spec + "-")]
                gated_size = next(
                    (
                        s
                        for g in gate
                        for s in ("2b", "4b")
                        if g.name.startswith(f"{gate_spec}-{s}-")
                    ),
                    None,
                )
                lp = f"{run_id}@logprobs"
                dev_g = token_grades(
                    dev,
                    truth,
                    [root / "runs" / "arm-b" / lp / "p1" / "level0" / c / "dev" for c in corpora],
                )
                test_g = token_grades(
                    test,
                    truth,
                    [root / "runs" / "arm-b" / lp / "p1" / "level0" / c / "test" for c in corpora],
                )
                conf = (
                    confidence(dev_g, review(dev_g, test_g) if test_g else None) if dev_g else None
                )
                facts = CardFacts(
                    run_id=run_id,
                    config=config,
                    table=readme_table,
                    schemas=[SCHEMAS[k] for k in (nist_faces if corpus == "nist" else [corpus])],
                    prompt_version=sets[0][0].prompt_version,
                    counts=counts,
                    record=record,
                    test_name=test_name,
                    own=own,
                    pooled=pooled,
                    gap=gap,
                    curve_levels=levels,
                    curve_pages=curve_pages,
                    curve=curve,
                    seeds=seeds,
                    gate=gate,
                    gated_size=gated_size,
                    confidence=conf,
                )
                path = out / f"{run_id}.md"
                path.write_text(render(facts), encoding="utf-8", newline="\n")
                acc = own[0].row.accuracy
                written.append(
                    f"{path}: {100 * acc.point:.1f}%"
                    if acc and not math.isnan(acc.point)
                    else str(path)
                )
    typer.echo("\n".join(written))


@app.command("publish")
def publish_command(
    adapter: Path = typer.Argument(..., help="A finished run's adapter directory."),
    repo: str | None = typer.Option(
        None, help="The Hub repository. Default: legible-<run id> under the token's account."
    ),
    cards: Path = typer.Option(Path("docs/cards")),
    public: bool = typer.Option(False, "--public", help="Create the repository public."),
) -> None:
    """Upload one adapter with its card to the Hugging Face Hub, private unless --public.
    Reads the token from HF_TOKEN; refuses without a card for the run."""
    import json as _json

    from legible.publish import HubUploader, PublishRefused, publish

    record = adapter / "run.json"
    run_id = (
        _json.loads(record.read_text(encoding="utf-8")).get("run_id") if record.exists() else None
    )
    card = cards / f"{run_id or adapter.parent.name}.md"
    try:
        from legible.publish import check

        check(adapter, card)
        done = publish(
            adapter, card, repo or f"legible-{run_id}", HubUploader(), private=not public
        )
    except PublishRefused as refused:
        typer.echo(f"refused: {refused}", err=True)
        raise typer.Exit(1) from refused
    typer.echo(
        f"{done.repo_id} ({'private' if done.private else 'public'}): {len(done.files)} files, "
        f"card sha256 {done.card_sha256}, {done.commit_url}"
    )


def main() -> None:
    app()


verify_app = typer.Typer(
    no_args_is_help=True, help="The verifier's rules (legible/verify_rules.py)."
)
app.add_typer(verify_app, name="verify")


@verify_app.command("hold")
def verify_hold(
    out: Path = typer.Option(Path("docs/verify-rules.md"), help="Where the table is written."),
) -> None:
    """How often each rule holds on the training split's own truth. A rule the truth breaks
    would flag right fields, so a rule is kept only if it holds on 99% of the documents it
    applies to (a sum with its total filled in, a date or pattern field with a value)."""
    from legible.schema.corpora import NIST_SCHEMAS, SCHEMAS
    from legible.verify import applies, check_rules, flagged
    from legible.verify_rules import REJECTED, RULES

    truth = _truths()
    schemas = {**SCHEMAS, **NIST_SCHEMAS}
    train = (
        part_docs("fara", "train") | part_docs("deepform", "train") | part_docs("cord", "train")
    ) | part_docs("nist", "train")
    lines = [
        "# The verifier's rules against the training truth",
        "",
        "Written by `legible verify hold`; do not edit. Each rule in `legible/verify_rules.py`, "
        "how many training documents it applies to, and on how many the corpus's own answers "
        "satisfy it. A rule is kept at 99% or more.",
        "",
        "| Corpus | Rule | Applies to | Holds on | Run |",
        "|---|---|---:|---:|---|",
    ]
    measured = [(c, r, "yes") for c, rs in RULES.items() for r in rs] + [
        (c, r, "no: below 99%") for c, rs in REJECTED.items() for r in rs
    ]
    for corpus, rules, kept in [(c, (r,), k) for c, r, k in measured]:
        schema = schemas[corpus]
        check_rules(schema, rules)
        docs = [d for d in sorted(train) if d in truth and truth[d].schema.corpus == corpus]
        for rule in rules:
            applying = [d for d in docs if applies(rule, truth[d].record)]
            holds = sum(1 for d in applying if not flagged(schema, (rule,), truth[d].record))
            share = f"{100 * holds / len(applying):.1f}%" if applying else "none apply"
            lines.append(
                f"| {corpus} | {rule.name} | {len(applying)} | {holds} ({share}) | {kept} |"
            )
    out.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    typer.echo("\n".join(lines))
