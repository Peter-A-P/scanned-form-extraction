"""Arm A and D requests, and a run that resumes without paying twice, against a stub gateway."""

from __future__ import annotations

import io
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest
from boundary import BatchHandle, ChatRequest, ChatResponse, Usage
from PIL import Image

from legible.arms.frontier import (
    LONG_EDGE,
    RunDir,
    build_request,
    collect_batches,
    run_sync,
    submit_batches,
    vendor_image,
)


def png(size: tuple[int, int], mode: str = "L") -> bytes:
    out = io.BytesIO()
    Image.new(mode, size, 255).save(out, format="PNG")
    return out.getvalue()


def test_pages_are_scaled_to_the_long_edge_and_never_up() -> None:
    with Image.open(io.BytesIO(vendor_image(png((2550, 3300))))) as img:
        assert max(img.size) == LONG_EDGE and img.size[0] == round(2550 * LONG_EDGE / 3300)
    with Image.open(io.BytesIO(vendor_image(png((800, 600), "RGB")))) as img:
        assert img.size == (800, 600) and img.mode == "RGB"


@pytest.mark.parametrize(
    ("vendor", "image_key"),
    [("anthropic", "source"), ("openai", "image_url"), ("google", "inline_data")],
)
def test_image_blocks_are_in_each_vendors_shape(vendor: Any, image_key: str) -> None:
    r = build_request(vendor, "m", "PROMPT", images=[png((100, 100))] * 2, max_tokens=100)
    content = r.messages[0]["content"]
    assert len(content) == 3
    assert all(image_key in block for block in content[:2])
    assert content[-1].get("text") == "PROMPT"
    assert r.model == f"{vendor}/m"


def test_ocr_text_request_carries_pages_in_order() -> None:
    r = build_request("anthropic", "m", "PROMPT", ocr_pages=["first", "second"], max_tokens=100)
    content = r.messages[0]["content"]
    assert content[0]["text"] == "--- page 1 ---\nfirst\n\n--- page 2 ---\nsecond"
    with pytest.raises(ValueError, match="exactly one"):
        build_request("anthropic", "m", "P", images=[png((10, 10))], ocr_pages=["x"], max_tokens=1)


def response(text: str, ledger_id: int) -> ChatResponse:
    return ChatResponse(
        text=text,
        finish_reason="end_turn",
        usage=Usage(input_tokens=2900, output_tokens=300),
        cost_usd=0.01,
        costed=True,
        model_requested="anthropic/m",
        model_returned="m",
        provider="anthropic",
        latency_ms=1200.0,
        status=200,
        headers={},
        raw=None,
        ledger_id=ledger_id,
        mode=None,  # type: ignore[arg-type]
        retries=0,
        cached=False,
        price_list=None,
        price_sha256=None,
    )


class StubGateway:
    def __init__(self) -> None:
        self.calls = 0
        self.submitted: dict[str, list[ChatRequest]] = {}
        self.data_classes: list[str | None] = []

    def chat(
        self,
        request: ChatRequest,
        *,
        purpose: str,
        run_id: str | None = None,
        data_class: str | None = None,
    ) -> ChatResponse:
        self.calls += 1
        self.data_classes.append(data_class)
        return response("{}", self.calls)

    def batch_submit(
        self,
        requests: Sequence[ChatRequest],
        *,
        purpose: str,
        run_id: str | None = None,
        data_class: str | None = None,
    ) -> BatchHandle:
        self.data_classes.append(data_class)
        batch_id = f"b{len(self.submitted)}"
        self.submitted[batch_id] = list(requests)
        return self.batch_handle(batch_id)

    def batch_handle(self, batch_id: str) -> BatchHandle:
        n = len(self.submitted[batch_id])
        return BatchHandle(
            provider="anthropic",
            batch_id=batch_id,
            project="legible",
            purpose="arm-a",
            run_id="r",
            custom_ids=tuple(str(i) for i in range(n)),
            ledger_ids=tuple(range(n)),
        )

    def batch_results(
        self, handle: BatchHandle, *, wait_s: float = 0.0, poll_s: float = 30.0
    ) -> list[ChatResponse]:
        return [response(f'{{"i": {i}}}', i) for i in range(len(self.submitted[handle.batch_id]))]


def requests(n: int) -> dict[str, ChatRequest]:
    return {
        f"d{i}": build_request("anthropic", "m", "P", ocr_pages=[str(i)], max_tokens=10)
        for i in range(n)
    }


def test_batches_resume_without_resubmitting(tmp_path: Path) -> None:
    gw = StubGateway()
    run = RunDir(tmp_path / "run")
    assert len(submit_batches(gw, requests(5), run, purpose="arm-a", run_id="r", batch_size=2)) == 3
    assert submit_batches(gw, requests(5), run, purpose="arm-a", run_id="r", batch_size=2) == []
    assert collect_batches(gw, run) == 5
    assert collect_batches(gw, RunDir(tmp_path / "run")) == 0
    reads = run.reads()
    assert reads["d4"].text == '{"i": 0}' and reads["d4"].input_tokens == 2900
    assert set(gw.data_classes) == {"public"}


def test_sync_run_resumes(tmp_path: Path) -> None:
    gw = StubGateway()
    run = RunDir(tmp_path / "run")
    assert run_sync(gw, requests(3), run, purpose="arm-d", run_id="r") == 3
    assert run_sync(gw, requests(4), run, purpose="arm-d", run_id="r") == 1
    assert gw.calls == 4


def test_unanswered_reads_are_set_aside_and_sent_again(tmp_path: Path) -> None:
    from legible.arms.frontier import Read, RunDir

    def read(doc: str, status: str) -> Read:
        return Read(
            doc_id=doc,
            text=None if status == "missing" else "{}",
            status=status,
            cost_usd=None if status == "missing" else 0.01,
            input_tokens=0,
            output_tokens=0,
            latency_ms=None,
            ledger_id=None,
            model_returned=None,
        )

    run = RunDir(tmp_path)
    run.add_batch("b1", ["d1", "d2", "d3"])
    run.add_reads([read("d1", "200"), read("d2", "missing"), read("d3", "200")])
    assert run.set_aside_missing() == ["d2"]
    assert set(run.reads()) == {"d1", "d3"}
    assert run.batches() == {"b1": ["d1", "d3"]}
    assert "d2" in (tmp_path / "missing.jsonl").read_text(encoding="utf-8")
    # Nothing left to set aside the second time, and the record of the first is kept.
    assert run.set_aside_missing() == []
    assert (tmp_path / "retried.json").exists()
