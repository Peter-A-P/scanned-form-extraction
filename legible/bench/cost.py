"""What a page costs: the self-hosted price entry, OCR's CPU cost and cost per 1,000 pages.

Vendored from 06's smallprint/bench/cost.py at commit 01a6da502420e161a67b3c845f7ef6f7fd7579e7
(2026-09-19), rather than imported, because importing smallprint brings its EDGAR stack
(lxml, httpx) with it (PLAN.md 2.3). The arithmetic is unchanged; the unit is a page where 06's
was a call, because a form is read a document at a time but priced, compared and sold by the
page, and the documents here run from one page to twelve. What is added: the frontier cost per
1,000 pages from the ledger's reads, with its interval over documents, and OCR's cost from CPU
time.

Frontier cost per page comes from the gateway ledger, which records what each call was billed.
Self-hosted cost has no bill to read, so it is derived, and the derivation is registered with
the gateway as that host's price entry so both kinds of cost land in one ledger:

    cost per page = GPU-hour rate / (pages per second at measured throughput * 3600 * utilisation)

Utilisation is the share of rented GPU time spent serving at that throughput: an input the
reader supplies, not a measurement, which is why the break-even is a curve over it.

Every price carries the date it was read and where from. A rate without a date cannot be
checked, and a cost computed from one cannot be either.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping, Sequence
from enum import StrEnum
from typing import Final

from pydantic import BaseModel, ConfigDict, Field

from legible.stats import Interval, ratio_ci

SECONDS_PER_HOUR: Final = 3600.0
#: The average month, 365.25 * 24 / 12. Break-even is stated per month.
HOURS_PER_MONTH: Final = 730.5


class PriceKind(StrEnum):
    SPOT = "spot"
    ON_DEMAND = "on_demand"


class GpuPrice(BaseModel):
    """One machine-hour rate, as read on one day from one page. Used for CPU machines too,
    with the machine type in `gpu`."""

    model_config = ConfigDict(frozen=True)

    gpu: str
    provider: str
    kind: PriceKind
    usd_per_hour: float = Field(gt=0)
    checked: dt.date
    source: str

    def __str__(self) -> str:
        return (
            f"{self.gpu} {self.kind.value} at {self.provider}, "
            f"US${self.usd_per_hour:.3f}/h, checked {self.checked.isoformat()}"
        )


class PriceEntry(BaseModel):
    """What the gateway is told a self-hosted page costs, and how that was worked out."""

    model_config = ConfigDict(frozen=True)

    host: str
    price: GpuPrice
    pages_per_second: float
    output_tokens_per_second: float
    utilisation: float
    usd_per_page: float
    usd_per_million_output_tokens: float


def _check_utilisation(utilisation: float) -> None:
    if not 0 < utilisation <= 1:
        raise ValueError(f"utilisation must be in (0, 1]; got {utilisation}")


def usd_per_page(usd_per_hour: float, pages_per_second: float, utilisation: float) -> float:
    """Rent divided by pages served in the hour it buys."""
    _check_utilisation(utilisation)
    if usd_per_hour <= 0 or pages_per_second <= 0:
        raise ValueError("the rate and the throughput must both be positive")
    return usd_per_hour / (pages_per_second * SECONDS_PER_HOUR * utilisation)


def price_entry(
    host: str,
    price: GpuPrice,
    *,
    pages_per_second: float,
    output_tokens_per_second: float,
    utilisation: float,
) -> PriceEntry:
    """The price entry the gateway ledger uses for a self-hosted host.

    Per page for this project's arithmetic, and per million output tokens because that is
    the unit frontier prices are quoted in, so the two can be read side by side.
    """
    per_page = usd_per_page(price.usd_per_hour, pages_per_second, utilisation)
    per_million = usd_per_page(price.usd_per_hour, output_tokens_per_second, utilisation) * 1e6
    return PriceEntry(
        host=host,
        price=price,
        pages_per_second=pages_per_second,
        output_tokens_per_second=output_tokens_per_second,
        utilisation=utilisation,
        usd_per_page=per_page,
        usd_per_million_output_tokens=per_million,
    )


def usd_per_thousand(usd_per_page: float) -> float:
    """Cost per 1,000 pages, the unit the results table reports."""
    return usd_per_page * 1000


def ocr_usd_per_page(price: GpuPrice, cpu_seconds_per_page: float) -> float:
    """OCR's cost: the machine's hourly rate for the CPU seconds a page took, on one core.
    The machine is assumed fully used, which flatters OCR slightly; it is a cent-level cost
    either way, and the table prints the inputs."""
    if cpu_seconds_per_page <= 0:
        raise ValueError("CPU time per page must be positive")
    return price.usd_per_hour * cpu_seconds_per_page / SECONDS_PER_HOUR


class LedgerCost(BaseModel):
    """Cost per 1,000 pages from the ledger, with its interval over documents."""

    model_config = ConfigDict(frozen=True)

    per_thousand_pages: Interval
    documents: int
    pages: int
    #: Reads the ledger could not cost (a model missing from the price list). Refused
    #: rather than counted as free; see `ledger_cost`.
    uncosted: int


class Costed(BaseModel):
    """What `ledger_cost` needs from a read: its document and what the ledger billed."""

    model_config = ConfigDict(frozen=True)

    doc_id: str
    cost_usd: float | None


def ledger_cost(reads: Sequence[Costed], pages: Mapping[str, int], *, seed: int = 0) -> LedgerCost:
    """Billed dollars over pages read, per 1,000 pages, resampled over documents.

    A read the ledger could not cost raises: a run with an uncosted call has a cost the table
    cannot state, and printing it as zero would be the cheapest-looking error there is.
    """
    uncosted = [r.doc_id for r in reads if r.cost_usd is None]
    if uncosted:
        raise ValueError(
            f"{len(uncosted)} reads have no cost in the ledger, first {uncosted[:3]}; "
            "add the model's price to the gateway's price list and re-cost"
        )
    dollars = [float(r.cost_usd or 0.0) * 1000 for r in reads]
    counts = [float(pages[r.doc_id]) for r in reads]
    return LedgerCost(
        per_thousand_pages=ratio_ci(dollars, counts, seed=seed),
        documents=len(reads),
        pages=int(sum(counts)),
        uncosted=0,
    )
