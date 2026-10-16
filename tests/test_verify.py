"""The verifier against hand-built receipts."""

from __future__ import annotations

import pytest

from legible.grade import grade_document
from legible.schema import Record
from legible.verify import DateRule, PatternRule, SumRule, catch_rate, check_rules, flagged
from tests.schemas import ORDER, RECEIPT

RULES = (
    SumRule(name="items to subtotal", parts=("menu.price",), total="subtotal_price"),
    SumRule(
        name="subtotal and tax to total", parts=("subtotal_price", "tax_price"), total="total_price"
    ),
)

GOOD: Record = {
    "menu": [
        {"nm": "Nasi Goreng", "cnt": "1", "price": "25.000"},
        {"nm": "Es Teh", "cnt": "2", "price": "10.000"},
    ],
    "subtotal_price": "35.000",
    "tax_price": "3.500",
    "total_price": "38.500",
}


def test_a_consistent_receipt_passes() -> None:
    assert flagged(RECEIPT, RULES, GOOD) == set()


def test_a_misread_line_price_flags_the_items_and_subtotal() -> None:
    bad = dict(GOOD, menu=[GOOD["menu"][0], {"nm": "Es Teh", "cnt": "2", "price": "16.000"}])  # type: ignore[index]
    assert flagged(RECEIPT, RULES, bad) == {"menu.price", "subtotal_price"}


def test_a_misread_total_flags_the_second_rule() -> None:
    assert flagged(RECEIPT, RULES, dict(GOOD, total_price="36.500")) == {
        "subtotal_price",
        "tax_price",
        "total_price",
    }


def test_blank_tax_counts_as_zero_and_blank_total_skips() -> None:
    no_tax = dict(GOOD, tax_price=None, total_price="35.000")
    assert flagged(RECEIPT, RULES, no_tax) == set()
    assert flagged(RECEIPT, RULES, dict(GOOD, total_price=None)) == set()


def test_unparsable_amount_fails_its_rule() -> None:
    assert "total_price" in flagged(RECEIPT, RULES, dict(GOOD, total_price="thirty"))


def test_pattern_and_date_rules() -> None:
    rules = (
        PatternRule(name="contract", field="contract_num", pattern=r"\d{5}-[A-Z]"),
        DateRule(name="flight", field="flight_from"),
    )
    check_rules(ORDER, rules)
    assert flagged(ORDER, rules, {"contract_num": "12345-A", "flight_from": "03/15/2021"}) == set()
    assert flagged(ORDER, rules, {"contract_num": "1234-A", "flight_from": "the 15th"}) == {
        "contract_num",
        "flight_from",
    }


def test_rule_on_unknown_or_non_numeric_field_is_refused() -> None:
    with pytest.raises(KeyError):
        check_rules(RECEIPT, (SumRule(name="x", parts=("menu.discount",), total="total_price"),))
    with pytest.raises(ValueError, match="sums"):
        check_rules(RECEIPT, (SumRule(name="x", parts=("menu.nm",), total="total_price"),))


def test_catch_rate_counts_wrong_fields_flagged() -> None:
    pred = dict(GOOD, total_price="36.500")
    g = grade_document(RECEIPT, "r", GOOD, pred)
    flags = {"r": flagged(RECEIPT, RULES, pred)}
    c = catch_rate([g], flags)
    assert c.catch_rate.point == 1.0  # the one wrong field, total_price, is flagged
    assert c.false_alarm_rate.point == pytest.approx(
        2 / 8
    )  # subtotal and tax, right but flagged, of eight right
