"""Arm F: the labels drawn on the service's words, its answers read back into the schema, and
the document it is sent."""

from __future__ import annotations

import base64
import io
from pathlib import Path
from typing import Any

from PIL import Image

from legible.arms.docintel import (
    analyze_request,
    document_tiff,
    fields_file,
    find_words,
    labels,
    model_id,
    receipt_record,
    to_record,
)
from legible.schema.corpora import SCHEMAS


def _page(*words: str, width: float = 1000, height: float = 2000) -> dict[str, Any]:
    return {
        "width": width,
        "height": height,
        "words": [
            {"content": w, "polygon": [10 * i, 20, 10 * i + 9, 20, 10 * i + 9, 40, 10 * i, 40]}
            for i, w in enumerate(words)
        ],
    }


def test_a_value_is_found_on_consecutive_words_whatever_its_case_and_punctuation() -> None:
    pages = [_page("Registrant:", "ACME", "Corp.,", "Inc", "dated")]
    assert find_words("Acme Corp Inc", pages) == [(0, 1), (0, 2), (0, 3)]
    assert find_words("Acme Inc", pages) is None  # not consecutive
    assert find_words("Widgets", pages) is None


def test_two_fields_with_one_value_label_two_places() -> None:
    pages = [_page("John", "Smith", "signed", "John", "Smith")]
    used: set[tuple[int, int]] = set()
    first = find_words("John Smith", pages, used)
    assert first is not None
    used.update(first)
    assert find_words("John Smith", pages, used) == [(0, 3), (0, 4)]


def test_labels_carry_normalised_boxes_and_count_what_was_not_found() -> None:
    schema = SCHEMAS["fara"]
    record = {f.name: None for f in schema.fields} | {
        "registrant_name": "Acme Corp",
        "signer_title": "President of nothing on the page",
    }
    out, total, found = labels(schema, "d.tiff", record, {"pages": [_page("Acme", "Corp")]})
    assert (total, found) == (2, 1)
    (label,) = out["labels"]
    assert label["label"] == "registrant_name" and label["value"][0]["page"] == 1
    box = label["value"][0]["boundingBoxes"][0]
    assert len(box) == 8 and all(0 <= v <= 1 for v in box)
    assert box[1] == 0.01  # 20 over a height of 2,000


def test_a_table_is_labelled_row_by_row_and_declared_as_an_array() -> None:
    schema = SCHEMAS["deepform"]
    record: dict[str, Any] = {f.name: None for f in schema.fields}
    record["line_item"] = [{"channel": "KOMO", "program_desc": None}, {"channel": "KING"}]
    out, total, found = labels(schema, "d.tiff", record, {"pages": [_page("KOMO", "x", "KING")]})
    assert (total, found) == (2, 2)
    assert [x["label"] for x in out["labels"]] == ["line_item/0/channel", "line_item/1/channel"]
    spec = fields_file(schema)
    line = next(f for f in spec["fields"] if f["fieldKey"] == "line_item")
    assert line["fieldType"] == "array" and line["itemType"] in spec["definitions"]


def test_the_answer_is_read_back_as_printed_and_missing_fields_are_null() -> None:
    schema = SCHEMAS["deepform"]
    analyze = {
        "documents": [
            {
                "fields": {
                    "advertiser": {"type": "string", "content": "Smith for Senate"},
                    "gross_amount": {"type": "string", "valueString": "$4,200.00"},
                    "line_item": {
                        "type": "array",
                        "valueArray": [
                            {"type": "object", "valueObject": {"channel": {"content": "KOMO"}}},
                            {"type": "object", "valueObject": {}},
                        ],
                    },
                }
            }
        ]
    }
    rec = to_record(schema, analyze)
    assert rec["advertiser"] == "Smith for Senate" and rec["gross_amount"] == "$4,200.00"
    assert rec["agency"] is None
    assert rec["line_item"] == [
        {c: ("KOMO" if c == "channel" else None) for c in rec["line_item"][0]}
    ]  # the empty row is dropped
    assert to_record(schema, {})["advertiser"] is None


def test_the_receipt_model_maps_onto_cords_fields() -> None:
    analyze = {
        "documents": [
            {
                "fields": {
                    "Total": {"content": "45,500"},
                    "Items": {
                        "valueArray": [
                            {
                                "valueObject": {
                                    "Description": {"content": "EGG TART"},
                                    "Quantity": {"content": "1"},
                                    "TotalPrice": {"content": "13,000"},
                                }
                            }
                        ]
                    },
                }
            }
        ]
    }
    rec = receipt_record(SCHEMAS["cord"], analyze)
    assert rec["total_price"] == "45,500" and rec["subtotal_price"] is None
    assert rec["menu"][0]["nm"] == "EGG TART" and rec["menu"][0]["price"] == "13,000"
    assert rec["sub_item"] == [] and rec["cashprice"] is None


def test_the_document_is_the_pages_pixels_in_order(tmp_path: Path) -> None:
    paths = []
    for i, shade in enumerate((0, 128)):
        p = tmp_path / f"p{i}.png"
        Image.new("L", (40, 30), shade).save(p)
        paths.append(p)
    tiff = document_tiff(paths)
    with Image.open(io.BytesIO(tiff)) as img:
        assert getattr(img, "n_frames", 1) == 2
        img.seek(1)
        assert img.getpixel((0, 0)) == 128
    req = analyze_request("azure-docintel/custom/x", tiff, 2)
    block = req.messages[0]["content"][0]
    assert base64.b64decode(block["source"]["data"]) == tiff and req.extra["pages"] == 2


def test_model_ids_are_in_the_characters_the_service_allows() -> None:
    assert model_id("fara-unseen-short-form-s0") == "legible-fara-unseen-short-form-s0"
    assert model_id("a b,c") == "legible-a-b-c"
