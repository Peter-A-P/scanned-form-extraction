"""Running a frontier arm over a split part: arm A reads the page images, arm D the OCR text.

Arm A is sent each document's pages at the level asked (the rendered page at 0, the degraded
copy above, `legible.arms.ocr_run.page_image`), scaled as `legible.arms.frontier` says. Arm D
is sent the same words arm E reads, laid out as positioned text, one block per page. Both get
the one corpus prompt, built for the input they are given. One read per document over the
union of a part's split files: a zero-shot model does not depend on the split's training part,
so the per-file numbers are cut from the one read at grading time.

A run directory holds what the run was (`run.json`: arm, corpus, part, level, route, model,
prompt version) and the exact prompt (`prompt.json`). A run is resumed only with the same
description and prompt, so a run's reads all name the same words; a prompt changed since is
refused, not mixed in. A test run is refused unless the same prompt has a finished dev run
at the same level, because prompts are tuned on dev and test is touched once.

Batches are cut by size as well as count: page images make large requests, and each vendor
caps a batch (Anthropic at 256 MB, an OpenAI batch file at 200 MB, Gemini's inline batches at
20 MB). Requests are built a batch at a time, so a run never holds every image in memory.
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path
from typing import Any, Literal

from boundary import ChatRequest
from pydantic import BaseModel, ConfigDict

from legible.arms.frontier import GatewayLike, RunDir, Vendor, build_request, submit_batches
from legible.arms.ocr import positioned_text
from legible.arms.ocr_run import load, page_image, stored
from legible.data.render import PageEntry
from legible.grade import parse_output
from legible.prompt import Prompt, Source, build_prompt, load_prompt, save_prompt
from legible.schema.corpora import SCHEMAS

Arm = Literal["a", "d"]
SOURCE: Mapping[Arm, Source] = {"a": "images", "d": "ocr_text"}

#: Output budget per corpus: a FARA record is a handful of short fields; a DeepForm order
#: can list dozens of line items and a receipt a dozen menu rows. The gateway's pre-call
#: estimate charges the whole budget, so it is no larger than the longest training record
#: needs.
MAX_TOKENS: Mapping[str, int] = {"fara": 1024, "deepform": 8192, "cord": 2048}

#: Bytes of request body per batch, well inside each vendor's cap.
BATCH_BYTES: Mapping[Vendor, int] = {
    "anthropic": 100_000_000,
    "openai": 100_000_000,
    "google": 15_000_000,
}
BATCH_DOCS = 1000


class RunSpec(BaseModel):
    model_config = ConfigDict(frozen=True)

    arm: Arm
    corpus: str
    part: str
    level: int
    route: str
    vendor: Vendor
    model: str
    prompt_version: int

    @property
    def purpose(self) -> str:
        return f"arm-{self.arm}"

    @property
    def run_id(self) -> str:
        return (
            f"{self.purpose}-{self.route}-{self.corpus}-{self.part}"
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
        / spec.purpose
        / spec.route
        / f"p{spec.prompt_version}"
        / f"level{spec.level}"
        / spec.corpus
        / spec.part
    )


def _ordered(entries: Sequence[PageEntry]) -> list[PageEntry]:
    return sorted(entries, key=lambda e: e.page)


def document_text(root: Path, level: int, entries: Sequence[PageEntry]) -> list[str]:
    """A document's pages as positioned text, in page order."""
    return [
        positioned_text(page.words, page.width)
        for page in (load(root, level, e.path) for e in _ordered(entries))
    ]


def document_images(root: Path, level: int, entries: Sequence[PageEntry]) -> list[bytes]:
    """A document's pages at a level, as the PNG bytes on disk, in page order."""
    return [page_image(root, e, level).read_bytes() for e in _ordered(entries)]


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


def check_inputs(
    root: Path, spec: RunSpec, doc_ids: Sequence[str], pages: Mapping[str, Sequence[PageEntry]]
) -> None:
    """Refuse before any request if a document has no pages, or (arm D) a page has no OCR."""
    empty = [d for d in doc_ids if not pages.get(d)]
    if empty:
        raise FileNotFoundError(f"{len(empty)} documents have no pages, first {empty[:3]}")
    if spec.arm == "d":
        missing = [
            e.path
            for d in doc_ids
            for e in pages[d]
            if not stored(root, spec.level, e.path).exists()
        ]
        if missing:
            raise FileNotFoundError(
                f"{len(missing)} pages have no OCR at level {spec.level}, first {missing[:3]}"
            )


def request_for(
    root: Path, spec: RunSpec, prompt: Prompt, entries: Sequence[PageEntry]
) -> ChatRequest:
    if spec.arm == "a":
        return build_request(
            spec.vendor,
            spec.model,
            prompt.text,
            images=document_images(root, spec.level, entries),
            max_tokens=MAX_TOKENS[spec.corpus],
        )
    return build_request(
        spec.vendor,
        spec.model,
        prompt.text,
        ocr_pages=document_text(root, spec.level, entries),
        max_tokens=MAX_TOKENS[spec.corpus],
    )


def requests_for(
    root: Path,
    spec: RunSpec,
    prompt: Prompt,
    doc_ids: Sequence[str],
    pages: Mapping[str, Sequence[PageEntry]],
) -> dict[str, ChatRequest]:
    """One request per document, all at once: for a synchronous run or a test."""
    check_inputs(root, spec, doc_ids, pages)
    return {d: request_for(root, spec, prompt, pages[d]) for d in doc_ids}


def request_bytes(request: ChatRequest) -> int:
    return len(json.dumps(request.messages, separators=(",", ":")))


def chunks(
    root: Path,
    spec: RunSpec,
    prompt: Prompt,
    doc_ids: Sequence[str],
    pages: Mapping[str, Sequence[PageEntry]],
    *,
    max_bytes: int,
    max_docs: int = BATCH_DOCS,
) -> Iterator[dict[str, ChatRequest]]:
    """The requests in batches of at most `max_bytes` of body and `max_docs` documents, built
    one batch at a time. A single request over `max_bytes` goes in a batch of its own."""
    check_inputs(root, spec, doc_ids, pages)
    batch: dict[str, ChatRequest] = {}
    size = 0
    for d in doc_ids:
        request = request_for(root, spec, prompt, pages[d])
        n = request_bytes(request)
        if batch and (size + n > max_bytes or len(batch) >= max_docs):
            yield batch
            batch, size = {}, 0
        batch[d] = request
        size += n
    if batch:
        yield batch


def submit(
    gateway: GatewayLike,
    root: Path,
    spec: RunSpec,
    prompt: Prompt,
    run: RunDir,
    doc_ids: Sequence[str],
    pages: Mapping[str, Sequence[PageEntry]],
) -> tuple[int, int]:
    """Submit every document not yet read or submitted, in size-bounded batches.
    Returns (documents, batches) submitted."""
    have = set(run.reads()) | {d for ids in run.batches().values() for d in ids}
    todo = [d for d in doc_ids if d not in have]
    docs = batches = 0
    for batch in chunks(root, spec, prompt, todo, pages, max_bytes=BATCH_BYTES[spec.vendor]):
        batches += len(
            submit_batches(
                gateway,
                batch,
                run,
                purpose=spec.purpose,
                run_id=spec.run_id,
                batch_size=len(batch),
            )
        )
        docs += len(batch)
    return docs, batches


def prompt_for(corpus: str, version: int, arm: Arm = "d") -> Prompt:
    return build_prompt(SCHEMAS[corpus], SOURCE[arm], version)


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
