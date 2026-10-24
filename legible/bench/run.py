"""A load test, whole: every concurrency level for one served model on one card, on disk.

Vendored from 06's smallprint/bench/run.py at commit 1a5847a6bc08fce071673d204ac72eec24b999ee
(2026-10-23). `client.run_level` measures one level; this runs the sweep PLAN.md 2.7 names,
1, 8 and 32 reads in flight, and writes it as one record with the card and its dated price
beside the timings. The raw timings are kept, so a reader can recompute any percentile, and
the price travels with them because a throughput without the rent it was bought at is not a
cost.

What changes from 06 is the number of reads a level takes. 06's calls took a second or two;
a read here is a document of up to twelve page images and an answer of up to a few thousand
tokens, and a DeepForm order at one in flight takes most of a minute. A level is 100 reads,
or ten rounds of the loop if more, and runs for at least three minutes after its 30-second
warm-up, so a fast corpus is measured at steady state and a slow one still has a p99 that its
interval qualifies.
"""

from __future__ import annotations

import asyncio
import datetime as dt
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Final

from boundary import ChatRequest
from pydantic import BaseModel, ConfigDict

from legible.bench.client import LevelResult, StreamCaller, run_level
from legible.bench.cost import GpuPrice

RECORD: Final = "bench.json"
#: The concurrency levels of the sweep (PLAN.md 2.7).
LEVELS: Final = (1, 8, 32)
MIN_REQUESTS: Final = 100
ROUNDS: Final = 10
#: Seconds each level runs for after its warm-up, at least.
MEASURED_SECONDS: Final = 180.0


class LoadRun(BaseModel):
    """One served model on one card, every level of the sweep."""

    model_config = ConfigDict(frozen=True)

    #: The served route: a fine-tune's run id.
    model: str
    #: What it read: the training set's corpus and the documents' part and level.
    corpus: str
    documents: int
    price: GpuPrice
    warmup_seconds: float
    started_at: dt.datetime
    finished_at: dt.datetime | None = None
    levels: tuple[LevelResult, ...] = ()

    def level(self, concurrency: int) -> LevelResult | None:
        return next((lv for lv in self.levels if lv.concurrency == concurrency), None)

    def write(self, out_dir: Path) -> Path:
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / RECORD
        path.write_text(self.model_dump_json(indent=1), encoding="utf-8", newline="\n")
        return path


def read(out_dir: Path) -> LoadRun:
    return LoadRun.model_validate_json((out_dir / RECORD).read_text(encoding="utf-8"))


def requests_per_level(concurrency: int) -> int:
    return max(MIN_REQUESTS, ROUNDS * concurrency)


def sweep(
    caller: StreamCaller,
    requests: Sequence[tuple[ChatRequest, int]],
    *,
    model: str,
    corpus: str,
    price: GpuPrice,
    out_dir: Path,
    levels: Sequence[int] = LEVELS,
    warmup_seconds: float = 30.0,
    total: Callable[[int], int] = requests_per_level,
    measured_seconds: float = MEASURED_SECONDS,
    on_level: Callable[[LevelResult], None] | None = None,
) -> LoadRun:
    """Every level in turn, lowest first, the record rewritten after each, so a pod lost at
    the last level keeps the ones it finished."""
    if not levels:
        raise ValueError("no concurrency levels")
    if not requests:
        raise ValueError("no requests to send")
    record = LoadRun(
        model=model,
        corpus=corpus,
        documents=len(requests),
        price=price,
        warmup_seconds=warmup_seconds,
        started_at=dt.datetime.now(dt.UTC),
    )
    record.write(out_dir)
    with asyncio.Runner() as runner:
        for concurrency in sorted(levels):
            result = run_level(
                caller,
                requests,
                concurrency=concurrency,
                total=total(concurrency),
                purpose=model,
                run_id=f"load-{model}-c{concurrency}",
                warmup_seconds=warmup_seconds,
                seconds=warmup_seconds + measured_seconds,
                runner=runner,
            )
            record = record.model_copy(update={"levels": (*record.levels, result)})
            record.write(out_dir)
            if on_level is not None:
                on_level(result)
    record = record.model_copy(update={"finished_at": dt.datetime.now(dt.UTC)})
    record.write(out_dir)
    return record


def pages_per_second(result: LevelResult, *, warmup_seconds: float) -> float:
    """Pages read a second at one level: the successful reads' pages over the measured
    window, the throughput a self-hosted page is costed at."""
    if not result.timings or len(result.pages) != len(result.timings):
        raise ValueError("a level without its page counts")
    start = min(t.sent_at for t in result.timings) + warmup_seconds
    kept = [(t, n) for t, n in zip(result.timings, result.pages, strict=True) if t.sent_at >= start]
    if not kept:
        raise ValueError("the warm-up discarded every read")
    window = max(t.done_at for t, _ in kept) - min(t.sent_at for t, _ in kept)
    if window <= 0:
        raise ValueError("the measured window has no duration")
    return sum(n for t, n in kept if t.ok) / window
