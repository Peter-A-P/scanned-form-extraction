"""Running arm D over a split part: stored OCR as positioned text, read by a frontier model.

The same words arm E reads (`legible.arms.ocr_run`), laid out as positioned text, one block per
page, with the corpus prompt built for OCR text. One read per document over the union of a
part's split files: a zero-shot model does not depend on the split's training part, so the
per-file numbers are cut from the one read at grading time.

A run directory holds what the run was (`run.json`: corpus, part, level, route, model,
prompt version) and the exact prompt (`prompt.json`). A run is resumed only with the same
description and prompt, so a run's reads all name the same words; a prompt changed since is
refused, not mixed in. A test run is refused unless the same prompt has a finished dev run
at the same level, because prompts are tuned on dev and test is touched once.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from boundary import ChatRequest
from pydantic import BaseModel, ConfigDict

from legible.arms.frontier import RunDir, Vendor, build_request
from legible.arms.ocr import positioned_text
from legible.arms.ocr_run import load, stored
from legible.data.render import PageEntry
from legible.grade import parse_output
from legible.prompt import Prompt, build_prompt, load_prompt, save_prompt
from legible.schema.corpora import SCHEMAS

PURPOSE = "arm-d"

#: Output budget per corpus: a FARA record is a handful of short fields; a DeepForm order
#: can list dozens of line items and a receipt a dozen menu rows. The gateway's pre-call
#: estimate charges the whole budget, so it is no larger than the longest training record
#: needs.
MAX_TOKENS: Mapping[str, int] = {"fara": 1024, "deepform": 8192, "cord": 2048}


class RunSpec(BaseModel):
    model_config = ConfigDict(frozen=True)

    corpus: str
    part: str
    level: int
    route: str
    vendor: Vendor
    model: str
    prompt_version: int

    @property
    def run_id(self) -> str:
        return (
            f"{PURPOSE}-{self.route}-{self.corpus}-{self.part}"
            f"-level{self.level}-p{self.prompt_version}"
        )


class RunMismatch(RuntimeError):
    """A run directory resumed with a different description or prompt than it was begun with."""


class DevFirst(RuntimeError):
    """A test run asked for before the same prompt has a finished dev run."""


def run_dir(root: Path, spec: RunSpec) -> Path:
    return (
        root
        / "runs"
        / PURPOSE
        / spec.route
        / f"p{spec.prompt_version}"
        / f"level{spec.level}"
        / spec.corpus
        / spec.part
    )


def document_text(root: Path, level: int, entries: Sequence[PageEntry]) -> list[str]:
    """A document's pages as positioned text, in page order."""
    return [
        positioned_text(page.words, page.width)
        for page in (load(root, level, e.path) for e in sorted(entries, key=lambda e: e.page))
    ]


def open_run(path: Path, spec: RunSpec, prompt: Prompt) -> RunDir:
    """The run directory, begun with this spec and prompt or resumed with the same ones."""
    meta, stored_prompt = path / "run.json", path / "prompt.json"
    if meta.exists():
        before = RunSpec.model_validate_json(meta.read_text(encoding="utf-8"))
        if before != spec:
            raise RunMismatch(f"{path} was begun as {before}, not {spec}")
        kept = load_prompt(stored_prompt, SCHEMAS[spec.corpus])
        if kept.text != prompt.text:
            raise RunMismatch(f"{path}: the prompt has changed since the run began")
        return RunDir(path)
    run = RunDir(path)
    save_prompt(prompt, stored_prompt)
    meta.write_text(spec.model_dump_json(indent=1) + "\n", encoding="utf-8", newline="\n")
    return run


def finished(path: Path, doc_ids: Sequence[str]) -> bool:
    return path.exists() and set(doc_ids) <= set(RunDir(path).reads())


def require_dev(root: Path, spec: RunSpec, dev_docs: Sequence[str], prompt: Prompt) -> None:
    """Refuse a test run unless this prompt has read every dev document at this level."""
    if spec.part != "test":
        return
    dev = run_dir(root, spec.model_copy(update={"part": "dev"}))
    if not finished(dev, dev_docs):
        raise DevFirst(f"no finished dev run at {dev}; test is run after dev, once")
    kept = load_prompt(dev / "prompt.json", SCHEMAS[spec.corpus])
    if kept.text != prompt.text:
        raise DevFirst("the prompt differs from the one the dev run used")


def requests_for(
    root: Path,
    spec: RunSpec,
    prompt: Prompt,
    doc_ids: Sequence[str],
    pages: Mapping[str, Sequence[PageEntry]],
) -> dict[str, ChatRequest]:
    """One request per document; refuses to build any if a page's OCR is missing."""
    missing = [
        e.path for d in doc_ids for e in pages[d] if not stored(root, spec.level, e.path).exists()
    ]
    if missing:
        raise FileNotFoundError(
            f"{len(missing)} pages have no OCR at level {spec.level}, first {missing[:3]}"
        )
    return {
        d: build_request(
            spec.vendor,
            spec.model,
            prompt.text,
            ocr_pages=document_text(root, spec.level, pages[d]),
            max_tokens=MAX_TOKENS[spec.corpus],
        )
        for d in doc_ids
    }


def prompt_for(corpus: str, version: int) -> Prompt:
    return build_prompt(SCHEMAS[corpus], "ocr_text", version)


def outputs(path: Path) -> dict[str, dict[str, Any] | None]:
    """Each read document's answer as parsed JSON, or None when the reply was not one."""
    return {
        d: parse_output(r.text) if r.text is not None else None
        for d, r in RunDir(path).reads().items()
    }


def describe(path: Path) -> dict[str, Any]:
    """What a run holds, for the command line: submitted, read, failed, cost so far."""
    run = RunDir(path)
    reads = run.reads()
    return {
        "submitted": sum(len(v) for v in run.batches().values()),
        "read": len(reads),
        "failed": sum(1 for r in reads.values() if r.text is None),
        "cost_usd": round(sum(r.cost_usd or 0.0 for r in reads.values()), 4),
        "spec": json.loads((path / "run.json").read_text(encoding="utf-8")),
    }
