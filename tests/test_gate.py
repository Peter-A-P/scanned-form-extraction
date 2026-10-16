"""The gate's files: one suite per field, one outcome per document, sides paired."""

from __future__ import annotations

import pytest

from legible.gate import SideMeta, export, suite_key
from legible.grade import grade_document
from legible.schema import Record
from tests.schemas import ORDER

TRUTH: Record = {
    "advertiser": "Smith for Senate",
    "agency": None,
    "contract_num": "12345",
    "flight_from": "03/15/2021",
    "gross_amount": "$1,000.00",
    "product": None,
    "line_item": [
        {"program": "News", "start": "03/15/2021", "amount": "$400.00"},
        {"program": "Late", "start": "03/16/2021", "amount": "$600.00"},
    ],
}


def meta(label: str) -> SideMeta:
    return SideMeta(
        label=label,
        run_id="r",
        directory="runs/x",
        calls=3,
        latency_p50_ms=900.0,
        cost_usd=0.03,
        uncosted_calls=0,
    )


def wrong_amount() -> Record:
    items = TRUTH["line_item"]
    assert isinstance(items, list)
    return dict(TRUTH, line_item=[items[0], dict(items[1], amount="$650.00")], agency="Blue Ridge")


def test_suites_are_fields_and_columns() -> None:
    b = [grade_document(ORDER, "d1", TRUTH, TRUTH)]
    c = [grade_document(ORDER, "d1", TRUTH, wrong_amount())]
    spec, side_b, side_c = export(
        ORDER, b, c, baseline_meta=meta("frontier"), candidate_meta=meta("e4b"), name="order"
    )
    keys = [s["key"] for s in spec["suites"]]
    assert "line_item-amount" in keys and "advertiser" in keys
    assert all(s["source"] == {"kind": "outcomes_file", "block": s["key"]} for s in spec["suites"])
    assert spec["delta_points"] == 3.0
    assert side_b["suites"]["line_item-amount"]["outcomes"] == {"d1": True}
    assert side_c["suites"]["line_item-amount"]["outcomes"] == {"d1": False}  # one row wrong


def test_a_field_blank_for_both_is_left_out_but_kept_if_either_filled() -> None:
    b = [grade_document(ORDER, "d1", TRUTH, TRUTH)]
    c = [grade_document(ORDER, "d1", TRUTH, wrong_amount())]
    _, side_b, side_c = export(
        ORDER, b, c, baseline_meta=meta("a"), candidate_meta=meta("b"), name="order"
    )
    assert side_b["suites"]["product"]["outcomes"] == {}  # blank on the page, blank in both
    assert side_b["suites"]["agency"]["outcomes"] == {"d1": True}  # the candidate filled it
    assert side_c["suites"]["agency"]["outcomes"] == {"d1": False}


def test_a_failed_call_is_ungradeable_not_wrong() -> None:
    b = [grade_document(ORDER, "d1", TRUTH, TRUTH), grade_document(ORDER, "d2", TRUTH, TRUTH)]
    c = [grade_document(ORDER, "d1", TRUTH, TRUTH)]
    _, side_b, side_c = export(
        ORDER,
        b,
        c,
        baseline_meta=meta("a"),
        candidate_meta=meta("b"),
        candidate_failed=["d2"],
        name="order",
    )
    assert side_c["suites"]["advertiser"]["ungradeable_items"] == 1
    assert "d2" not in side_c["suites"]["advertiser"]["outcomes"]
    assert side_b["suites"]["advertiser"]["outcomes"] == {"d1": True, "d2": True}


def test_an_unparsed_answer_is_wrong() -> None:
    b = [grade_document(ORDER, "d1", TRUTH, TRUTH)]
    c = [grade_document(ORDER, "d1", TRUTH, "not json")]
    _, _, side_c = export(
        ORDER, b, c, baseline_meta=meta("a"), candidate_meta=meta("b"), name="order"
    )
    assert side_c["suites"]["advertiser"]["outcomes"] == {"d1": False}


def test_sides_over_different_documents_are_refused() -> None:
    b = [grade_document(ORDER, "d1", TRUTH, TRUTH)]
    c = [grade_document(ORDER, "d2", TRUTH, TRUTH)]
    with pytest.raises(ValueError, match="different documents"):
        export(ORDER, b, c, baseline_meta=meta("a"), candidate_meta=meta("b"), name="order")


def test_suite_keys_are_gate_shaped() -> None:
    assert suite_key("line_item.sub_amount") == "line_item-sub_amount"


def test_committed_specs_match_the_schemas() -> None:
    """The specs in gate-runs/specs are what `legible gate specs` writes from today's schemas;
    a schema change without regenerating them fails here."""
    from pathlib import Path

    import yaml

    from legible.cli import GATE_LEVELS
    from legible.gate import spec, spec_name
    from legible.schema.corpora import SCHEMAS

    for corpus, levels in GATE_LEVELS.items():
        for level in levels:
            name = spec_name(SCHEMAS[corpus], level)
            on_disk = yaml.safe_load(
                Path(f"gate-runs/specs/{name}.yaml").read_text(encoding="utf-8")
            )
            assert on_disk == spec(SCHEMAS[corpus], name=name)
