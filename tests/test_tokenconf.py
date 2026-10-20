"""The fine-tuned arm's confidence from token log-probabilities, against adversarial answers."""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from legible.arms.frontier import answer_tokens
from legible.schema.corpora import SCHEMAS
from legible.tokenconf import Token, confidences, value_spans


def tokens_of(pieces: list[tuple[str, float]]) -> tuple[str, list[Token]]:
    """An answer and its tokens, from (text, probability) pieces."""
    text = "".join(p for p, _ in pieces)
    return text, [(len(p.encode("utf-8")), math.log(q)) for p, q in pieces]


def test_a_field_is_as_sure_as_its_least_sure_token() -> None:
    text, toks = tokens_of(
        [
            ('{"file_date":"', 0.99),
            ("2019", 0.95),
            ("-0", 0.40),
            ('3-01"', 0.90),
            (',"registrant_name":', 0.99),
            ("null", 0.70),
            ("}", 0.99),
        ]
    )
    c = confidences(SCHEMAS["fara"], text, toks)
    # The opening quote's token also carries the key, so it counts: the lowest is 0.40.
    assert c["file_date"] == pytest.approx(0.40)
    assert c["registrant_name"] == pytest.approx(0.70)


def test_a_field_left_out_has_no_confidence() -> None:
    text, toks = tokens_of([('{"file_date":"2019-03-01"}', 0.9)])
    c = confidences(SCHEMAS["fara"], text, toks)
    assert "file_date" in c
    assert "signer_name" not in c


def test_tokens_that_do_not_spell_the_answer_give_nothing() -> None:
    text, toks = tokens_of([('{"file_date":"2019"}', 0.9)])
    assert confidences(SCHEMAS["fara"], text + " ", toks) == {}
    assert confidences(SCHEMAS["fara"], text, []) == {}
    assert confidences(SCHEMAS["fara"], None, toks) == {}


def test_an_end_of_turn_token_past_the_text_is_ignored() -> None:
    text, toks = tokens_of([('{"file_date":"', 0.99), ("2019", 0.5), ('"}', 0.99)])
    toks.append((7, math.log(0.01)))  # "<turn|>", listed but not in the text
    assert confidences(SCHEMAS["fara"], text, toks)["file_date"] == pytest.approx(0.5)


def test_unparseable_json_gives_nothing() -> None:
    text, toks = tokens_of([('{"file_date":"2019', 0.9)])
    assert confidences(SCHEMAS["fara"], text, toks) == {}


def test_a_token_ending_inside_a_character_is_counted_in_bytes() -> None:
    # "é" is two bytes; a tokenizer may split it, and the halves still spell the answer.
    e = "é".encode()
    text = '{"registrant_name":"Caf' + "é" + '"}'
    head = len(b'{"registrant_name":"Caf')
    toks: list[Token] = [(head, math.log(0.9)), (1, math.log(0.3)), (1, math.log(0.8))]
    toks.append((len(text.encode()) - head - len(e), math.log(0.95)))
    c = confidences(SCHEMAS["fara"], text, toks)
    assert c["registrant_name"] == pytest.approx(0.3)


def test_repeated_rows_are_keyed_by_row_and_column() -> None:
    text, toks = tokens_of(
        [
            ('{"menu":[{"nm":"', 0.99),
            ("TEA", 0.5),
            ('","num":"1"},{"nm":"', 0.99),
            ("RICE", 0.8),
            ('"}],"total_price":"', 0.99),
            ("9", 0.6),
            ('"}', 0.99),
        ]
    )
    c = confidences(SCHEMAS["cord"], text, toks)
    assert c["menu[0].nm"] == pytest.approx(0.5)
    assert c["menu[1].nm"] == pytest.approx(0.8)
    assert c["menu[0].num"] == pytest.approx(0.99)
    assert "menu[1].num" not in c
    assert c["total_price"] == pytest.approx(0.6)


def test_spans_skip_prose_before_the_object_and_escapes_inside_strings() -> None:
    text = 'Here: {"a":"say \\"hi\\"","b":[1,2]}'
    spans = value_spans(text)
    assert spans is not None
    a0, a1 = spans[("a",)]
    assert text.encode()[a0:a1] == b'"say \\"hi\\""'
    assert text.encode()[slice(*spans[("b", 1)])] == b"2"


def test_answer_tokens_reads_an_openai_shaped_body() -> None:
    raw = {
        "choices": [
            {
                "logprobs": {
                    "content": [
                        {"token": "{", "logprob": -0.1, "bytes": [123]},
                        {"token": "é", "logprob": -0.2, "bytes": [195, 169]},
                        {"token": "}", "logprob": -0.3},
                    ]
                }
            }
        ]
    }
    assert answer_tokens(raw) == [(1, -0.1), (2, -0.2), (1, -0.3)]
    assert answer_tokens({"choices": [{"message": {}}]}) is None
    assert answer_tokens(None) is None


def test_a_logprobs_run_is_graded_with_its_token_confidences(tmp_path: Path) -> None:
    from legible.arms.frontier import Read, RunDir
    from legible.report import Truth, token_grades
    from legible.schema import Record
    from tests.schemas import ORDER

    text, toks = tokens_of(
        [
            ('{"advertiser":"', 0.99),
            ("Smith", 0.9),
            ('","contract_num":"', 0.99),
            ("1", 0.2),
            ('2345"}', 0.99),
        ]
    )
    run = RunDir(tmp_path / "run")
    (tmp_path / "run" / "run.json").write_text("{}", encoding="utf-8")
    common = dict(status="200", cost_usd=None, input_tokens=1, output_tokens=1)
    run.add_reads(
        [
            Read(
                doc_id="d",
                text=text,
                tokens=toks,
                latency_ms=None,
                ledger_id=None,
                model_returned=None,
                **common,
            )
        ]
    )
    truth: Record = {
        "advertiser": "Smith",
        "agency": None,
        "contract_num": "99999",
        "flight_from": None,
        "gross_amount": "$400.00",
        "product": None,
        "line_item": [],
    }
    grades = token_grades(["d", "missing"], {"d": Truth(ORDER, truth, {}, None, 1)}, [run.path])
    assert grades is not None and len(grades) == 1
    by_path = {o.path: o for o in grades[0].outcomes}
    assert by_path["advertiser"].confidence == pytest.approx(0.9)
    assert by_path["contract_num"].confidence == pytest.approx(0.2)
    assert by_path["gross_amount"].confidence is None  # left out of the answer: to review
    assert token_grades(["d"], {}, [tmp_path / "nowhere"]) is None
