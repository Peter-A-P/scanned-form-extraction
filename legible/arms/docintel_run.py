"""Arm F's runs: layout readings of the training documents, the training sets, the builds, and
the reads, each resumable from what is on disk.

Layout readings and reads go through the gateway (boundary 1.6), one document a batch, so each
page is in the ledger at the price the service bills. Uploading a training set to blob storage
and asking the service to build a model are not model calls: the upload is a file copy, and
building is free for ten hours a month and then billed by the hour, which is recorded from the
service's own `trainingHours` (docs/docintel.md).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from legible.arms.docintel import (
    analyze_request,
    answer_text,
    document_tiff,
    fields_file,
    labels,
    ocr_file,
)
from legible.arms.frontier import DATA_CLASS, Read, RunDir, to_read
from legible.data.render import PageEntry
from legible.schema import CorpusSchema

LAYOUT = "docintel-layout"


def safe_name(doc_id: str) -> str:
    """A training document's file name in the set: its id's hash, since FARA's ids carry
    commas and spaces."""
    return hashlib.sha256(doc_id.encode("utf-8")).hexdigest()[:20]


def set_dir(root: Path, dataset: str) -> Path:
    """The training set as uploaded: documents, their readings and labels, and fields.json."""
    return root / "docintel" / "train" / dataset


def meta_path(root: Path, dataset: str, what: str) -> Path:
    """A training set's own records (batch ids, label coverage, the build), kept out of the
    set's directory so they are not uploaded with it."""
    return root / "docintel" / "meta" / f"{dataset}-{what}.json"


class Batches:
    """Batch ids by document, for the layout readings, which are not graded reads."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> dict[str, str]:
        if not self.path.exists():
            return {}
        out: dict[str, str] = json.loads(self.path.read_text(encoding="utf-8"))
        return out

    def add(self, doc_id: str, batch_id: str) -> None:
        data = self.load()
        data[doc_id] = batch_id
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, indent=1) + "\n", encoding="utf-8")


def submit_layout(
    gateway: Any,
    root: Path,
    dataset: str,
    docs: Mapping[str, Sequence[Path]],
    *,
    run_id: str,
) -> int:
    """Send every training document without a layout reading or a batch. Returns how many."""
    out = set_dir(root, dataset)
    batches = Batches(meta_path(root, dataset, "layout-batches"))
    have = batches.load()
    sent = 0
    for doc_id, images in docs.items():
        if doc_id in have or (out / f"{safe_name(doc_id)}.tiff.ocr.json").exists():
            continue
        tiff = document_tiff(images)
        handle = gateway.batch_submit(
            [analyze_request(LAYOUT, tiff, len(images))],
            purpose="arm-f-layout",
            run_id=run_id,
            data_class=DATA_CLASS,
        )
        batches.add(doc_id, handle.batch_id)
        sent += 1
    return sent


def collect_layout(gateway: Any, root: Path, dataset: str) -> tuple[int, int]:
    """Store every finished layout reading as its document's `.ocr.json`. Returns (stored,
    still running)."""
    from boundary import BatchNotReady

    out = set_dir(root, dataset)
    stored = running = 0
    for doc_id, batch_id in Batches(meta_path(root, dataset, "layout-batches")).load().items():
        path = out / f"{safe_name(doc_id)}.tiff.ocr.json"
        if path.exists():
            continue
        try:
            (response,) = gateway.batch_results(gateway.batch_handle(batch_id))
        except BatchNotReady:
            running += 1
            continue
        if not response.ok or response.text is None:
            raise RuntimeError(f"layout of {doc_id} failed: {response.status}")
        path.write_text(
            json.dumps(ocr_file(json.loads(response.text)), ensure_ascii=False), encoding="utf-8"
        )
        stored += 1
    return stored, running


def write_set(
    root: Path,
    dataset: str,
    schema: CorpusSchema,
    docs: Mapping[str, Sequence[Path]],
    truth: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """The training set as the service reads it: each document's TIFF, its `.ocr.json` (the
    layout reading) and its `.labels.json`, and the set's `fields.json`. Returns the label
    coverage, which is also written to the set's coverage record."""
    out = set_dir(root, dataset)
    names: dict[str, str] = {}
    total = found = 0
    per_field: dict[str, list[int]] = {}
    for doc_id, images in docs.items():
        name = f"{safe_name(doc_id)}.tiff"
        ocr_path = out / f"{name}.ocr.json"
        if not ocr_path.exists():
            raise FileNotFoundError(f"{doc_id} has no layout reading; collect it first")
        tiff_path = out / name
        if not tiff_path.exists():
            tiff_path.write_bytes(document_tiff(images))
        analyze = json.loads(ocr_path.read_text(encoding="utf-8"))["analyzeResult"]
        doc_labels, n, k = labels(schema, name, truth[doc_id], analyze)
        (out / f"{name}.labels.json").write_text(
            json.dumps(doc_labels, ensure_ascii=False), encoding="utf-8"
        )
        names[name] = doc_id
        total += n
        found += k
        for item in doc_labels["labels"]:
            key = item["label"].split("/")[0]
            per_field.setdefault(key, [0, 0])[1] += 1
        for f in schema.fields:
            v = truth[doc_id].get(f.name)
            if v not in (None, "", []):
                per_field.setdefault(f.name, [0, 0])[0] += 1
    (out / "fields.json").write_text(json.dumps(fields_file(schema), indent=1), encoding="utf-8")
    coverage = {
        "dataset": dataset,
        "documents": len(docs),
        "values": total,
        "labelled": found,
        # Per field: documents with a value in the truth, label entries written (a table's
        # entries are its cells).
        "fields": per_field,
        "names": names,
    }
    path = meta_path(root, dataset, "coverage")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(coverage, indent=1), encoding="utf-8")
    return coverage


