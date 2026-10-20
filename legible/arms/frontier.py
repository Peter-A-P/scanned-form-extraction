"""Arms A and D: a frontier model reads the page images (A) or the positioned OCR text (D).

Every call goes through 04's gateway with `data_class=public`, which is true of every page
this project sends (docs/data.md), with `purpose` naming the arm and `run_id` the run, so cost
per page comes out of one ledger. Batches are used wherever the vendor offers them; a batch is
submitted, its id written to the run directory, and collected later, by the same process or
another, because a batch can take hours.

Images are the 300 dpi pages scaled to 1,568 pixels on the long edge, the size Anthropic's
documentation recommends and above which it scales down itself, and the same pixels go to
every vendor so that the comparison is between models and not between resizes. Content
blocks are built in each vendor's own shape; the gateway passes them through untouched.
"""

from __future__ import annotations

import base64
import io
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Literal, Protocol

from boundary import BatchHandle, ChatRequest, ChatResponse
from PIL import Image
from pydantic import BaseModel, ConfigDict

#: "selfhosted" is a vLLM server on a rented GPU (legible/serve.py), which takes OpenAI's shape.
Vendor = Literal["anthropic", "openai", "google", "selfhosted"]
LONG_EDGE = 1568
DATA_CLASS = "public"


class GatewayLike(Protocol):
    """The part of boundary.Gateway the arms use; a stub implements it in the tests."""

    def chat(
        self,
        request: ChatRequest,
        *,
        purpose: str,
        run_id: str | None = ...,
        data_class: str | None = ...,
    ) -> ChatResponse: ...

    def batch_submit(
        self,
        requests: Sequence[ChatRequest],
        *,
        purpose: str,
        run_id: str | None = ...,
        data_class: str | None = ...,
    ) -> BatchHandle: ...

    def batch_handle(self, batch_id: str) -> BatchHandle: ...

    def batch_results(
        self, handle: BatchHandle, *, wait_s: float = ..., poll_s: float = ...
    ) -> list[ChatResponse]: ...


def vendor_image(page_png: bytes) -> bytes:
    """A page scaled so its long edge is at most 1,568 pixels, as PNG."""
    with Image.open(io.BytesIO(page_png)) as img:
        page = img.convert("L") if img.mode in {"1", "L", "P"} else img.convert("RGB")
        scale = LONG_EDGE / max(page.size)
        if scale < 1:
            size = (max(1, round(page.width * scale)), max(1, round(page.height * scale)))
            page = page.resize(size, Image.Resampling.LANCZOS)
        out = io.BytesIO()
        page.save(out, format="PNG", optimize=False)
        return out.getvalue()


def image_block(vendor: Vendor, png: bytes) -> dict[str, Any]:
    data = base64.b64encode(png).decode("ascii")
    match vendor:
        case "anthropic":
            return {
                "type": "image",
                "source": {"type": "base64", "media_type": "image/png", "data": data},
            }
        case "openai" | "selfhosted":
            return {
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{data}", "detail": "high"},
            }
        case "google":
            return {"inline_data": {"mime_type": "image/png", "data": data}}


def text_block(vendor: Vendor, text: str) -> dict[str, Any]:
    return {"text": text} if vendor == "google" else {"type": "text", "text": text}


def build_request(
    vendor: Vendor,
    model: str,
    prompt: str,
    *,
    images: Sequence[bytes] = (),
    ocr_pages: Sequence[str] = (),
    max_tokens: int,
    extra: Mapping[str, Any] | None = None,
    temperature: float | None = None,
) -> ChatRequest:
    """One document's request: its page images (arm A) or its pages' positioned text (arm D),
    then the instruction. Exactly one of the two inputs is given."""
    if bool(images) == bool(ocr_pages):
        raise ValueError("a request reads the page images or the OCR text, exactly one")
    # The vendors get every page at 1,568 pixels on the long edge, the same pixels each. A
    # self-hosted model gets the page as rendered, the pixels it was trained on: its own
    # processor scales a page to its visual budget, and a page already cut to 1,568 pixels
    # reached it with fewer patches than in training (the first fine-tuned reads, 2026-10-18).
    content: list[dict[str, Any]] = [
        image_block(vendor, png if vendor == "selfhosted" else vendor_image(png)) for png in images
    ]
    if ocr_pages:
        joined = "\n\n".join(f"--- page {i + 1} ---\n{text}" for i, text in enumerate(ocr_pages))
        content.append(text_block(vendor, joined))
    content.append(text_block(vendor, prompt))
    return ChatRequest(
        model=f"{vendor}/{model}",
        messages=[{"role": "user", "content": content}],
        max_tokens=max_tokens,
        extra=dict(extra or {}),
        temperature=temperature,
    )


class Read(BaseModel):
    """One document read by one arm: the text returned and what it cost, from the ledger."""

    model_config = ConfigDict(frozen=True)

    doc_id: str
    text: str | None
    status: str
    cost_usd: float | None
    input_tokens: int
    output_tokens: int
    latency_ms: float | None
    ledger_id: int | None
    model_returned: str | None
    #: A self-hosted read asked for log-probabilities: each generated token as (UTF-8 bytes,
    #: natural-log probability), in order (`legible.tokenconf`). None when not asked.
    tokens: list[tuple[int, float]] | None = None


def answer_tokens(raw: Any) -> list[tuple[int, float]] | None:
    """The answer's tokens from an OpenAI-shaped body with `logprobs`, or None."""
    try:
        content = raw["choices"][0]["logprobs"]["content"]
    except (KeyError, IndexError, TypeError):
        return None
    if not isinstance(content, list):
        return None
    out: list[tuple[int, float]] = []
    for t in content:
        b = t.get("bytes")
        n = len(b) if isinstance(b, list) else len(str(t.get("token", "")).encode("utf-8"))
        out.append((n, float(t["logprob"])))
    return out


