"""The load client and the sweep record, against a fake server whose timings are known."""

from __future__ import annotations

import asyncio
import datetime as dt
from pathlib import Path
from typing import Any

import pytest
from boundary import ChatRequest, ChatResponse, Mode
from boundary.errors import ProviderError

from legible.bench.client import closed_loop, run_level
from legible.bench.cost import GpuPrice, PriceKind
from legible.bench.load import RequestTiming
from legible.bench.run import LoadRun, pages_per_second, read, requests_per_level, sweep

PRICE = GpuPrice(
    gpu="RTX 3090",
    provider="RunPod Secure Cloud",
    kind=PriceKind.ON_DEMAND,
    usd_per_hour=0.5,
    checked=dt.date(2026, 10, 23),
    source="test",
)


def _request(n: int = 0) -> ChatRequest:
    return ChatRequest(model="m", messages=[{"role": "user", "content": f"page {n}"}], max_tokens=8)


class FakeServer:
    """Answers after `delay` seconds; fails every `fail_every`-th call if set."""

    def __init__(self, delay: float = 0.01, fail_every: int = 0) -> None:
        self.delay = delay
        self.fail_every = fail_every
        self.calls = 0
        self.data_classes: list[str | None] = []

    async def achat_stream(
        self,
        request: ChatRequest,
        *,
        purpose: str,
        run_id: str | None = None,
        mode: Mode = Mode.STANDARD,
        data_class: str | None = None,
    ) -> ChatResponse:
        self.calls += 1
        self.data_classes.append(data_class)
        n = self.calls
        await asyncio.sleep(self.delay)
        if self.fail_every and n % self.fail_every == 0:
            raise ProviderError("selfhosted", "ReadError", "dropped")
        response: ChatResponse = _response()
        return response


def _response() -> Any:
    class Usage:
        output_tokens = 20
        input_tokens = 300

    class Response:
        ok = True
        retries = 0
        ttft_ms = 5.0
        usage = Usage()

    return Response()


def test_the_loop_keeps_exactly_the_concurrency_in_flight() -> None:
    server = FakeServer()
    timings, pages, retried, peak = asyncio.run(
        closed_loop(
            server, [(_request(i), i + 1) for i in range(3)], concurrency=4, total=20,
            purpose="p", run_id="r",
        )
    )  # fmt: skip
    assert peak == 4
    assert len(timings) == len(pages) == 20
    assert retried == 0
    assert sorted(set(pages)) == [1, 2, 3]


def test_every_read_is_declared_public() -> None:
    server = FakeServer()
    asyncio.run(
        closed_loop(server, [(_request(), 1)], concurrency=2, total=6, purpose="p", run_id="r")
    )
    assert server.data_classes == ["public"] * 6


def test_a_dropped_connection_is_a_failed_read_not_the_end_of_the_level() -> None:
    server = FakeServer(fail_every=3)
    level = run_level(server, [(_request(), 2)], concurrency=1, total=9, purpose="p", run_id="r")
    assert level.summary is not None
    assert level.summary.errors == 3
    assert len(level.timings) == 9


def test_pages_per_second_counts_pages_of_successful_reads_over_the_window() -> None:
    timings = (
        RequestTiming(sent_at=0.0, first_token_at=0.1, done_at=1.0, output_tokens=5, ok=True),
        RequestTiming(sent_at=1.0, first_token_at=1.1, done_at=2.0, output_tokens=5, ok=True),
        RequestTiming(sent_at=2.0, first_token_at=None, done_at=4.0, output_tokens=0, ok=False),
    )
    from legible.bench.client import LevelResult

    level = LevelResult(
        concurrency=1, timings=timings, pages=(3, 5, 7), retried=0, max_in_flight=1, summary=None
    )
    # 3 + 5 pages read, the failed read's 7 not, over the four seconds from first sent to last done.
    assert pages_per_second(level, warmup_seconds=0.0) == pytest.approx(2.0)
    # A warm-up of one second drops the first read: 5 pages over three seconds.
    assert pages_per_second(level, warmup_seconds=1.0) == pytest.approx(5 / 3)


def test_a_level_without_page_counts_is_refused() -> None:
    from legible.bench.client import LevelResult

    t = RequestTiming(sent_at=0.0, first_token_at=0.1, done_at=1.0, output_tokens=5, ok=True)
    level = LevelResult(concurrency=1, timings=(t,), retried=0, max_in_flight=1, summary=None)
    with pytest.raises(ValueError, match="page counts"):
        pages_per_second(level, warmup_seconds=0.0)


def test_the_sweep_writes_every_level_and_reads_back(tmp_path: Path) -> None:
    server = FakeServer(delay=0.001)
    done = sweep(
        server,
        [(_request(i), 1) for i in range(4)],
        model="m",
        corpus="cord",
        price=PRICE,
        out_dir=tmp_path,
        levels=(8, 1),
        warmup_seconds=0.0,
        total=lambda c: 4 * c,
    )
    again = read(tmp_path)
    assert isinstance(again, LoadRun)
    assert [lv.concurrency for lv in again.levels] == [1, 8]
    assert again.finished_at is not None and again.price.checked == dt.date(2026, 10, 23)
    assert done.documents == 4


def test_a_level_is_at_least_a_hundred_reads_and_ten_rounds() -> None:
    assert requests_per_level(1) == 100
    assert requests_per_level(32) == 320
