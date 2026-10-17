"""Audit corrections reach the truth through the loaders, by name, and nowhere else."""

from __future__ import annotations

import pytest

from legible.data.audit import Decision
from legible.data.patches import Patch, apply, patches_from
from legible.schema import Record

TRUTH: Record = {
    "flight_from": "02/62/20",
    "line_item": [{"program_end_date": "06/90/20", "channel": "9"}],
}


def test_only_wrong_labels_with_a_correction_become_patches() -> None:
    decisions = [
        Decision(label_id="deepform/a.pdf/flight_from", verdict="wrong", corrected="02/26/20"),
        Decision(label_id="deepform/a.pdf/agency", verdict="wrong", corrected=None),
        Decision(label_id="deepform/a.pdf/product", verdict="right"),
        Decision(label_id="fara/x_Amendment.pdf/file_date", verdict="unreadable"),
    ]
    assert patches_from(decisions) == [
        Patch(corpus="deepform", doc_id="a.pdf", key="flight_from", value="02/26/20")
    ]


def test_patches_replace_scalars_and_line_item_fields_and_name_them() -> None:
    patches = [
        Patch(corpus="deepform", doc_id="a.pdf", key="flight_from", value="02/26/20"),
        Patch(
            corpus="deepform", doc_id="a.pdf", key="line_item[0].program_end_date", value="06/09/20"
        ),
        Patch(corpus="deepform", doc_id="b.pdf", key="flight_from", value="x"),
    ]
    truth, alts, patched = apply("deepform", "a.pdf", TRUTH, {"flight_from": ["02/62/20"]}, patches)
    assert truth["flight_from"] == "02/26/20" and alts == {}
    items = truth["line_item"]
    assert isinstance(items, list) and items[0]["program_end_date"] == "06/09/20"
    assert patched == ("flight_from", "line_item[0].program_end_date")
    original = TRUTH["line_item"]
    assert (
        isinstance(original, list) and original[0]["program_end_date"] == "06/90/20"
    )  # not mutated


def test_a_patch_for_a_field_that_is_not_there_is_refused() -> None:
    with pytest.raises(KeyError):
        apply(
            "deepform",
            "a.pdf",
            TRUTH,
            {},
            [Patch(corpus="deepform", doc_id="a.pdf", key="line_item[3].channel", value="x")],
        )
