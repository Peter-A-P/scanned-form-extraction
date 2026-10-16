"""CORD's gt_parse as truth, on receipts shaped like the real ones."""

from __future__ import annotations

import pytest

from legible.data.cord import parse_gt, shard_split
from legible.grade import grade_document
from legible.schema import SchemaDrift
from legible.schema.corpora import CORD

ONE_ITEM = {
    "menu": {
        "nm": "-TICKET CP",
        "num": "901016",
        "cnt": "2",
        "price": "60.000",
        "itemsubtotal": "60.000",
    },
    "sub_total": {"subtotal_price": "60.000", "discount_price": "-60.000", "tax_price": "5.455"},
    "total": {"total_price": "60.000", "creditcardprice": "60.000", "menuqty_cnt": "2.00"},
}


def test_single_item_dict_becomes_one_row() -> None:
    truth, alternatives = parse_gt("test-0000", ONE_ITEM)
    assert truth["menu"] == [
        {
            "nm": "-TICKET CP",
            "num": "901016",
            "unitprice": None,
            "cnt": "2",
            "discountprice": None,
            "price": "60.000",
            "itemsubtotal": "60.000",
            "vatyn": None,
            "etc": None,
        }
    ]
    assert truth["sub_item"] == [] and truth["void_menu"] == []
    assert truth["menuqty_cnt"] == "2.00"
    assert alternatives == {}


def test_sub_items_and_repeated_scalars() -> None:
    gt = {
        "menu": [
            {
                "nm": "Paket A",
                "price": "45,000",
                "sub": [{"nm": "Nasi"}, {"nm": "Es Teh", "cnt": "1"}],
            },
            {"nm": "Kerupuk", "price": "5,000", "sub": {"nm": "Pedas"}},
        ],
        "sub_total": {"subtotal_price": "50,000", "tax_price": ["2,500", "2,500"], "etc": "PB1"},
        "total": {"total_price": "55,000", "cashprice": ["50,000", "10,000"]},
    }
    truth, alternatives = parse_gt("train-0001", gt)
    subs = truth["sub_item"]
    assert isinstance(subs, list)
    assert [s["nm"] for s in subs] == ["Nasi", "Es Teh", "Pedas"]
    assert truth["subtotal_etc"] == "PB1"
    assert truth["tax_price"] == "2,500" and "tax_price" not in alternatives
    assert truth["cashprice"] == "50,000" and alternatives == {"cashprice": ["10,000"]}


def test_receipt_conventions_grade_as_the_same_amount() -> None:
    truth, alternatives = parse_gt("test-0000", ONE_ITEM)
    pred = {
        "menu": [
            {
                "nm": "-TICKET CP",
                "num": "901016",
                "cnt": "2x",
                "price": "Rp 60,000",
                "itemsubtotal": "60000",
            }
        ],
        "subtotal_price": "60,000",
        "discount_price": "-60.000",
        "tax_price": "5455",
        "total_price": "Rp.60.000",
        "creditcardprice": "60.000,00",
        "menuqty_cnt": "2",
    }
    g = grade_document(CORD, "test-0000", truth, pred, alternatives=alternatives)
    assert g.all_right, [o for o in g.outcomes if not o.correct]


def test_unknown_keys_are_refused() -> None:
    with pytest.raises(SchemaDrift):
        parse_gt("x", {"menu": {"nm": "A", "colour": "red"}})
    with pytest.raises(SchemaDrift):
        parse_gt("x", {"store_info": {"name": "A"}})
    with pytest.raises(SchemaDrift):
        parse_gt("x", {"total": {"tip_price": "1"}})


def test_shard_names_map_to_splits() -> None:
    assert shard_split("data/validation-00000-of-00001-cc3c5779fe22e8ca.parquet") == "dev"
    assert shard_split("data/train-00003-of-00004-2d0cd200555ed7fd.parquet") == "train"
