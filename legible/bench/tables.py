"""The README's serving tables: latency and throughput from the load test, and the break-even
against each frontier model, every input printed beside it.

Kept out of `legible.report` because it reads load-test records rather than graded reads; the
report command calls it.
"""

from __future__ import annotations

from collections.abc import Sequence

from legible.bench.breakeven import UTILISATIONS, BreakEvenInputs, break_even
from legible.bench.client import LevelResult
from legible.bench.cost import usd_per_page
from legible.bench.load import Measured, mean_measured
from legible.bench.run import LoadRun


def throughput(level: LevelResult, *, warmup_seconds: float, seed: int = 0) -> Measured:
    """Pages a second at one level with its 95% interval: reads resampled, the window fixed,
    as 06's throughput is (legible/bench/load.py). A failed read's pages count as zero."""
    if not level.timings or len(level.pages) != len(level.timings):
        raise ValueError("a level without its page counts")
    start = min(t.sent_at for t in level.timings) + warmup_seconds
    kept = [(t, n) for t, n in zip(level.timings, level.pages, strict=True) if t.sent_at >= start]
    if not kept:
        raise ValueError("the warm-up discarded every read")
    window = max(t.done_at for t, _ in kept) - min(t.sent_at for t, _ in kept)
    if window <= 0:
        raise ValueError("the measured window has no duration")
    # The mean of n * pages / window is the pages over the window.
    scaled = [len(kept) * (n if t.ok else 0) / window for t, n in kept]
    return mean_measured(scaled, unit="pages/s", seed=seed)


def _ms(m: Measured) -> str:
    return f"{m.point / 1000:,.1f} s ({m.low / 1000:,.1f} to {m.high / 1000:,.1f})"


def _rate(m: Measured) -> str:
    return f"{m.point:.2f} ({m.low:.2f} to {m.high:.2f})"


def latency_table(runs: Sequence[tuple[str, LoadRun]]) -> list[str]:
    """One row per model and concurrency: a document read's latency, p50 and p99, its time to
    first token, pages a second, and what a page costs at that rate with the GPU kept busy."""
    out = [
        "| Fine-tune | In flight | Reads (errors) | Pages a read | Read p50 (95% CI) "
        "| Read p99 | First token p50 | Pages a second | Cost per 1,000 pages, GPU kept busy |",
        "|---|---:|---:|---:|---|---|---|---|---|",
    ]
    for label, run in runs:
        for level in sorted(run.levels, key=lambda lv: lv.concurrency):
            s = level.summary
            if s is None:
                out.append(f"| {label} | {level.concurrency} | every read failed | | | | | | |")
                continue
            rate = throughput(level, warmup_seconds=run.warmup_seconds)
            pages = sum(level.pages) / len(level.pages) if level.pages else 0.0
            per_k = usd_per_page(run.price.usd_per_hour, rate.point, 1.0) * 1000
            out.append(
                f"| {label} | {level.concurrency} | {s.requests} ({s.errors}) | {pages:.1f} "
                f"| {_ms(s.e2e_p50_ms)} | {_ms(s.e2e_p99_ms)} | {_ms(s.ttft_p50_ms)} "
                f"| {_rate(rate)} | US${per_k:.2f} |"
            )
    return [*out, ""]


def best_throughput(run: LoadRun) -> tuple[int, Measured] | None:
    """The level with the most pages a second, and that rate: what one card sustains."""
    rates = [
        (lv.concurrency, throughput(lv, warmup_seconds=run.warmup_seconds))
        for lv in run.levels
        if lv.summary is not None
    ]
    return max(rates, key=lambda r: r[1].point) if rates else None


def _volume(v: float | None) -> str:
    if v is None:
        return "never"
    if v >= 1e6:
        return f"{v / 1e6:,.1f} million"
    return f"{v:,.0f}"


def breakeven_table(
    run: LoadRun,
    api: Sequence[tuple[str, float]],
    utilisations: Sequence[float] = UTILISATIONS,
) -> list[str]:
    """Pages a month at which renting the card for the fine-tune costs no more than paying
    each frontier model per page, over utilisation. `api` is (label, US$ per page)."""
    best = best_throughput(run)
    if best is None:
        return ["Not yet measured.", ""]
    _, rate = best
    head = "| Utilisation | Fine-tune, US$ per 1,000 pages | " + " | ".join(
        f"{label} (US${1000 * cost:.2f} per 1,000)" for label, cost in api
    )
    out = [head + " |", "|---:|---:|" + "---:|" * len(api)]
    for u in utilisations:
        cells = []
        own = 0.0
        for _, cost in api:
            point = break_even(
                BreakEvenInputs(
                    price=run.price, pages_per_second=rate.point, api_usd_per_page=cost
                ),
                u,
            )
            own = point.self_hosted_usd_per_page
            cells.append(_volume(point.volume_per_month))
        out.append(f"| {100 * u:.0f}% | US${1000 * own:.2f} | " + " | ".join(cells) + " |")
    return [*out, ""]
