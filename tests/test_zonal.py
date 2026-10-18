"""NIST's zonal rules on hand-built pages: zones learned where values sit, faces by their
printed words, and a value read from its zone."""

from __future__ import annotations

from legible.arms.ocr import OcrPage, Preprocess, Word
from legible.arms.zonal import FaceRules, Zone, identify, learn_face, locate, read_zone
from legible.schema import Record


def page(rows: list[tuple[int, int, str]]) -> OcrPage:
    """(left, top, text) words on a 1000 by 1000 page; one line per distinct top."""
    tops = sorted({t for _, t, _ in rows})
    words = tuple(
        Word(
            text=x,
            left=left,
            top=top,
            width=10 * len(x),
            height=10,
            conf=90.0,
            block=1,
            par=1,
            line=tops.index(top),
        )
        for left, top, x in rows
    )
    return OcrPage(
        page_path="p.png",
        page_sha256="0" * 64,
        width=1000,
        height=1000,
        tesseract="test",
        preprocess=Preprocess(),
        seconds=1.0,
        words=words,
    )


def filled(amount: str, dy: int) -> tuple[OcrPage, Record]:
    dollars, cents = amount.split()
    return (
        page(
            [
                (10, 10, "Schedule"),
                (100, 10, "Itemized"),
                (10, 500 + dy, "Line"),
                (60, 500 + dy, "7"),
                (700, 500 + dy, dollars),
                (800, 500 + dy, cents),
            ]
        ),
        {"f_line_7": f"{dollars}  {cents}", "f_never": None},
    )


def test_a_value_is_located_as_a_run_of_tokens_on_one_line() -> None:
    p, _ = filled("5140 00", 0)
    box = locate("5140  00", p)
    assert box is not None and box[0] == 0.7 and box[1] == 0.5
    assert locate("9999", p) is None


def test_zones_are_learned_from_three_or_more_samples_and_read_back() -> None:
    pages = [filled(a, dy) for a, dy in (("5140 00", 0), ("12 50", 4), ("789 69", -3))]
    rules = learn_face("sch_a", pages)
    assert set(rules.zones) == {"f_line_7"} and rules.zones["f_line_7"].samples == 3
    assert {"schedule", "itemized", "line"} <= set(rules.template_words)
    test, _ = filled("101 00", 2)
    assert read_zone(test, rules.zones["f_line_7"].box) == "101 00"
    assert learn_face("sch_a", pages[:2]).zones == {}


def test_a_page_is_read_as_the_face_whose_printed_words_it_shows() -> None:
    a = FaceRules(
        face="sch_a", template_words=("schedule", "itemized"), printed=(), anchors={}, zones={}
    )
    b = FaceRules(
        face="1040_1", template_words=("income", "exemptions"), printed=(), anchors={}, zones={}
    )
    p, _ = filled("1 00", 0)
    assert identify(p, {"sch_a": a, "1040_1": b}) == "sch_a"
    assert read_zone(p, Zone(box=(0.0, 0.9, 0.1, 1.0), samples=3).box) is None
