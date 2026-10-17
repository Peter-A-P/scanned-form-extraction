"""Arm E's engine on hand-built OCR pages: anchors, columns, rows, and a template it lacks."""

from __future__ import annotations

from legible.arms.ocr import OcrPage, Preprocess, Word
from legible.arms.rule_sets import FARA_BY_TEMPLATE, fara_rules
from legible.arms.rules import Extract, RowRule, TemplateRules, apply_extract, lines_of, read
from legible.arms.rules_run import RulesRead, answer
from legible.grade import Outcome, grade_document
from tests.schemas import ORDER


def page(rows: list[list[tuple[int, str]]], *, height: int = 3300) -> OcrPage:
    """One page: each row a line at 100 px spacing, each (left, text) a word."""
    words = []
    for line_no, row in enumerate(rows, 1):
        for left, text in row:
            words.append(
                Word(
                    text=text,
                    left=left,
                    top=100 * line_no,
                    width=20 * len(text),
                    height=30,
                    conf=95.0,
                    block=line_no,
                    par=1,
                    line=1,
                )
            )
    return OcrPage(
        page_path="x/p00.png",
        page_sha256="0" * 64,
        width=2550,
        height=height,
        tesseract="test",
        preprocess=Preprocess(),
        seconds=0.0,
        words=tuple(words),
    )


ORDER_PAGE = page(
    [
        [(100, "ORDER"), (300, "CONFIRMATION")],
        [
            (100, "Advertiser:"),
            (400, "Smith"),
            (520, "for"),
            (600, "Senate"),
            (1500, "Order"),
            (1650, "#"),
            (1700, "12345"),
        ],
        [(100, "1."), (150, "Name"), (1200, "2."), (1250, "Registration"), (1500, "No.")],
        [(1250, "3712")],
        [(100, "DLA"), (200, "Piper"), (330, "US"), (400, "LLP")],
        [(100, "Line"), (300, "Channel"), (600, "Description")],
        [(100, "1"), (300, "9"), (600, "News"), (720, "at"), (800, "6"), (1500, "$400.00")],
        [(600, "03/15/21"), (800, "to"), (900, "03/21/21")],
        [(100, "Gross"), (300, "Total"), (1500, "$400.00")],
    ]
)


def test_right_of_anchor_stops_at_the_next_label() -> None:
    lines = lines_of([ORDER_PAGE])
    ex = Extract(anchor=r"Advertiser:", stop=r"\sOrder\b")
    assert apply_extract(lines, ex) == "Smith for Senate"


def test_below_reads_the_anchors_column_only() -> None:
    lines = lines_of([ORDER_PAGE])
    number = Extract(anchor=r"Registration No", where="below", lines=2, value=r"\b(\d{3,6})\b")
    name = Extract(anchor=r"^1\.\s*Name", where="below", column_end=r"^2\.?$")
    assert apply_extract(lines, number) == "3712"
    assert apply_extract(lines, name) == "DLA Piper US LLP"


def test_rows_take_their_continuation_line() -> None:
    rules = TemplateRules(
        name="t",
        detect=(r"ORDER CONFIRMATION",),
        fields={"gross_amount": (Extract(anchor=r"Gross Total", value=r"(\$[\d,]+\.\d{2})"),)},
        rows=(
            RowRule(
                group="line_item",
                start=r"Line\s+Channel",
                end=r"Gross Total",
                pattern=r"^\d+\s+\S+\s+(?P<program>.+?)\s+(?P<amount>\$[\d,]+\.\d{2})$",
                exclude=r"\d/\d",
                continuation=r"(?P<start>\d{2}/\d{2}/\d{2})",
            ),
        ),
    )
    out = read(ORDER, [ORDER_PAGE], (rules,))
    assert out is not None
    assert out["gross_amount"] == "$400.00"
    assert out["line_item"] == [{"program": "News at 6", "start": "03/15/21", "amount": "$400.00"}]


def test_a_document_no_rule_set_recognises_gets_no_answer() -> None:
    rules = TemplateRules(name="t", detect=(r"DISSEMINATION REPORT",), fields={})
    assert read(ORDER, [ORDER_PAGE], (rules,)) is None


def test_a_fara_split_gets_only_its_training_templates_rules() -> None:
    names = {r.name for r in fara_rules({"Short-Form", "Dissemination Report"})}
    assert names == {"fara-short-form", "fara-dissemination-report"}
    assert FARA_BY_TEMPLATE["Amendment"].name not in names


def test_an_unrecognised_document_is_graded_missing_not_malformed() -> None:
    unread = RulesRead(doc_id="d", output=None, ocr_seconds=1.0, rule_set=None)
    truth = {"advertiser": "Smith for Senate", "gross_amount": "$400.00", "line_item": []}
    g = grade_document(ORDER, "d", truth, answer(unread))
    assert {o.outcome for o in g.outcomes} == {Outcome.MISSING} and not g.unparsed
