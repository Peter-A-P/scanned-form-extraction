"""Cost per page and the break-even. The break-even tests are 06's, carried with the code
(06 tests/test_bench.py at 01a6da5), with the unit changed from a call to a page."""

from __future__ import annotations

import datetime as dt

import numpy as np
import pytest
from pydantic import ValidationError

from legible.bench.breakeven import (
    BreakEvenInputs,
    break_even,
    capacity_per_gpu_month,
    curve,
    self_hosted_monthly,
)
from legible.bench.cost import (
    HOURS_PER_MONTH,
    Costed,
    GpuPrice,
    PriceKind,
    ledger_cost,
    ocr_usd_per_page,
    price_entry,
    usd_per_page,
    usd_per_thousand,
)


def gpu(rate: float) -> GpuPrice:
    return GpuPrice(
        gpu="L4",
        provider="example",
        kind=PriceKind.SPOT,
        usd_per_hour=rate,
        checked=dt.date(2026, 10, 16),
        source="https://example.invalid/prices",
    )


# -- the price entry -------------------------------------------------------------------------


def test_cost_per_page_is_rent_over_pages_served_in_the_hour() -> None:
    assert usd_per_page(0.80, 2.0, 1.0) == pytest.approx(0.80 / 7200)
    assert usd_per_page(0.80, 2.0, 0.5) == pytest.approx(2 * 0.80 / 7200)


def test_the_price_entry_reproduces_cost_per_page_from_rate_and_throughput() -> None:
    entry = price_entry(
        "legible-e4b@l4",
        gpu(0.80),
        pages_per_second=2.0,
        output_tokens_per_second=400.0,
        utilisation=0.5,
    )
    assert entry.usd_per_page * 2.0 * 3600 * 0.5 == pytest.approx(0.80)
    assert entry.usd_per_million_output_tokens == pytest.approx(0.80 / (400 * 3600 * 0.5) * 1e6)
    assert usd_per_thousand(entry.usd_per_page) == pytest.approx(entry.usd_per_page * 1000)


@pytest.mark.parametrize("utilisation", [0.0, -0.1, 1.01])
def test_a_utilisation_outside_zero_to_one_is_refused(utilisation: float) -> None:
    with pytest.raises(ValueError, match="utilisation"):
        usd_per_page(0.80, 2.0, utilisation)


def test_a_price_without_its_date_is_not_a_price() -> None:
    with pytest.raises(ValidationError):
        GpuPrice.model_validate(
            {"gpu": "L4", "provider": "x", "kind": "spot", "usd_per_hour": 0.8, "source": "x"}
        )


def test_ocr_costs_cpu_time_at_the_machine_rate() -> None:
    assert ocr_usd_per_page(gpu(0.036), 2.5) == pytest.approx(0.036 * 2.5 / 3600)
    with pytest.raises(ValueError):
        ocr_usd_per_page(gpu(0.036), 0)


# -- the ledger cost -------------------------------------------------------------------------


def test_ledger_cost_is_dollars_over_pages_not_over_documents() -> None:
    # A two-page document at 2 cents and a one-page one at 1 cent: 3 cents for 3 pages.
    reads = [Costed(doc_id="a", cost_usd=0.02), Costed(doc_id="b", cost_usd=0.01)]
    c = ledger_cost(reads, {"a": 2, "b": 1})
    assert c.per_thousand_pages.point == pytest.approx(10.0)
    assert c.pages == 3 and c.documents == 2
    assert c.per_thousand_pages.low <= 10.0 <= c.per_thousand_pages.high


def test_an_uncosted_read_is_refused_not_counted_free() -> None:
    with pytest.raises(ValueError, match="no cost"):
        ledger_cost([Costed(doc_id="a", cost_usd=None)], {"a": 1})


# -- the break-even --------------------------------------------------------------------------


def inputs(
    *, rate: float = 1.0, pps: float = 1.0, api: float = 0.01, fixed: float = 0.0
) -> BreakEvenInputs:
    return BreakEvenInputs(
        price=gpu(rate), pages_per_second=pps, api_usd_per_page=api, fixed_usd_per_month=fixed
    )


def brute_force(case: BreakEvenInputs, utilisation: float, up_to: int) -> int | None:
    """The first whole volume at which the API costs at least the staircase."""
    volume = np.arange(0, up_to + 1, dtype=float)
    capacity = capacity_per_gpu_month(case, utilisation)
    gpus = np.maximum(1, np.ceil(volume / capacity))
    self_hosted = gpus * case.price.usd_per_hour * case.hours_per_month + case.fixed_usd_per_month
    api = volume * case.api_usd_per_page
    hits = np.nonzero(api >= self_hosted - 1e-9)[0]
    return int(hits[0]) if hits.size else None


def test_one_gpu_breaks_even_at_one_month_of_rent_in_api_pages() -> None:
    point = break_even(inputs(), 0.5)
    assert point.gpus_at_break_even == 1
    assert point.volume_per_month == pytest.approx(HOURS_PER_MONTH / 0.01)
    assert point.monthly_cost_at_break_even == pytest.approx(HOURS_PER_MONTH)


def test_without_fixed_costs_the_break_even_does_not_depend_on_utilisation() -> None:
    volumes = [p.volume_per_month for p in curve(inputs())]
    assert volumes == [pytest.approx(HOURS_PER_MONTH / 0.01)] * len(volumes)


def test_a_gpu_dearer_per_page_than_the_api_never_breaks_even() -> None:
    point = break_even(inputs(pps=0.001), 0.1)
    assert point.volume_per_month is None
    assert point.self_hosted_usd_per_page > point.api_usd_per_page


def test_a_break_even_many_gpus_out_matches_the_staircase_evaluated_everywhere() -> None:
    case = inputs(pps=1.0, api=0.003, fixed=1000.0)
    point = break_even(case, 0.1)
    assert point.gpus_at_break_even == 18
    expected = brute_force(case, 0.1, up_to=5_000_000)
    assert expected is not None and point.volume_per_month is not None
    assert point.volume_per_month == pytest.approx(expected, abs=1.0)


@pytest.mark.parametrize("fixed", [0.0, 250.0, 5000.0])
@pytest.mark.parametrize("utilisation", [0.1, 0.5, 0.9])
def test_the_break_even_agrees_with_brute_force_across_inputs(
    fixed: float, utilisation: float
) -> None:
    case = inputs(pps=0.5, api=0.002, fixed=fixed)
    point = break_even(case, utilisation)
    expected = brute_force(case, utilisation, up_to=3_000_000)
    if expected is None:
        assert point.volume_per_month is None or point.volume_per_month > 3_000_000
    else:
        assert point.volume_per_month == pytest.approx(expected, abs=1.0)


def test_the_staircase_rents_whole_gpus() -> None:
    case = inputs()
    capacity = capacity_per_gpu_month(case, 0.5)
    assert self_hosted_monthly(case, capacity + 1, 0.5) == pytest.approx(
        2 * self_hosted_monthly(case, capacity, 0.5)
    )


def test_the_curve_is_drawn_from_ten_to_ninety_percent() -> None:
    assert [p.utilisation for p in curve(inputs())] == pytest.approx(
        [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]
    )
