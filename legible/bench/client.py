"""The closed-loop load client: N reads in flight, the next sent as each one returns.

Vendored from 06's smallprint/bench/client.py at commit
1a5847a6bc08fce071673d204ac72eec24b999ee (2026-10-23). The loop is unchanged; what changes is
what is sent. A request is one document's read, every page of it as an image with the prompt
the accuracy runs used, built by `legible.arms.read_run.request_for`, so the latency measured
is the latency of the answers graded, not of a synthetic prompt. Every call is declared
`data_class=public` like every other read.

Closed rather than open loop because the question is what one card sustains, and a closed
loop at concurrency N is how a pool of N workers behaves: nobody sends read N+1 until a
worker is free. An open loop at a fixed arrival rate measures a queue once the rate passes
capacity, and the queue's length is a property of the test, not the server.

**Through the gateway, streamed.** Streaming is where the gateway records time to first
token, and it refuses to stream in pass-through mode, so the load test runs in standard mode.
The served configuration (`legible serve config`) sets `retry.max_attempts` to 1: a retried
read's latency includes the retry. Retries are counted in every result anyway, so a run where
that was not so says so rather than hiding it inside a percentile.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable, Sequence
from typing import Protocol

from boundary import ChatRequest, ChatResponse, Mode
from boundary.errors import ProviderError
from pydantic import BaseModel, ConfigDict

from legible.arms.frontier import DATA_CLASS
from legible.bench.load import LoadSummary, RequestTiming, summarise


class StreamCaller(Protocol):
    """What the load client needs from the gateway. `Gateway` satisfies it."""

    async def achat_stream(
        self,
        request: ChatRequest,
        *,
        purpose: str,
        run_id: str | None = ...,
        mode: Mode = ...,
        data_class: str | None = ...,
    ) -> ChatResponse: ...


class LevelResult(BaseModel):
    """One concurrency level: the raw timings, what they summarise to, and the caveats."""

    model_config = ConfigDict(frozen=True)

    concurrency: int
    timings: tuple[RequestTiming, ...]
    #: Pages in each timed read, in the order of `timings`, so latency can be read per page.
    pages: tuple[int, ...] = ()
    #: Reads the gateway retried. Should be zero; see the module docstring.
    retried: int
    #: The most reads ever in flight at once. Equal to `concurrency` in a correct run, and the
    #: test that the loop is closed rather than serial.
    max_in_flight: int
    summary: LoadSummary | None


async def closed_loop(
    caller: StreamCaller,
    requests: Sequence[tuple[ChatRequest, int]],
    *,
    concurrency: int,
    total: int,
    purpose: str,
    run_id: str,
    seconds: float = 0.0,
    clock: Callable[[], float] = time.monotonic,
) -> tuple[list[RequestTiming], list[int], int, int]:
    """Send at least `total` reads with `concurrency` in flight, and keep sending until
    `seconds` have passed since the first, cycling `requests` (each a request and its page
    count) in order. Returns timings, their page counts, retries and the peak.

    The duration is what 06's calls did not need: a CORD receipt at 32 in flight returns in
    under three seconds, so 320 reads were over in half a minute, and a 30-second warm-up left
    28 of them to measure (2026-10-23)."""
    if concurrency < 1 or total < 1:
        raise ValueError("concurrency and total must both be at least one")
    if not requests:
        raise ValueError("no requests to send")
    timings: list[RequestTiming] = []
    pages: list[int] = []
    counters = {"next": 0, "in_flight": 0, "peak": 0, "retried": 0}
    start = clock()

    async def worker() -> None:
        while counters["next"] < total or clock() - start < seconds:
            index = counters["next"]
            counters["next"] += 1
            request, n_pages = requests[index % len(requests)]
            counters["in_flight"] += 1
            counters["peak"] = max(counters["peak"], counters["in_flight"])
            sent = clock()
            response: ChatResponse | None
            try:
                response = await caller.achat_stream(
                    request,
                    purpose="load:" + purpose,
                    run_id=run_id,
                    mode=Mode.STANDARD,
                    data_class=DATA_CLASS,
                )
            except ProviderError:
                # A connection the server dropped is a failed read, counted against its
                # level, not the end of the load test (06, 2026-09-26).
                response = None
            finally:
                counters["in_flight"] -= 1
            done = clock()
            pages.append(n_pages)
            if response is None:
                timings.append(
                    RequestTiming(
                        sent_at=sent, first_token_at=None, done_at=done, output_tokens=0, ok=False
                    )
                )
                continue
            counters["retried"] += 1 if response.retries else 0
            first = sent + response.ttft_ms / 1000 if response.ttft_ms is not None else None
            timings.append(
                RequestTiming(
                    sent_at=sent,
                    first_token_at=first,
                    done_at=done,
                    output_tokens=response.usage.output_tokens,
                    ok=response.ok,
                    input_tokens=response.usage.input_tokens,
                )
            )

    await asyncio.gather(*(worker() for _ in range(concurrency)))
    return timings, pages, counters["retried"], counters["peak"]


def run_level(
    caller: StreamCaller,
    requests: Sequence[tuple[ChatRequest, int]],
    *,
    concurrency: int,
    total: int,
    purpose: str,
    run_id: str,
    warmup_seconds: float = 0.0,
    seconds: float = 0.0,
    runner: asyncio.Runner | None = None,
) -> LevelResult:
    """One concurrency level, run to completion and summarised. `runner` is the event loop a
    sweep shares across its levels: the gateway's HTTP client keeps its connections in the
    loop that first used them (06, 2026-09-26)."""
    run = runner.run if runner is not None else asyncio.run
    timings, pages, retried, peak = run(
        closed_loop(
            caller,
            requests,
            concurrency=concurrency,
            total=total,
            purpose=purpose,
            run_id=run_id,
            seconds=seconds,
        )
    )
    try:
        summary: LoadSummary | None = summarise(
            timings, concurrency=concurrency, warmup_seconds=warmup_seconds
        )
    except ValueError:
        # Every read failed, or the warm-up took them all. The timings are kept so the
        # failure can be read; there is simply nothing to summarise.
        summary = None
    return LevelResult(
        concurrency=concurrency,
        timings=tuple(timings),
        pages=tuple(pages),
        retried=retried,
        max_in_flight=peak,
        summary=summary,
    )
