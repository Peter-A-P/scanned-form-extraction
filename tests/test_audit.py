"""The audit sample is fixed, spread across documents, and its rate is arithmetic."""

from __future__ import annotations

import io

import pytest
from PIL import Image

from legible.data.audit import (
    Decision,
    Label,
    crop,
    flat_values,
    report,
    sample,
    worksheet,
)


def labels(corpus: str, docs: int, per_doc: int) -> list[Label]:
    return [
        Label(
            corpus=corpus,
            doc_id=f"d{d}",
            key=f"f{k}",
            value=f"v{d}{k}",
            box=(0, 0.1, 0.1, 0.2, 0.2),
        )
        for d in range(docs)
        for k in range(per_doc)
    ]


ALL = labels("fara", 100, 3) + labels("deepform", 100, 5) + labels("cord", 100, 4)


def test_sample_meets_quotas_one_label_per_document() -> None:
    s = sample(ALL)
    assert [sum(x.corpus == c for x in s) for c in ("fara", "deepform", "cord")] == [60, 80, 60]
    for c in ("fara", "deepform", "cord"):
        docs = [x.doc_id for x in s if x.corpus == c]
        assert len(docs) == len(set(docs))


def test_sample_is_fixed_and_independent_of_input_order() -> None:
    assert sample(ALL) == sample(list(reversed(ALL)))


def test_too_few_documents_is_refused() -> None:
    with pytest.raises(ValueError, match="quota"):
        sample(labels("fara", 10, 3) + labels("deepform", 100, 1) + labels("cord", 100, 1))


def test_flat_values_match_box_keys() -> None:
    truth = {"a": "x", "b": None, "line_item": [{"c": "y", "d": None}]}
    assert flat_values(truth) == {"a": "x", "line_item[0].c": "y"}


def test_report_excludes_unreadable_and_needs_every_decision() -> None:
    s = sample(ALL)
    decisions = [
        Decision(label_id=x.label_id, verdict="wrong" if i % 10 == 0 else "right")
        for i, x in enumerate(s)
    ]
    decisions[1] = Decision(label_id=s[1].label_id, verdict="unreadable")
    reports = {r.corpus: r for r in report(s, decisions) if r.stratum == "all"}
    assert reports["fara"].audited == 59 and reports["fara"].unreadable == 1
    assert reports["fara"].disagreement.point == pytest.approx(6 / 59)
    with pytest.raises(ValueError, match="no decision"):
        report(s, decisions[:-1])


def test_crop_and_worksheet() -> None:
    page = io.BytesIO()
    Image.new("L", (1000, 1000), 255).save(page, format="PNG")
    c = crop(page.getvalue(), (0, 0.1, 0.1, 0.2, 0.2))
    with Image.open(io.BytesIO(c)) as img:
        assert img.size == (180, 180)  # 0.1 wide plus 0.04 either side
    s = sample(ALL)[:2]
    html = worksheet(s, {x.label_id: c for x in s})
    assert html.count("<section") == 2 and "decisions.json" in html
    assert html.isascii()


def test_corpora_with_line_items_are_split_half_and_half() -> None:
    items = [
        Label(
            corpus="deepform",
            doc_id=f"d{d}",
            key=f"line_item[{k}].channel",
            value="9",
            box=(0, 0.1, 0.1, 0.2, 0.2),
        )
        for d in range(200)
        for k in range(10)
    ]
    heads = [
        Label(
            corpus="deepform",
            doc_id=f"d{d}",
            key="advertiser",
            value="A",
            box=(0, 0.1, 0.1, 0.2, 0.2),
        )
        for d in range(200)
    ]
    s = sample(labels("fara", 100, 3) + heads + items + labels("cord", 100, 4))
    deepform = [x for x in s if x.corpus == "deepform"]
    assert sum("[" in x.key for x in deepform) == 40
    assert sum("[" not in x.key for x in deepform) == 40
    strata = {
        (r.corpus, r.stratum)
        for r in report(s, [Decision(label_id=x.label_id, verdict="right") for x in s])
    }
    assert ("deepform", "line items") in strata and ("fara", "line items") not in strata
