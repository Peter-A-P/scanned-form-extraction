"""Writing the demo site: page images, each arm's graded reads of them, and the tables.

`legible site` gathers the runs (the same ones `legible report` reads) and calls into this
module, which does three things and nothing else:

- **Grades with the project's grader.** Each arm's read of a shown page is graded by
  `legible.grade.grade_document` exactly as the report grades it, and every field's outcome
  goes into the JSON as the grader returned it: the value read, the truth, right or wrong.
  The browser draws those flags; it never compares a value itself.
- **Places each field on the page** where the corpus says it is printed: VRDU's entity boxes
  for DeepForm, CORD's word quads, and for NIST the field zones arm E learned from the
  training pages (`legible/arms/nist_zones.json`), registered to the page by its own OCR. On
  a degraded page the box is turned by the skew `legible.degrade` applied. A field with no
  location is listed beside the page instead of drawn.
- **Serialises the tables** from `legible.report.Results`, the object the README's tables
  are formatted from, with the report's own cell text, so the two cannot disagree.

Registration forms (FARA) name individuals and are never shown as images: an image of any
corpus outside `SHOWN` is refused where it would be made, and the finished directory is
checked once more before the build reports success.
"""

from __future__ import annotations

import io
import json
import math
import random
import shutil
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from PIL import Image

from legible.arms.ocr import OcrPage
from legible.arms.zonal import FaceRules, register, to_page
from legible.bench.run import LoadRun
from legible.bench.tables import best_throughput, throughput
from legible.data.render import PageEntry
from legible.degrade import degrade, skew_angle
from legible.grade import DocGrade, FieldOutcome, grade_document
from legible.report import (
    ARMS,
    Arm,
    Curve,
    GateResult,
    Results,
    ReviewTable,
    Row,
    Table,
    Truth,
    pct,
    price_date,
    review_cells,
    usd,
)
from legible.stats import Interval

#: The corpora whose pages may be shown: NIST's synthesised tax forms, CORD's receipts
#: (CC BY 4.0) and DeepForm's ad-buy forms (FCC public files). FARA's registration forms
#: name individuals and appear in the tables only (PLAN.md 2.8).
SHOWN: Final = ("nist", "cord", "deepform")
#: Pages shown per corpus, drawn from sorted ids with a fixed seed, never by how an arm did.
PER_CORPUS: Final = 8
SEED: Final = 16
#: A shown image's width in pixels, its JPEG quality, and the most pages of one document shown.
MAX_WIDTH: Final = 1000
JPEG_QUALITY: Final = 62
MAX_PAGES: Final = 2
#: The files in this directory that are the site itself, copied into the output.
ASSETS: Final = (
    "index.html",
    "architecture.html",
    "app.js",
    "breakeven.js",
    "style.css",
    "staticwebapp.config.json",
    "robots.txt",
    "fonts/LICENSE.txt",
    "fonts/inter-latin.woff2",
    "fonts/newsreader-latin.woff2",
)
#: The four diagrams of docs/architecture.md, shown on the site's architecture page. Copied
#: from the docs at build time so the two cannot differ.
DIAGRAMS: Final = ("system.svg", "five-arms.svg", "train-serve.svg", "evaluation.svg")
SOURCE: Final = Path(__file__).parent
DIAGRAM_SOURCE: Final = SOURCE.parents[1] / "docs" / "architecture"
IMAGE_SUFFIXES: Final = frozenset({".jpg", ".jpeg", ".png", ".webp", ".gif", ".svg", ".bmp"})

#: (page, x1, y1, x2, y2), corners as shares of the page's width and height.
Box = tuple[int, float, float, float, float]


class RegistrationImage(ValueError):
    """A page of a corpus the site may not show (a FARA registration form) was about to be
    written, or was found in the output."""


def family(corpus: str) -> str:
    """NIST's twenty faces (`nist_1040_1`) are one corpus to the site."""
    return "nist" if corpus.startswith("nist") else corpus


def refuse_unshown(corpus: str) -> None:
    if family(corpus) not in SHOWN:
        raise RegistrationImage(
            f"{corpus} pages are never shown as images (PLAN.md 2.8); only {', '.join(SHOWN)}"
        )


