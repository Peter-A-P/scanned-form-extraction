"""A fine-tuned read's confidence: the probability the model gave its own answer, per field.

The fine-tuned and untuned self-hosted arms (B and C) are read with the token log-probabilities
of the answer they wrote (PLAN.md section 2.6). Each field's confidence is the lowest token
probability inside the span of its value in the answer's JSON: a field is as sure as its least
sure token, so one guessed digit in an amount marks the amount. A value written as `null` is
scored the same way, by the tokens of `null`. A field the answer leaves out has no confidence
and goes to review, as does every field of an answer whose tokens are fewer bytes than its
text. Tokens past the text's end (the end-of-turn token vLLM lists) are ignored.

The keys are the ones `legible.agreement.confidences` gives: a scalar's name, and
`group[j].field` for the j-th row of a repeated group.

Token offsets are counted in UTF-8 bytes, because a token can end inside a character.
"""

from __future__ import annotations

import json
import math
from collections.abc import Sequence
from dataclasses import dataclass

from legible.schema import CorpusSchema

#: One generated token: its length in UTF-8 bytes and its natural-log probability.
Token = tuple[int, float]


@dataclass(frozen=True)
class _Span:
    start: int
    end: int


class _Parser:
    """A JSON value parser that records the byte span of every value by its path."""

    def __init__(self, data: bytes) -> None:
        self.data = data
        self.i = 0
        self.spans: dict[tuple[str | int, ...], _Span] = {}

    def _ws(self) -> None:
        while self.i < len(self.data) and self.data[self.i] in b" \t\r\n":
            self.i += 1

    def value(self, path: tuple[str | int, ...]) -> object:
        self._ws()
        start = self.i
        if self.i >= len(self.data):
            raise ValueError("unexpected end")
        c = self.data[self.i : self.i + 1]
        out: object
        if c == b"{":
            out = self._object(path)
        elif c == b"[":
            out = self._array(path)
        elif c == b'"':
            out = self._string()
        else:
            out = self._literal()
        self.spans[path] = _Span(start, self.i)
        return out

    def _object(self, path: tuple[str | int, ...]) -> dict[str, object]:
        self.i += 1
        out: dict[str, object] = {}
        self._ws()
        if self.data[self.i : self.i + 1] == b"}":
            self.i += 1
            return out
        while True:
            self._ws()
            key = self._string()
            self._ws()
            if self.data[self.i : self.i + 1] != b":":
                raise ValueError("expected a colon")
            self.i += 1
            out[key] = self.value((*path, key))
            self._ws()
            c = self.data[self.i : self.i + 1]
            self.i += 1
            if c == b"}":
                return out
            if c != b",":
                raise ValueError("expected a comma")

    def _array(self, path: tuple[str | int, ...]) -> list[object]:
        self.i += 1
        out: list[object] = []
        self._ws()
        if self.data[self.i : self.i + 1] == b"]":
            self.i += 1
            return out
        while True:
            out.append(self.value((*path, len(out))))
            self._ws()
            c = self.data[self.i : self.i + 1]
            self.i += 1
            if c == b"]":
                return out
            if c != b",":
                raise ValueError("expected a comma")

    def _string(self) -> str:
        if self.data[self.i : self.i + 1] != b'"':
            raise ValueError("expected a string")
        j = self.i + 1
        while j < len(self.data):
            if self.data[j : j + 1] == b"\\":
                j += 2
                continue
            if self.data[j : j + 1] == b'"':
                text = json.loads(self.data[self.i : j + 1].decode("utf-8"))
                self.i = j + 1
                return str(text)
            j += 1
        raise ValueError("unterminated string")

    def _literal(self) -> object:
        j = self.i
        while j < len(self.data) and self.data[j : j + 1] not in (b",", b"}", b"]", b" ", b"\n"):
            j += 1
        word = self.data[self.i : j].decode("utf-8")
        self.i = j
        return json.loads(word)


def value_spans(text: str) -> dict[tuple[str | int, ...], tuple[int, int]] | None:
    """The byte span of every value in the first JSON object of the text, or None."""
    data = text.encode("utf-8")
    start = data.find(b"{")
    if start == -1:
        return None
    p = _Parser(data)
    p.i = start
    try:
        p.value(())
    except (ValueError, IndexError, UnicodeDecodeError):
        return None
    return {k: (s.start, s.end) for k, s in p.spans.items()}


def _lowest(tokens: Sequence[Token], ends: Sequence[int], span: tuple[int, int]) -> float:
    """The lowest probability among the tokens that overlap the span."""
    lo, hi = span
    worst = 0.0
    start = 0
    for (_, logprob), end in zip(tokens, ends, strict=True):
        if start >= hi:
            break
        if end > lo:
            worst = min(worst, logprob)
        start = end
    return math.exp(worst)


def confidences(
    schema: CorpusSchema, text: str | None, tokens: Sequence[Token] | None
) -> dict[str, float]:
    """Per-field confidence for a self-hosted read, keyed as `grade_document` takes them."""
    if text is None or not tokens:
        return {}
    ends: list[int] = []
    total = 0
    for n, _ in tokens:
        total += n
        ends.append(total)
    # The server lists the end-of-turn token too, which the answer's text leaves out: the
    # tokens may run past the text's end, never stop short of it.
    if total < len(text.encode("utf-8")):
        return {}
    spans = value_spans(text)
    if spans is None:
        return {}
    out: dict[str, float] = {}
    for f in schema.scalars:
        if (f.name,) in spans:
            out[f.name] = _lowest(tokens, ends, spans[(f.name,)])
    for group in schema.groups:
        j = 0
        while (group.name, j) in spans:
            for g in group.fields:
                key = (group.name, j, g.name)
                if key in spans:
                    out[f"{group.name}[{j}].{g.name}"] = _lowest(tokens, ends, spans[key])
            j += 1
    return out