def to_read(doc_id: str, response: ChatResponse) -> Read:
    return Read(
        doc_id=doc_id,
        text=response.text,
        status=str(response.status),
        cost_usd=response.cost_usd,
        input_tokens=response.usage.input_tokens
        + response.usage.cache_read_tokens
        + response.usage.cache_write_tokens,
        output_tokens=response.usage.output_tokens,
        latency_ms=response.latency_ms,
        ledger_id=response.ledger_id,
        model_returned=response.model_returned,
        tokens=answer_tokens(response.raw),
    )


class RunDir:
    """A run's directory: the batch ids submitted and the reads collected, so that a run can
    be resumed after the process that started it is gone, and nothing is paid for twice."""

    def __init__(self, path: Path) -> None:
        self.path = path
        path.mkdir(parents=True, exist_ok=True)

    @property
    def _batches(self) -> Path:
        return self.path / "batches.json"

    @property
    def _reads(self) -> Path:
        return self.path / "reads.jsonl"

    def batches(self) -> dict[str, list[str]]:
        """Batch id to the document ids it carries, in submission order."""
        if not self._batches.exists():
            return {}
        raw: dict[str, list[str]] = json.loads(self._batches.read_text(encoding="utf-8"))
        return raw

    def add_batch(self, batch_id: str, doc_ids: Sequence[str]) -> None:
        batches = self.batches()
        batches[batch_id] = list(doc_ids)
        self._batches.write_text(json.dumps(batches, indent=1) + "\n", encoding="utf-8")

    def reads(self) -> dict[str, Read]:
        if not self._reads.exists():
            return {}
        with self._reads.open(encoding="utf-8") as f:
            return {
                r.doc_id: r for r in (Read.model_validate_json(line) for line in f if line.strip())
            }

    def add_reads(self, reads: Sequence[Read]) -> None:
        with self._reads.open("a", encoding="utf-8", newline="\n") as f:
            for r in reads:
                f.write(r.model_dump_json() + "\n")


def submit_batches(
    gateway: GatewayLike,
    requests: Mapping[str, ChatRequest],
    run: RunDir,
    *,
    purpose: str,
    run_id: str,
    batch_size: int,
) -> list[str]:
    """Submit every document not already read or in a submitted batch. Returns new batch ids."""
    done = set(run.reads()) | {d for ids in run.batches().values() for d in ids}
    pending = [d for d in requests if d not in done]
    new = []
    for start in range(0, len(pending), batch_size):
        chunk = pending[start : start + batch_size]
        handle = gateway.batch_submit(
            [requests[d] for d in chunk], purpose=purpose, run_id=run_id, data_class=DATA_CLASS
        )
        run.add_batch(handle.batch_id, chunk)
        new.append(handle.batch_id)
    return new


def collect_batches(gateway: GatewayLike, run: RunDir, *, wait_s: float = 0.0) -> int:
    """Collect every submitted batch whose reads are not yet stored. Returns reads added.
    A batch still running raises boundary's BatchNotReady, which the caller reports."""
    have = run.reads()
    added = 0
    for batch_id, doc_ids in run.batches().items():
        if all(d in have for d in doc_ids):
            continue
        responses = gateway.batch_results(gateway.batch_handle(batch_id), wait_s=wait_s)
        if len(responses) != len(doc_ids):
            raise RuntimeError(
                f"batch {batch_id}: {len(responses)} results for {len(doc_ids)} documents"
            )
        reads = [to_read(d, r) for d, r in zip(doc_ids, responses, strict=True) if d not in have]
        run.add_reads(reads)
        added += len(reads)
    return added


def run_sync(
    gateway: GatewayLike,
    requests: Mapping[str, ChatRequest],
    run: RunDir,
    *,
    purpose: str,
    run_id: str,
) -> int:
    """One call per document, for a vendor or a run without batches. Resumes where it
    stopped; each read is stored as it arrives."""
    have = run.reads()
    added = 0
    for doc_id, request in requests.items():
        if doc_id in have:
            continue
        response = gateway.chat(request, purpose=purpose, run_id=run_id, data_class=DATA_CLASS)
        run.add_reads([to_read(doc_id, response)])
        added += 1
    return added


def run_concurrent(
    gateway: Any,
    requests: Mapping[str, ChatRequest],
    run: RunDir,
    *,
    purpose: str,
    run_id: str,
    concurrency: int,
) -> tuple[int, float]:
    """Calls kept `concurrency` in flight, for a self-hosted server that batches on its own
    (vLLM) and has no batch endpoint. Each read is stored as it arrives, so a stopped run
    resumes. Returns (reads added, wall seconds), the throughput a self-hosted page is
    costed from."""
    import asyncio
    import time

    have = run.reads()
    todo = [(d, r) for d, r in requests.items() if d not in have]

    async def go() -> int:
        gate = asyncio.Semaphore(concurrency)

        failed: list[str] = []

        async def one(doc_id: str, request: ChatRequest) -> None:
            async with gate:
                try:
                    response = await gateway.achat(
                        request, purpose=purpose, run_id=run_id, data_class=DATA_CLASS
                    )
                except Exception as error:
                    print(f"{doc_id}: {type(error).__name__}: {error}"[:300], flush=True)
                    failed.append(doc_id)
                    return
            run.add_reads([to_read(doc_id, response)])

        await asyncio.gather(*(one(d, r) for d, r in todo))
        # A failed call is left unread rather than stopping the pass; a later pass, or the
        # report's "of N", accounts for it.
        return len(todo) - len(failed)

    start = time.perf_counter()
    added = asyncio.run(go())
    return added, time.perf_counter() - start