def choose(ids: Iterable[str], n: int = PER_CORPUS, seed: int = SEED) -> list[str]:
    """A fixed draw of `n` ids: sorted first, so the draw depends only on the set."""
    pool = sorted(set(ids))
    return sorted(random.Random(seed).sample(pool, min(n, len(pool))))


def slug(corpus: str, doc_id: str) -> str:
    return f"{family(corpus)}-{Path(doc_id).stem}"


# --- Where each field is printed ------------------------------------------------------------


def box_key(o: FieldOutcome) -> str | None:
    """The truth box an outcome is drawn at, keyed as the loaders key boxes (`field`, or
    `group[i].field` with i the truth item). A value the truth does not carry (a filled
    blank, an extra line item) has no place on the page."""
    if o.truth is None:
        return None
    if "." in o.path and o.index is not None:
        group, sub = o.path.split(".", 1)
        return f"{group}[{o.index}].{sub}"
    return o.path


def _clamp(v: float) -> float:
    return min(1.0, max(0.0, v))


def nist_boxes(page: OcrPage, rules: FaceRules) -> dict[str, Box]:
    """A NIST page's field zones on the page: the face's learned zones, moved by how this
    page sits against the face's frame (registered by its own level-0 OCR, as arm E reads)."""
    t = register(page, rules.anchors)
    out: dict[str, Box] = {}
    for name, zone in rules.zones.items():
        x1, y1, x2, y2 = to_page(zone.box, t)
        out[name] = (0, _clamp(x1), _clamp(y1), _clamp(x2), _clamp(y2))
    return out


def turn_box(box: Box, angle: float, width: int, height: int) -> Box:
    """A box on the clean page, on the page turned `angle` degrees counter-clockwise about
    its centre (PIL's `rotate`, as `degrade` does): the bounding box of its turned corners."""
    if angle == 0.0:
        return box
    page, x1, y1, x2, y2 = box
    a = math.radians(angle)
    cx, cy = width / 2, height / 2
    xs: list[float] = []
    ys: list[float] = []
    for x, y in ((x1, y1), (x2, y1), (x1, y2), (x2, y2)):
        dx, dy = x * width - cx, y * height - cy
        xs.append((cx + dx * math.cos(a) + dy * math.sin(a)) / width)
        ys.append((cy - dx * math.sin(a) + dy * math.cos(a)) / height)
    return (page, _clamp(min(xs)), _clamp(min(ys)), _clamp(max(xs)), _clamp(max(ys)))


# --- Page images ----------------------------------------------------------------------------


def page_image(root: Path, entry: PageEntry, level: int) -> Image.Image:
    """The page as the arms were sent it at a level: the rendered page, or its degraded copy
    under the data root. A copy not stored is made in memory, never written there."""
    refuse_unshown(entry.corpus)
    source = root / "pages" / entry.path
    if level == 0:
        return Image.open(source)
    stored = root / "degraded" / f"level{level}" / entry.path
    if stored.exists():
        return Image.open(stored)
    with Image.open(source) as img:
        return degrade(img, f"{entry.corpus}/{entry.path}", level)


def jpeg(image: Image.Image, max_width: int = MAX_WIDTH, quality: int = JPEG_QUALITY) -> bytes:
    """A small JPEG of a page for the browser, no metadata."""
    img = image.convert("L") if image.mode in {"1", "L", "P", "I", "I;16"} else image
    img = img.convert("L") if img.mode == "L" else img.convert("RGB")
    if img.width > max_width:
        img = img.resize(
            (max_width, max(1, round(img.height * max_width / img.width))),
            Image.Resampling.LANCZOS,
        )
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=quality, optimize=True, progressive=True)
    return buffer.getvalue()


# --- Reads, graded --------------------------------------------------------------------------


def field_reads(grade: DocGrade) -> list[dict[str, Any]]:
    """Every scored field of one graded read, as the grader decided it."""
    return [
        {
            "key": box_key(o),
            "path": o.path,
            "item": o.index if o.truth is not None else None,
            "truth": o.truth,
            "read": o.predicted,
            "outcome": o.outcome.value,
            "correct": o.correct,
        }
        for o in grade.outcomes
    ]


def graded(truth: Truth, doc_id: str, output: Any) -> DocGrade:
    """One read graded exactly as `legible.report.row` grades it."""
    return grade_document(
        truth.schema,
        doc_id,
        truth.record,
        output,
        page_text=truth.text,
        alternatives=truth.alternatives,
    )


