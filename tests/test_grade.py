"""The grader against the fixtures that break naive graders."""

from __future__ import annotations

import datetime as dt
import json

import pytest

from legible.grade import (
    DocGrade,
    Outcome,
    accuracy_delta,
    grade_document,
    parse_date,
    parse_number,
    summarise,
    values_match,
)
from legible.schema import FieldKind, FieldSpec, Record
from legible.stats import UnpairedItems
from tests.schemas import ORDER, RECEIPT

TRUTH: Record = {
    "advertiser": "Smith for Senate",
    "agency": "Blue Ridge Media",
    "contract_num": "12345-A",
    "flight_from": "03/15/2021",
    "gross_amount": "$12,500.00",
    "product": None,
    "line_item": [
        {"program": "Morning News", "start": "03/15/2021", "amount": "$1,000.00"},
        {"program": "Evening News", "start": "03/16/2021", "amount": "$2,500.00"},
        {"program": "Late Show", "start": "03/17/2021", "amount": "$9,000.00"},
    ],
}

PAGE = (
    "ORDER Advertiser: Smith for Senate Agency: Blue Ridge Media Contract 12345-A "
    "Flight 03/15/2021 Gross $12,500.00 Morning News 03/15/2021 $1,000.00 Evening News "
    "03/16/2021 $2,500.00 Late Show 03/17/2021 $9,000.00 Political candidate"
)


def outcomes(g: DocGrade) -> dict[tuple[str, int | None], Outcome]:
    return {(o.path, o.index): o.outcome for o in g.outcomes}


def test_exact_answer_is_all_right() -> None:
    g = grade_document(ORDER, "d", TRUTH, json.dumps(TRUTH), page_text=PAGE)
    assert g.all_right
    assert g.correct == g.scored == 5 + 9
    assert g.abstained == 1  # product: blank in both, not scored


def test_line_items_in_the_wrong_order_score_full() -> None:
    pred = dict(TRUTH, line_item=list(reversed(TRUTH["line_item"])))  # type: ignore[arg-type]
    assert grade_document(ORDER, "d", TRUTH, pred, page_text=PAGE).all_right


def test_blank_truth_with_a_filled_prediction_is_a_hallucination() -> None:
    pred = dict(TRUTH, product="Political candidate")
    g = grade_document(ORDER, "d", TRUTH, pred, page_text=PAGE)
    assert outcomes(g)[("product", None)] is Outcome.BLANK_FILLED
    assert g.hallucinated == 1
    assert not g.all_right


def test_value_not_on_the_page_is_invented() -> None:
    pred = dict(TRUTH, product="Soft drinks")
    g = grade_document(ORDER, "d", TRUTH, pred, page_text=PAGE)
    assert outcomes(g)[("product", None)] is Outcome.INVENTED


def test_without_page_text_nothing_is_called_invented() -> None:
    pred = dict(TRUTH, product="Soft drinks")
    g = grade_document(ORDER, "d", TRUTH, pred)
    assert outcomes(g)[("product", None)] is Outcome.BLANK_FILLED


def test_swapped_fields_are_wrong_field() -> None:
    pred = dict(TRUTH, advertiser="Blue Ridge Media", agency="Smith for Senate")
    o = outcomes(grade_document(ORDER, "d", TRUTH, pred, page_text=PAGE))
    assert o[("advertiser", None)] is Outcome.WRONG_FIELD
    assert o[("agency", None)] is Outcome.WRONG_FIELD


@pytest.mark.parametrize("printed", ["$12,500.00", "12500", "12,500", "USD 12500.00", "$12500.0"])
def test_price_with_thousands_separator_and_currency(printed: str) -> None:
    g = grade_document(ORDER, "d", TRUTH, dict(TRUTH, gross_amount=printed), page_text=PAGE)
    assert outcomes(g)[("gross_amount", None)] is Outcome.CORRECT


def test_price_off_by_a_dollar_is_wrong() -> None:
    g = grade_document(ORDER, "d", TRUTH, dict(TRUTH, gross_amount="$12,501.00"), page_text=PAGE)
    assert outcomes(g)[("gross_amount", None)] is not Outcome.CORRECT


@pytest.mark.parametrize(
    "printed",
    ["03/15/2021", "March 15, 2021", "2021-03-15", "15 Mar 2021", "3/15/21", "Mar. 15th, 2021"],
)
def test_date_in_many_formats(printed: str) -> None:
    g = grade_document(ORDER, "d", TRUTH, dict(TRUTH, flight_from=printed), page_text=PAGE)
    assert outcomes(g)[("flight_from", None)] is Outcome.CORRECT


