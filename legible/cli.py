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
    from collections.abc import Mapping, Sequence

    from legible.arms.read_run import RunSpec
    from legible.bench.run import LoadRun
    from legible.prompt import Prompt
    from legible.report import Row, Truth

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


@app.command("report")
def report_command(readme: Path = typer.Option(Path("README.md"))) -> None:
    """Grade every arm's stored test reads and write the README's result tables."""
    from legible.data.vrdu import headline_split_files, read_split
    from legible.report import (
        ARMS,
        PRICE_LIST_DATE,
        answers_for,
        curve,
        row,
        splice,
        table,
    )
    from legible.schema.corpora import NIST_SCHEMAS

    root, raw = data_root(), data_root() / "raw"
    truth = _truths()

    e_dir = root / "runs" / "arm-e"

    def vrdu_rows(corpus: str, level: str) -> list[Row]:
        files = [f for f in headline_split_files(corpus, level) if f.endswith("SD_0.json")]  # type: ignore[arg-type]
        docs = sorted({d for f in files for d in read_split(corpus, raw / "vrdu" / f).test})  # type: ignore[arg-type]
        rules = [e_dir / "level0" / corpus / f"{Path(f).stem}-test.jsonl" for f in files]
        return [
            row(
                a.label,
                docs,
                truth,
                answers_for(root, a, [corpus], "test", 0, rules, f"{corpus}-{level}"),
            )
            for a in ARMS
        ]

    nist_faces = sorted(NIST_SCHEMAS)
    nist_test = sorted(part_docs("nist", "test"))
    cord_test = sorted(part_docs("cord", "test"))
    body = [
        "Test sets, read once per arm, level 0 unless stated. Field accuracy is VRDU's own "
        "matchers, one grader for every arm; intervals are 95% bootstrap over documents. "
        f"Frontier cost is the gateway ledger's at the {PRICE_LIST_DATE} price list, batch "
        "rate; OCR is costed at US$0.03 per vCPU-hour (RunPod, 2026-10-17). Written by "
        "`legible report`; do not edit.",
        "",
    ]
    headline: dict[str, list[Row]] = {
        "fara": vrdu_rows("fara", "unseen"),
        "deepform": vrdu_rows("deepform", "unseen"),
    }
    body += table(
        "FARA registration forms, templates never seen in training (headline)", headline["fara"]
    )
    body += table(
        "DeepForm ad-buy forms, templates never seen in training (headline)",
        headline["deepform"],
    )
    headline["cord"] = [
        row(
            a.label,
            cord_test,
            truth,
            answers_for(
                root, a, ["cord"], "test", 0, [e_dir / "level0" / "cord" / "test.jsonl"], "cord"
            ),
        )
        for a in ARMS
    ]
    body += table("CORD receipts, test set", headline["cord"])
    headline["nist"] = [
        row(
            a.label,
            nist_test,
            truth,
            answers_for(
                root, a, nist_faces, "test", 0, [e_dir / "level0" / "nist" / "test.jsonl"], "nist"
            ),
        )
        for a in ARMS
    ]
    body += table("NIST tax forms, 500 test faces", headline["nist"])
    body += table(
        "FARA, templates seen in training (the gap beside the headline)", vrdu_rows("fara", "mixed")
    )
    body += table(
        "DeepForm, templates seen in training (the gap beside the headline)",
        vrdu_rows("deepform", "mixed"),
    )
    curve_docs = sorted(part_docs("nist", "curve"))
    cells: dict[str, dict[int, Row]] = {}
    for a in ARMS:
        cells[a.label] = {}
        for lv in range(5):
            part = "test" if lv == 0 else "curve"
            rules = [e_dir / f"level{lv}" / "nist" / f"{part}.jsonl"]
            found = answers_for(root, a, nist_faces, part, lv, rules, "nist")
            if found is not None:
                cells[a.label][lv] = row(a.label, curve_docs, truth, found)
    body += [
        "**NIST, the 300 curve pages at each degradation level** (fields correct; what each "
        "level does to OCR is in [docs/degradation.md](docs/degradation.md))",
        "",
        *curve(range(5), cells),
    ]
    for c, name in (("fara", "FARA"), ("deepform", "DeepForm")):
        sub = sorted(part_docs(c, "vrdu_curve"))
        files = [f for f in headline_split_files(c, "unseen") if f.endswith("SD_0.json")]  # type: ignore[arg-type]
        vcells: dict[str, dict[int, Row]] = {}
        for a in ARMS:
            vcells[a.label] = {}
            for lv in (0, 2, 4):
                # Level 0 is the subset's share of the test reads; 2 and 4 the subset itself.
                part = "test" if lv == 0 else "vrdu_curve"
                rules = (
                    [e_dir / "level0" / c / f"{Path(f).stem}-test.jsonl" for f in files]
                    if lv == 0
                    else [
                        e_dir / f"level{lv}" / c / f"{Path(f).stem}-vrdu_curve.jsonl" for f in files
                    ]
                )
                found = answers_for(root, a, [c], part, lv, rules, f"{c}-unseen")
                if found is not None:
                    vcells[a.label][lv] = row(a.label, sub, truth, found)
        body += [
            f"**{name}, the {len(sub)} unseen-template test documents of the VRDU curve subset "
            "at levels 0, 2 and 4** (fields correct; real scans beside the NIST curve)",
            "",
            *curve((0, 2, 4), vcells),
        ]
    from legible.report import verifier_cell

    fara_files = [f for f in headline_split_files("fara", "unseen") if f.endswith("SD_0.json")]
    fara_test = sorted({d for f in fara_files for d in read_split("fara", raw / "vrdu" / f).test})
    fara_rules = [e_dir / "level0" / "fara" / f"{Path(f).stem}-test.jsonl" for f in fara_files]
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
    from legible.report import gate_table, read_gate

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
    from legible.report import agreed_grades, review_table
    from legible.review import review

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

    def vrdu_ids(corpus: str, level: str, attr: str) -> list[str]:
        files = [f for f in headline_split_files(corpus, level) if f.endswith("SD_0.json")]  # type: ignore[arg-type]
        splits = [read_split(corpus, raw / "vrdu" / f) for f in files]  # type: ignore[arg-type]
        return sorted({d for sp in splits for d in getattr(sp, attr)})

    body += [
        "**Review at 99%: Sonnet 5.5 on the image, each field checked against Sonnet 5.5 on the "
        "OCR text.** A field is accepted when the two reads agree; the threshold is chosen on "
        "dev and applied once to test (legible/review.py, legible/agreement.py).",
        "",
        *review_table(
            [
                (
                    "FARA, unseen templates",
                    review_for(
                        ["fara"],
                        vrdu_ids("fara", "unseen", "valid"),
                        vrdu_ids("fara", "unseen", "test"),
                    ),
                ),
                (
                    "DeepForm, unseen templates",
                    review_for(
                        ["deepform"],
                        vrdu_ids("deepform", "unseen", "valid"),
                        vrdu_ids("deepform", "unseen", "test"),
                    ),
                ),
                ("CORD", review_for(["cord"], sorted(part_docs("cord", "dev")), cord_test)),
                ("NIST", review_for(nist_faces, sorted(part_docs("nist", "dev")), nist_test)),
            ]
        ),
    ]
    from legible.report import TABLE_SETS, TOKEN_MISS, token_grades
    from legible.train.recipe import chosen

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
        body += [
            f"**Review at 99%: Gemma 4 {name} fine-tuned (seed 0), each field's confidence the "
            "lowest probability among the tokens of its value.** Read a second time with "
            "log-probabilities for this table (PLAN.md 2.6); the threshold is chosen on that dev "
            "read and applied once to its test read (legible/tokenconf.py).",
            "",
            *review_table(
                [
                    (
                        "FARA, unseen templates",
                        token_review(
                            size,
                            "fara-unseen",
                            ["fara"],
                            vrdu_ids("fara", "unseen", "valid"),
                            vrdu_ids("fara", "unseen", "test"),
                        ),
                    ),
                    (
                        "DeepForm, unseen templates",
                        token_review(
                            size,
                            "deepform-unseen",
                            ["deepform"],
                            vrdu_ids("deepform", "unseen", "valid"),
                            vrdu_ids("deepform", "unseen", "test"),
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
            ),
        ]
    body += _serving_section(root, headline)
    body += [
        "Arms B and C read through vLLM on an RTX 3090 at temperature 0, unconstrained (held "
        "to the schema's grammar, the fine-tunes left their trained format: docs/training.md), "
        "and are costed at the GPU's US$0.50 an hour on RunPod (2026-10-18) over the measured "
        "wall time of each read pass. "
        "B's row is seed 0, the model trained for that table's split; seeds 1 and 2 are "
        "the training variance. Latency is the fine-tunes' alone: the frontier models were "
        "read in batches, whose only latency is the batch's (docs/serving.md).",
    ]
    text = readme.read_text(encoding="utf-8")
    readme.write_text(splice(text, body), encoding="utf-8", newline="\n")
    typer.echo("\n".join(body))


#: The corpus a load-tested fine-tune's run id names, and how the tables call it.
_BENCH_CORPORA = {
    "fara": "FARA",
    "deepform": "DeepForm",
    "cord": "CORD",
    "nist": "NIST",
}


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
        "the first 30 seconds of each level are discarded.",
        "",
        *latency_table([(label(m), runs[m]) for m in ordered]),
    ]
    frontier = [a for a in ARMS if a.arm == "a"]
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
            (a.label.removeprefix("A, ").removesuffix(" on the image"), r.per_thousand.point / 1000)
            for a in frontier
            if (r := rows.get(a.label)) is not None and r.per_thousand is not None
        ]
        out += [
            f"**Break-even, {name}: pages a month at which renting the card for the {label(model)} "
            "fine-tune costs no more than paying each frontier model by the page**, over the "
            "share of the month the card is kept busy. 06's arithmetic (legible/bench/"
            "breakeven.py): whole cards rented all month, a month of 730.5 hours, no fixed "
            "costs, the fine-tune at its best measured throughput and each frontier model at "
            "its headline test cost. It says nothing about accuracy, which the tables above "
            "do.",
            "",
            *breakeven_table(runs[model], api),
        ]
    return out


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
    from legible.train.checkpoint import CheckpointStore, runpod_s3
    from legible.train.dataset import TrainingHeader, read_training_set
    from legible.train.recipe import chosen
    from legible.train.vision import describe, train

    # "nist" is the twenty faces' sets read as one: one model for the form family, each face
    # asked with its own prompt.
    names = [k for k in _nist_keys()] if dataset == "nist" else [dataset]
    headers: list[TrainingHeader] = []
    examples = []
    for name in names:
        path = data_root() / "train" / f"{name}.jsonl"
        with path.open(encoding="utf-8") as f:
            key = TrainingHeader.model_validate_json(f.readline()).corpus
        header, rows = read_training_set(path, SCHEMAS[key])
        headers.append(header)
        examples += [(header.instruction, r) for r in rows]
    if dataset == "nist":
        # Faces interleaved in a fixed order, so a step sees every form and a volume cut
        # takes some of each.
        import hashlib

        examples.sort(key=lambda e: hashlib.sha256(e[1].doc_id.encode()).hexdigest())
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
) -> None:
    """The reads a model trained on this set owes: one `corpus split part level` a line
    ("-" for no split file), dev before test. A VRDU model reads its own split file's dev
    and test documents, and the seed-0 unseen-template model its test documents in the VRDU
    curve subset at levels 2 and 4; CORD's its test set; NIST's the twenty faces' dev, test
    and curve."""
    typer.echo("\n".join(_owed_reads(dataset)))


def _owed_reads(dataset: str) -> list[str]:
    """`serve reads`, as a list."""
    from legible.data.vrdu import headline_split_files, read_split

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
    from legible.stats import Interval
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
