"""A vision read's confidence from a second read: agreement under the field's matcher."""

from __future__ import annotations

from legible.agreement import confidences
from legible.grade import grade_document
from legible.review import choose_threshold
from legible.schema import Record
from tests.schemas import ORDER

VISION = {
    "advertiser": "Smith for Senate",
    "gross_amount": "$400.00",
    "contract_num": "12345",
    "agency": None,
    "line_item": [{"program": "News at 6", "start": "03/15/21", "amount": "$400.00"}],
}
TEXT = {
    "advertiser": "Smith for Senate",
    "gross_amount": "400.00",
    "contract_num": "12346",
    "agency": None,
    "line_item": [{"program": "News at 6", "start": None, "amount": "$400.00"}],
}


def test_fields_agree_under_their_own_matcher_and_empty_agrees_with_empty() -> None:
    c = confidences(ORDER, VISION, TEXT)
    assert c["advertiser"] == 1.0 and c["gross_amount"] == 1.0  # a price within a cent
    assert c["contract_num"] == 0.0 and c["agency"] == 1.0
    assert c["line_item[0].program"] == 1.0 and c["line_item[0].start"] == 0.0


def test_agreed_fields_are_the_ones_a_threshold_accepts() -> None:
    truth: Record = {
        "advertiser": "Smith for Senate",
        "agency": None,
        "contract_num": "99999",
        "flight_from": None,
        "gross_amount": "$400.00",
        "product": None,
        "line_item": [{"program": "News at 6", "start": "03/15/21", "amount": "$400.00"}],
    }
    g = grade_document(ORDER, "d", truth, VISION, confidences=confidences(ORDER, VISION, TEXT))
    t = choose_threshold([g])
    # The agreed fields are all right; taking the disagreed ones too lets the misread
    # contract number in, so the threshold accepts exactly the agreed ones.
    assert t.value == 1.0 and t.dev_accepted_accuracy == 1.0
    assert confidences(ORDER, None, TEXT) == {}