def test_day_first_is_a_field_option() -> None:
    assert parse_date("03/04/2021", day_first=False) == dt.date(2021, 3, 4)
    assert parse_date("03/04/2021", day_first=True) == dt.date(2021, 4, 3)
    assert parse_date("31/02/2021", day_first=True) is None


def test_a_non_date_where_a_date_belongs_is_malformed() -> None:
    g = grade_document(ORDER, "d", TRUTH, dict(TRUTH, flight_from="see attached"), page_text=PAGE)
    assert outcomes(g)[("flight_from", None)] is Outcome.MALFORMED


def test_a_list_where_a_scalar_belongs_is_malformed() -> None:
    g = grade_document(ORDER, "d", TRUTH, dict(TRUTH, agency=["Blue Ridge Media"]), page_text=PAGE)
    assert outcomes(g)[("agency", None)] is Outcome.MALFORMED


def test_key_outside_the_schema_is_recorded_not_credited() -> None:
    pred = dict(TRUTH, station="WXYZ")
    g = grade_document(ORDER, "d", TRUTH, pred, page_text=PAGE)
    assert g.extra_keys == ("station",)
    assert g.all_right
    assert g.scored == 14


def test_unparsable_output_marks_every_truth_field_malformed() -> None:
    g = grade_document(ORDER, "d", TRUTH, "I could not read this page.", page_text=PAGE)
    assert g.unparsed and not g.all_right
    assert g.scored == 14 and g.correct == 0
    assert all(o.outcome is Outcome.MALFORMED for o in g.outcomes)


def test_fenced_json_with_prose_parses() -> None:
    text = "Here is the result:\n```json\n" + json.dumps(TRUTH) + "\n```"
    assert grade_document(ORDER, "d", TRUTH, text, page_text=PAGE).all_right


def test_missing_and_extra_line_items() -> None:
    pred = dict(
        TRUTH,
        line_item=[
            TRUTH["line_item"][0],  # type: ignore[index]
            {"program": "Weather Hour", "start": "03/18/2021", "amount": "$700.00"},
        ],
    )
    g = grade_document(ORDER, "d", TRUTH, pred, page_text=PAGE)
    o = [x for x in g.outcomes if x.path.startswith("line_item")]
    # The first item matches; Weather Hour is paired with one of the two remaining truth
    # rows and is wrong on all three fields; the third truth row is missing.
    assert sum(x.outcome is Outcome.CORRECT for x in o) == 3
    assert sum(x.outcome is Outcome.MISSING for x in o) == 3
    assert sum(x.outcome is Outcome.WRONG_VALUE for x in o) == 3


def test_an_item_the_page_does_not_carry_is_invented() -> None:
    extra = {"program": "Weather Hour", "start": "03/18/2021", "amount": "$700.00"}
    pred = dict(TRUTH, line_item=[*TRUTH["line_item"], extra])  # type: ignore[misc]
    g = grade_document(ORDER, "d", TRUTH, pred, page_text=PAGE)
    assert sum(x.outcome is Outcome.INVENTED for x in g.outcomes) == 3
    assert g.hallucinated == 3 and g.correct == 14


def test_code_fields_are_exact_after_whitespace_and_case() -> None:
    assert (
        outcomes(
            grade_document(ORDER, "d", TRUTH, dict(TRUTH, contract_num=" 12345-a "), page_text=PAGE)
        )[("contract_num", None)]
        is Outcome.CORRECT
    )
    assert (
        outcomes(
            grade_document(ORDER, "d", TRUTH, dict(TRUTH, contract_num="12346-A"), page_text=PAGE)
        )[("contract_num", None)]
        is Outcome.WRONG_VALUE
    )


def test_strings_ignore_punctuation_and_keep_case_as_vrdu_does() -> None:
    truth: Record = dict(TRUTH, advertiser="O'Brien for Mayor")
    same = dict(truth, advertiser=f"  O{chr(0x2019)}Brien  for Mayor. ")
    shouted = dict(truth, advertiser="O'BRIEN FOR MAYOR")
    assert (
        outcomes(grade_document(ORDER, "d", truth, same))[("advertiser", None)] is Outcome.CORRECT
    )
    assert (
        outcomes(grade_document(ORDER, "d", truth, shouted))[("advertiser", None)]
        is not Outcome.CORRECT
    )


