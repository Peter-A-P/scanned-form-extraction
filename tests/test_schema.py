"""One definition, three views, and a refusal when they drift apart."""

from __future__ import annotations

import json

import pytest

from legible.schema import CorpusSchema, FieldKind, FieldSpec, SchemaDrift
from tests.schemas import ORDER


def test_prompt_target_and_grader_name_the_same_fields() -> None:
    js = ORDER.json_schema()
    from_json_schema = {k for k, v in js["properties"].items() if v["type"] != "array"} | {
        f"{k}.{sub}"
        for k, v in js["properties"].items()
        if v["type"] == "array"
        for sub in v["items"]["properties"]
    }
    target = json.loads(ORDER.target({"advertiser": "A", "line_item": [{"program": "P"}]}))
    from_target = {k for k, v in target.items() if not isinstance(v, list)} | {
        f"{k}.{sub}" for k, v in target.items() if isinstance(v, list) for item in v for sub in item
    }
    assert from_json_schema == from_target == ORDER.names()


def test_target_round_trips_and_keeps_schema_order() -> None:
    truth = {
        "product": "Cola",
        "advertiser": "A",
        "line_item": [{"amount": "$1", "program": "P", "start": None}],
    }
    out = json.loads(ORDER.target(truth))  # type: ignore[arg-type]
    assert list(out) == [f.name for f in ORDER.fields]
    assert out["line_item"] == [{"program": "P", "start": None, "amount": "$1"}]
    assert out["agency"] is None


def test_target_refuses_a_field_the_schema_does_not_have() -> None:
    with pytest.raises(SchemaDrift):
        ORDER.target({"advertiser": "A", "station": "WXYZ"})
    with pytest.raises(SchemaDrift):
        ORDER.target({"line_item": [{"program": "P", "spots": "4"}]})


def test_stored_artefact_with_other_names_is_refused() -> None:
    names = set(ORDER.names()) - {"agency"}
    with pytest.raises(SchemaDrift, match="missing \\['agency'\\]"):
        ORDER.require_aligned(names, ORDER.fingerprint(), what="prompt v3")
    with pytest.raises(SchemaDrift, match="extra"):
        ORDER.require_aligned({*ORDER.names(), "station"}, ORDER.fingerprint(), what="prompt v3")


def test_changed_matcher_behind_unchanged_names_is_refused() -> None:
    changed = ORDER.model_copy(
        update={
            "fields": tuple(
                FieldSpec(name=f.name, kind=FieldKind.STRING, description=f.description)
                if f.name == "contract_num"
                else f
                for f in ORDER.fields
            )
        }
    )
    assert changed.names() == ORDER.names()
    assert changed.fingerprint() != ORDER.fingerprint()
    with pytest.raises(SchemaDrift, match="rebuild"):
        changed.require_aligned(ORDER.names(), ORDER.fingerprint(), what="training set")
    ORDER.require_aligned(ORDER.names(), ORDER.fingerprint(), what="training set")


def test_duplicate_field_names_are_refused() -> None:
    a = FieldSpec(name="a", kind=FieldKind.STRING, description="")
    with pytest.raises(ValueError, match="twice"):
        CorpusSchema(corpus="x", version=1, description="", fields=(a, a))