def arm_read(truth: Truth, doc_id: str, outputs: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """One arm's read of one page at one level, graded; None when the arm has not read it."""
    if outputs is None or doc_id not in outputs:
        return None
    g = graded(truth, doc_id, outputs[doc_id])
    return {
        "correct": g.correct,
        "scored": g.scored,
        "unparsed": g.unparsed,
        "fields": field_reads(g),
    }


def labels(truth: Truth) -> dict[str, str]:
    """Each field path's description from the schema, for the side panel."""
    out: dict[str, str] = {}
    for f in truth.schema.fields:
        sub = getattr(f, "fields", None)
        if sub is None:
            out[f.name] = f.description
        else:
            for g in sub:
                out[f"{f.name}.{g.name}"] = f"{f.description} {g.description}"
    return out


def page_record(
    *,
    corpus: str,
    doc_id: str,
    entries: Sequence[PageEntry],
    truth: Truth,
    boxes: Mapping[str, Box],
    levels: Sequence[int],
    reads: Mapping[int, Mapping[str, Mapping[str, Any] | None]],
    images: Mapping[int, Sequence[str]],
    arms: Sequence[Arm] = ARMS,
) -> dict[str, Any]:
    """Everything the page viewer shows for one document: its images at each level, where
    each field is at each level, and each arm's graded read at each level. `reads` maps a
    level to each arm's outputs by document (None for an arm with no run at that level)."""
    refuse_unshown(corpus)
    shown = list(entries)[:MAX_PAGES]
    by_level: dict[str, dict[str, Box]] = {}
    for lv in levels:
        placed: dict[str, Box] = {}
        for key, b in boxes.items():
            if b[0] >= len(shown):
                continue
            e = shown[b[0]]
            placed[key] = turn_box(b, skew_angle(f"{e.corpus}/{e.path}", lv), e.width, e.height)
        by_level[str(lv)] = placed
    return {
        "id": slug(corpus, doc_id),
        "corpus": family(corpus),
        "doc": doc_id,
        "pages": [{"width": e.width, "height": e.height} for e in shown],
        "pages_total": len(entries),
        "levels": list(levels),
        "images": {str(lv): list(images[lv]) for lv in levels},
        "labels": labels(truth),
        "boxes": by_level,
        "reads": {
            str(lv): {a.label: arm_read(truth, doc_id, reads[lv].get(a.label)) for a in arms}
            for lv in levels
        },
    }


def write_images(
    root: Path, entries: Sequence[PageEntry], levels: Sequence[int], out: Path
) -> dict[int, list[str]]:
    """Each shown page of a document at each level, as `img/<slug>-p<page>-l<level>.jpg`."""
    names: dict[int, list[str]] = {}
    (out / "img").mkdir(parents=True, exist_ok=True)
    for lv in levels:
        names[lv] = []
        for e in list(entries)[:MAX_PAGES]:
            refuse_unshown(e.corpus)
            name = f"img/{slug(e.corpus, e.doc_id)}-p{e.page:02d}-l{lv}.jpg"
            with page_image(root, e, lv) as img:
                (out / name).write_bytes(jpeg(img))
            names[lv].append(name)
    return names


# --- The tables -----------------------------------------------------------------------------


def interval(i: Interval | None) -> dict[str, float | int] | None:
    if i is None or not all(math.isfinite(v) for v in (i.point, i.low, i.high)):
        return None
    return {"point": i.point, "low": i.low, "high": i.high, "n": i.n}


def row_json(r: Row, arm: Arm) -> dict[str, Any]:
    return {
        "arm": r.label,
        "documents": r.documents,
        "missing": r.missing,
        "accuracy": interval(r.accuracy),
        "accuracy_text": pct(r.accuracy),
        "all_right": interval(r.all_right),
        "all_right_text": pct(r.all_right) if r.all_right else "",
        "invented": interval(r.invented),
        "invented_text": pct(r.invented) if r.invented else "",
        "per_thousand": interval(r.per_thousand),
        "per_thousand_text": usd(r.per_thousand),
        "price_date": price_date(arm) if r.per_thousand is not None else "",
    }


def table_json(t: Table, arms: Sequence[Arm] = ARMS) -> dict[str, Any]:
    by_label = {a.label: a for a in arms}
    return {
        "key": t.key,
        "title": t.title,
        "rows": [row_json(r, by_label[r.label]) for r in t.rows],
    }


def curve_json(c: Curve) -> dict[str, Any]:
    return {
        "key": c.key,
        "title": c.title,
        "levels": list(c.levels),
        "documents": c.documents,
        "cells": {
            label: {
                str(lv): {"accuracy": interval(r.accuracy), "text": pct(r.accuracy)}
                for lv, r in by_level.items()
            }
            for label, by_level in c.cells.items()
        },
    }


def review_json(t: ReviewTable) -> dict[str, Any]:
    rows = []
    for label, r in t.rows:
        sent, accepted, dev = review_cells(r, t.miss)
        rows.append(
            {
                "corpus": label,
                "review_rate": interval(r.review_rate) if r is not None else None,
                "sent_text": sent,
                "accepted_text": accepted,
                "dev_text": dev,
            }
        )
    return {"title": t.title, "note": t.note, "rows": rows}


def results_json(results: Results) -> dict[str, Any]:
    return {
        "arms": [arm_json(a) for a in ARMS],
        "tables": [table_json(t) for t in results.tables],
        "curves": [curve_json(c) for c in results.curves],
        "reviews": [review_json(t) for t in results.reviews],
    }


# --- The story around the tables -----------------------------------------------------------
#
# The front page leads with what the tables mean rather than with the tables, so it needs a
# little more than they hold: what kind of reader each arm is, the load test, the training
# records, the gate's verdicts, the ceiling and the noise floor, and how many pages were read
# in all. Every one of these is serialised from a record the project wrote; the browser only
# picks among them and draws.

#: What kind of reader each arm is, which decides its colour and its mark on every chart.
ARM_KIND: Final = {
    "a": "frontier",
    "b": "finetuned",
    "c": "untuned",
    "d": "ocr-llm",
    "e": "ocr-rules",
    "f": "managed",
}


def arm_short(label: str) -> str:
    """An arm's name without its letter and its input: "Claude Sonnet 5.5"."""
    name = label.split(", ", 1)[1] if ", " in label else label
    if name.endswith(" on the OCR text"):
        return name.removesuffix(" on the OCR text") + " on OCR text"
    return name.removesuffix(" on the image")


def arm_json(a: Arm) -> dict[str, Any]:
    return {
        "label": a.label,
        "arm": a.arm,
        "short": arm_short(a.label),
        "kind": ARM_KIND[a.arm],
        "size": a.size,
        "price_date": price_date(a),
    }


def _measured(m: Any, scale: float = 1.0) -> dict[str, float] | None:
    """A load-test `Measured` (06's), in the unit asked for."""
    if m is None:
        return None
    return {"point": m.point * scale, "low": m.low * scale, "high": m.high * scale}


def serving_json(runs: Mapping[str, LoadRun], gated: Mapping[str, str]) -> list[dict[str, Any]]:
    """The load test, one entry a served fine-tune: each level's reads, pages a second with
    its interval (`legible.bench.tables.throughput`, the README's), and latency in seconds.
    `gated` maps a corpus to the size the gate compared, the one the break-even is for."""
    out = []
    for model, run in runs.items():
        size, corpus = model.split("-")[0], model.split("-")[1]
        levels: list[dict[str, Any]] = []
        for lv in sorted(run.levels, key=lambda lv: lv.concurrency):
            s = lv.summary
            if s is None:
                levels.append({"concurrency": lv.concurrency, "reads": 0, "errors": None})
                continue
            rate = throughput(lv, warmup_seconds=run.warmup_seconds)
            levels.append(
                {
                    "concurrency": lv.concurrency,
                    "reads": s.requests,
                    "errors": s.errors,
                    "pages_per_read": sum(lv.pages) / len(lv.pages) if lv.pages else None,
                    "pages_per_second": _measured(rate),
                    "read_p50_s": _measured(s.e2e_p50_ms, 1 / 1000),
                    "read_p99_s": _measured(s.e2e_p99_ms, 1 / 1000),
                    "first_token_p50_s": _measured(s.ttft_p50_ms, 1 / 1000),
                }
            )
        best = best_throughput(run)
        out.append(
            {
                "model": model,
                "size": size,
                "corpus": corpus,
                "gated": gated.get(corpus) == size,
                "gpu": run.price.gpu,
                "usd_per_hour": run.price.usd_per_hour,
                "provider": run.price.provider,
                "checked": run.price.checked.isoformat(),
                "levels": levels,
                "best": {"concurrency": best[0], "pages_per_second": _measured(best[1])}
                if best
                else None,
            }
        )
    return out


#: The Hub account the adapters are under (docs/models.md). FARA's stay private: the
#: registration forms name individuals.
HUB: Final = "https://huggingface.co/Peter-A-P"


def hub_url(run_id: str) -> str | None:
    """The public repository of an adapter, or None for the private FARA ones."""
    return None if "fara" in run_id else f"{HUB}/legible-{run_id}"


def training_json(records: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Each headline adapter's training record (`run.json`, written by `legible train run`):
    the recipe, the set's size, the steps and how long they took."""
    import datetime as dt

    out = []
    for r in records:
        c = r["config"]
        started = dt.datetime.fromisoformat(r["started_at"].replace("Z", "+00:00"))
        finished = dt.datetime.fromisoformat(r["finished_at"].replace("Z", "+00:00"))
        out.append(
            {
                "run_id": r["run_id"],
                "size": c["size"],
                "dataset": c["dataset"],
                # The documents it trained on: the set less any left out for length, and no
                # more than its steps saw (NIST's run reads the first 800 of its set).
                "documents": min(
                    sum(int(d.get("rows", 0)) for d in r["datasets"]) - int(r.get("left_out", 0)),
                    int(r["steps"]) * int(c["grad_accum"]),
                ),
                "left_out": r.get("left_out", 0),
                "steps": r["steps"],
                "seconds_per_step": r["seconds_per_step"],
                "minutes": (finished - started).total_seconds() / 60,
                "train_loss": r["train_loss"],
                "rank": c["rank"],
                "alpha": c["alpha"],
                "learning_rate": c["learning_rate"],
                "epochs": c["epochs"],
                "visual_tokens": c["visual_tokens"],
                "max_seq_len": c["max_seq_len"],
                "grad_accum": c["grad_accum"],
                "hub": hub_url(r["run_id"]),
            }
        )
    return sorted(out, key=lambda t: (str(t["dataset"]), str(t["size"])))


def gate_json(results: Sequence[GateResult]) -> list[dict[str, Any]]:
    """The 03 gate's decisions, as `read_gate` parsed them."""
    return [
        {
            "name": g.name,
            "candidate": g.candidate,
            "baseline": g.baseline,
            "verdict": g.verdict.lower(),
            "pass": g.counts.get("pass", 0),
            "block": g.counts.get("block", 0),
            "underpowered": g.counts.get("warn", 0),
            "blocks": [{"field": f, "difference": d} for f, d in g.blocks[:3]],
        }
        for g in results
    ]


def subset_json(rows: Sequence[Any]) -> list[dict[str, Any]]:
    """The ceiling or the noise floor, a row a corpus (`legible.cli._Subset`)."""
    return [
        {
            "corpus": r.corpus,
            "documents": r.documents - r.missing,
            "first": interval(r.first.accuracy),
            "first_text": pct(r.first.accuracy),
            "first_cost": interval(r.first.per_thousand),
            "second": interval(r.second.accuracy),
            "second_text": pct(r.second.accuracy),
            "second_cost": interval(r.second.per_thousand),
            "changed": interval(r.changed),
            "changed_text": pct(r.changed) if r.changed is not None else "",
        }
        for r in rows
    ]


def ablation_json(ablations: Sequence[Any]) -> list[dict[str, Any]]:
    """The three ablations (`legible.cli._Ablation`): per set, the recipe it changes and each
    change, with the change's paired difference in points of fields correct."""
    return [
        {
            "key": a.key,
            "title": a.title,
            "columns": list(a.columns),
            "sets": [
                {
                    "name": s.name,
                    "documents": s.documents,
                    "rows": [
                        {
                            "label": r.label,
                            "accuracy": interval(r.accuracy),
                            "accuracy_text": pct(r.accuracy),
                            "per_thousand": interval(r.per_thousand),
                        }
                        for r in s.rows
                    ],
                    "deltas": [interval(d) for d in s.deltas],
                }
                for s in a.sets
            ],
        }
        for a in ablations
    ]


def pages_read(runs: Path, pages: Mapping[tuple[str, str], int]) -> dict[str, Any]:
    """Every page a reader was sent and answered, over every stored run: dev and test, every
    seed, every degradation level, the subsets and the second reads. A read that failed is
    not counted, nor an archived run. `pages` is each (corpus, document)'s page count."""
    by_arm: dict[str, int] = {}
    documents = 0
    for f in sorted(runs.rglob("*.jsonl")):
        rel = f.relative_to(runs).parts
        if rel[0] == "archive" or not rel[0].startswith("arm-"):
            continue
        if rel[0] != "arm-e" and f.name != "reads.jsonl":
            continue
        where = "/".join(rel).lower()
        corpus = next((c for c in ("cord", "deepform", "fara", "nist") if c in where), None)
        if corpus is None:
            continue
        with f.open(encoding="utf-8") as lines:
            for line in lines:
                r = json.loads(line)
                if rel[0] != "arm-e" and r.get("text") is None:
                    continue
                n = pages.get((corpus, r["doc_id"]))
                if n is None:
                    continue
                arm = rel[0].removeprefix("arm-")
                by_arm[arm] = by_arm.get(arm, 0) + n
                documents += 1
    return {"pages": sum(by_arm.values()), "documents": documents, "by_arm": by_arm}


# --- The output -----------------------------------------------------------------------------


def dump(path: Path, value: object) -> None:
    """JSON the browser can parse: no NaN, no Infinity."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")),
        encoding="utf-8",
        newline="\n",
    )


def copy_assets(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    for name in ASSETS:
        (out / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(SOURCE / name, out / name)
    (out / "architecture").mkdir(exist_ok=True)
    for name in DIAGRAMS:
        shutil.copyfile(DIAGRAM_SOURCE / name, out / "architecture" / name)


def check_output(out: Path) -> None:
    """The finished site holds no image of a corpus it may not show, and no page record of
    one: every image is named for a shown corpus and every page record is of one. The one
    exception is the architecture page's diagrams, by name and place, which hold no page."""
    for f in out.rglob("*"):
        if not f.is_file() or f.suffix.lower() not in IMAGE_SUFFIXES:
            continue
        if f.parent == out / "architecture" and f.name in DIAGRAMS:
            continue
        if not f.name.startswith(tuple(f"{c}-" for c in SHOWN)) or "fara" in f.name.lower():
            raise RegistrationImage(f"{f} is not an image of {', '.join(SHOWN)}")
    pages_dir = out / "data" / "pages"
    if pages_dir.exists():
        for f in pages_dir.glob("*.json"):
            corpus = json.loads(f.read_text(encoding="utf-8")).get("corpus")
            if corpus not in SHOWN:
                raise RegistrationImage(f"{f} is a page record of {corpus}")


def size_of(out: Path) -> int:
    return sum(f.stat().st_size for f in out.rglob("*") if f.is_file())


def serve(site: Path, port: int) -> None:
    """Serve the built site locally with the headers and content types the host sends, read
    from its `staticwebapp.config.json` (08's `headroom serve`): a plain file server sends no
    content security policy, so it shows a page the live site would partly refuse."""
    import os
    from functools import partial
    from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

    config = site / "staticwebapp.config.json"
    if not config.exists():
        raise FileNotFoundError(f"no {config}; run legible site first")
    declared = json.loads(config.read_text(encoding="utf-8"))
    headers: dict[str, str] = declared.get("globalHeaders", {})
    types: dict[str, str] = declared.get("mimeTypes", {})

    class Handler(SimpleHTTPRequestHandler):
        def guess_type(self, path: str | os.PathLike[str]) -> str:
            return types.get(Path(path).suffix) or super().guess_type(path)

        def end_headers(self) -> None:
            for key, value in headers.items():
                self.send_header(key, value)
            super().end_headers()

    print(f"serving {site} on http://localhost:{port} with {len(headers)} headers from {config}")
    with ThreadingHTTPServer(("127.0.0.1", port), partial(Handler, directory=str(site))) as http:
        try:
            http.serve_forever()
        except KeyboardInterrupt:
            print("stopped")