def test_vrdu_date_match_accepts_a_day_month_swap() -> None:
    # VRDU counts 4 March as 3 April when both parse, so a corpus number here is
    # comparable with the paper's; an impossible swap (month 15) is not a match.
    truth: Record = dict(TRUTH, flight_from="03/04/2021")
    swapped = dict(truth, flight_from="04/03/2021")
    impossible = dict(TRUTH, flight_from="15/03/2021")
    assert (
        outcomes(grade_document(ORDER, "d", truth, swapped))[("flight_from", None)]
        is Outcome.CORRECT
    )
    assert (
        outcomes(grade_document(ORDER, "d", TRUTH, impossible))[("flight_from", None)]
        is not Outcome.CORRECT
    )


def test_vrdu_price_match_is_within_a_cent() -> None:
    near = dict(TRUTH, gross_amount="12,500.01")
    far = dict(TRUTH, gross_amount="12,500.02")
    assert (
        outcomes(grade_document(ORDER, "d", TRUTH, near))[("gross_amount", None)] is Outcome.CORRECT
    )
    assert (
        outcomes(grade_document(ORDER, "d", TRUTH, far))[("gross_amount", None)]
        is Outcome.WRONG_VALUE
    )


def test_name_and_address_matchers() -> None:
    name = FieldSpec(name="n", kind=FieldKind.NAME, description="")
    address = FieldSpec(name="a", kind=FieldKind.ADDRESS, description="")
    assert values_match(name, "John  Q. Smith", "JohnQ. Smith")
    assert not values_match(name, "John Q Smith", "John Q. Smith")
    assert values_match(address, "12 Main St, Albany NY", "12 Main St. Albany, NY")
    assert not values_match(address, "14 Maine Street, Albany", "12 Main St. Albany, NY")


@pytest.mark.parametrize(
    ("printed", "mark", "value"),
    [
        ("Rp 45.000", None, 45000.0),
        ("45,000", None, 45000.0),
        ("1.234,50", ",", 1234.5),
        ("(1,234.50)", ".", -1234.5),
        ("1,234.50-", ".", -1234.5),
        ("twelve", ".", None),
        ("", ".", None),
    ],
)
def test_parse_number(printed: str, mark: str | None, value: float | None) -> None:
    assert parse_number(printed, mark) == value


def test_receipt_whole_unit_prices() -> None:
    truth: Record = {
        "menu": [{"nm": "Nasi Goreng", "cnt": "2", "price": "50.000"}],
        "subtotal_price": "50.000",
        "tax_price": "5.000",
        "total_price": "55.000",
    }
    pred = {
        "menu": [{"nm": "Nasi  Goreng.", "cnt": 2, "price": "50,000"}],
        "subtotal_price": "50000",
        "tax_price": "5,000",
        "total_price": "Rp 55.000",
    }
    assert grade_document(RECEIPT, "r", truth, pred).all_right


def test_truth_naming_an_unknown_field_is_refused() -> None:
    from legible.schema import SchemaDrift

    with pytest.raises(SchemaDrift):
        grade_document(ORDER, "d", dict(TRUTH, station="WXYZ"), json.dumps(TRUTH))


def test_summary_and_intervals_are_over_documents() -> None:
    right = grade_document(ORDER, "a", TRUTH, TRUTH, page_text=PAGE)
    wrong = grade_document(ORDER, "b", TRUTH, "nonsense", page_text=PAGE)
    s = summarise([right, wrong])
    assert s.documents == 2
    assert s.accuracy.point == pytest.approx(0.5)
    assert s.all_right.point == pytest.approx(0.5)
    assert s.unparsed.point == pytest.approx(0.5)
    assert s.accuracy.low <= 0.5 <= s.accuracy.high
    assert s.misses["malformed"] == 14


def test_paired_delta_refuses_different_documents() -> None:
    a = [grade_document(ORDER, "a", TRUTH, TRUTH)]
    b = [grade_document(ORDER, "b", TRUTH, TRUTH)]
    with pytest.raises(UnpairedItems):
        accuracy_delta(a, b)


def test_paired_delta_refuses_a_duplicated_document() -> None:
    a = [grade_document(ORDER, "a", TRUTH, TRUTH)] * 2
    b = [grade_document(ORDER, "a", TRUTH, TRUTH)]
    with pytest.raises(UnpairedItems):
        accuracy_delta(a, b)


def test_paired_delta_on_identical_documents() -> None:
    a = [grade_document(ORDER, str(i), TRUTH, TRUTH) for i in range(20)]
    b = [grade_document(ORDER, str(i), TRUTH, TRUTH if i % 2 else "x") for i in range(20)]
    d = accuracy_delta(a, b)
    assert d.point == pytest.approx(0.5)
    assert d.low <= d.point <= d.high
