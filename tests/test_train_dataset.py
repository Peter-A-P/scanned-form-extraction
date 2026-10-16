"""The training set is built from the schema, holds no held-out document, and refuses drift."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from legible.data.split import SplitLeak
from legible.schema import FieldKind, FieldSpec, Record, SchemaDrift
from legible.schema.corpora import FARA
from legible.train.dataset import read_training_set, write_training_set

DOCS: list[tuple[str, Record, list[str]]] = [
    (
        "a.pdf",
        {"registrant_name": "DLA Piper US LLP", "registration_num": "3712"},
        ["fara/a/p00.png"],
    ),
    ("b.pdf", {"file_date": "July 16, 2008"}, ["fara/b/p00.png", "fara/b/p01.png"]),
]


def test_round_trip_targets_are_the_schema_json(tmp_path: Path) -> None:
    path = tmp_path / "fara.jsonl"
    assert write_training_set(path, FARA, "FARA-x.json", DOCS, held_out={"c.pdf"}) == 2
    header, rows = read_training_set(path, FARA)
    assert header.rows == 2 and "page images" in header.instruction
    first = next(rows)
    assert json.loads(first.target)["registration_num"] == "3712"
    assert list(json.loads(first.target)) == [f.name for f in FARA.fields]


def test_held_out_document_is_refused(tmp_path: Path) -> None:
    with pytest.raises(SplitLeak):
        write_training_set(tmp_path / "x.jsonl", FARA, "FARA-x.json", DOCS, held_out={"b.pdf"})


def test_set_from_another_schema_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "fara.jsonl"
    write_training_set(path, FARA, "FARA-x.json", DOCS, held_out=set())
    moved = FARA.model_copy(
        update={
            "fields": (
                *FARA.fields,
                FieldSpec(name="address", kind=FieldKind.ADDRESS, description="x"),
            )
        }
    )
    with pytest.raises(SchemaDrift):
        read_training_set(path, moved)
