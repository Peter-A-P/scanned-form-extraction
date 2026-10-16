"""The prompt is built from the schema and refused when the schema moves under it."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from legible.prompt import build_prompt, load_prompt, save_prompt
from legible.schema import FieldKind, FieldSpec, SchemaDrift
from legible.schema.corpora import CORD, DEEPFORM, FARA


@pytest.mark.parametrize("schema", [FARA, DEEPFORM, CORD])
def test_prompt_names_every_field_and_carries_the_json_schema(schema: object) -> None:
    from legible.schema import CorpusSchema

    assert isinstance(schema, CorpusSchema)
    p = build_prompt(schema)
    assert set(p.fields) == schema.names()
    for f in schema.fields:
        assert f"- {f.name}" in p.text
    embedded = json.loads(p.text.rsplit("\n", 1)[1])
    assert embedded == schema.json_schema()


def test_prompt_is_plain_ascii() -> None:
    for schema in (FARA, DEEPFORM, CORD):
        assert build_prompt(schema).text.isascii()


def test_stored_prompt_round_trips_and_refuses_drift(tmp_path: Path) -> None:
    path = tmp_path / "fara-v1.json"
    save_prompt(build_prompt(FARA), path)
    assert load_prompt(path, FARA).text == build_prompt(FARA).text
    moved = FARA.model_copy(
        update={
            "fields": (
                *FARA.fields[:-1],
                FieldSpec(name="signer_title", kind=FieldKind.NAME, description="x"),
            )
        }
    )
    with pytest.raises(SchemaDrift):
        load_prompt(path, moved)


def test_ocr_text_prompt_differs_only_in_its_source() -> None:
    images = build_prompt(DEEPFORM)
    text = build_prompt(DEEPFORM, source="ocr_text")
    assert "page images" in images.text and "OCR text" in text.text
    assert images.text.split("Rules:")[1] == text.text.split("Rules:")[1]
    assert images.schema_fingerprint == text.schema_fingerprint
