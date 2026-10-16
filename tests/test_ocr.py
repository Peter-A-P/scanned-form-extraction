"""Tesseract's TSV, the positioned text and word accuracy, without Tesseract."""

from __future__ import annotations

import pytest

from legible.arms.ocr import parse_tsv, positioned_text, word_accuracy

HEADER = (
    "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext"
)


def row(
    level: int, block: int, line: int, word: int, left: int, top: int, text: str, conf: float = 95.0
) -> str:
    return f"{level}\t1\t{block}\t1\t{line}\t{word}\t{left}\t{top}\t50\t20\t{conf}\t{text}"


TSV = "\n".join(
    [
        HEADER,
        row(1, 0, 0, 0, 0, 0, "", -1),
        row(5, 1, 1, 1, 100, 100, "Advertiser:"),
        row(5, 1, 1, 2, 800, 102, "Smith"),
        row(5, 1, 1, 3, 870, 101, "for"),
        row(5, 2, 1, 1, 100, 300, "Gross"),
        row(5, 2, 1, 2, 1500, 300, "$12,500.00"),
        row(5, 2, 1, 3, 1600, 300, " ", 0),
    ]
)


def test_tsv_keeps_only_words() -> None:
    words = parse_tsv(TSV)
    assert [w.text for w in words] == ["Advertiser:", "Smith", "for", "Gross", "$12,500.00"]
    assert words[1].left == 800 and words[1].conf == 95.0


def test_positioned_text_keeps_values_beside_their_labels() -> None:
    text = positioned_text(parse_tsv(TSV), page_width=2000, columns=100)
    lines = text.splitlines()
    assert lines[0].startswith("     Advertiser:")
    assert lines[0].index("Smith") == 40
    assert lines[1].index("$12,500.00") == 75
    assert lines[0].endswith("Smith for")


def test_lines_are_ordered_top_to_bottom() -> None:
    reordered = "\n".join([HEADER, *reversed(TSV.splitlines()[1:])])
    assert positioned_text(parse_tsv(reordered), 2000) == positioned_text(parse_tsv(TSV), 2000)


@pytest.mark.parametrize(
    ("hyp", "ref", "acc"),
    [
        ("a b c d", "a b c d", 1.0),
        ("a x c d", "a b c d", 0.75),
        ("a c d", "a b c d", 0.75),
        ("", "a b", 0.0),
        ("", "", 1.0),
        ("a b c d e f", "a b", -1.0),
    ],
)
def test_word_accuracy(hyp: str, ref: str, acc: float) -> None:
    assert word_accuracy(hyp.split(), ref.split()) == pytest.approx(acc)