def open_read_run(path: Path, description: Mapping[str, Any]) -> RunDir:
    """A read run's directory, its description in `run.json` as every arm's run has, refused
    if it was begun with another."""
    run = RunDir(path)
    spec = path / "run.json"
    if spec.exists():
        if json.loads(spec.read_text(encoding="utf-8")) != dict(description):
            raise RuntimeError(f"{path} was begun with another description")
    else:
        spec.write_text(
            json.dumps(dict(description), indent=1, sort_keys=True) + "\n", encoding="utf-8"
        )
    return run


def submit_reads(
    gateway: Any,
    run: RunDir,
    model: str,
    docs: Mapping[str, Sequence[Path]],
    *,
    run_id: str,
) -> int:
    """Send every document not yet read or submitted, one a batch. Returns how many."""
    have = set(run.reads()) | {d for ids in run.batches().values() for d in ids}
    sent = 0
    for doc_id, images in docs.items():
        if doc_id in have:
            continue
        handle = gateway.batch_submit(
            [analyze_request(model, document_tiff(images), len(images))],
            purpose="arm-f",
            run_id=run_id,
            data_class=DATA_CLASS,
        )
        run.add_batch(handle.batch_id, [doc_id])
        sent += 1
    return sent


def collect_reads(
    gateway: Any, run: RunDir, convert: Callable[[Mapping[str, Any]], Mapping[str, Any]]
) -> tuple[int, int]:
    """Store every finished read: the answer in the corpus schema as the read's text, and the
    service's own fields, with their confidences, in `fields.jsonl`. Returns (stored, still
    running)."""
    from boundary import BatchNotReady

    have = run.reads()
    stored = running = 0
    for batch_id, (doc_id,) in run.batches().items():
        if doc_id in have:
            continue
        try:
            (response,) = gateway.batch_results(gateway.batch_handle(batch_id))
        except BatchNotReady:
            running += 1
            continue
        read: Read = to_read(doc_id, response)
        if response.ok and response.text is not None:
            analyze = json.loads(response.text)
            from legible.arms.docintel import document_fields

            with (run.path / "fields.jsonl").open("a", encoding="utf-8", newline="\n") as f:
                f.write(json.dumps({"doc_id": doc_id, "fields": document_fields(analyze)}) + "\n")
            read = read.model_copy(update={"text": answer_text(convert(analyze))})
        run.add_reads([read])
        stored += 1
    return stored, running


def doc_images(
    root: Path, level: int, pages: Mapping[str, Sequence[PageEntry]], doc_ids: Sequence[str]
) -> dict[str, list[Path]]:
    """Each document's page images at a level, in page order."""
    from legible.arms.ocr_run import page_image

    return {
        d: [page_image(root, e, level) for e in sorted(pages[d], key=lambda e: e.page)]
        for d in doc_ids
    }
