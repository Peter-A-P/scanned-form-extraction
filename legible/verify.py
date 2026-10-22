"""The verifier: arithmetic and format checks a form defines, run after extraction.

A receipt's line items sum to its subtotal and subtotal plus tax to its total; a date parses;
a registration number has its pattern; a 1040 line the form defines as a sum is that sum.
None of this needs a model, and every error it catches is one a person does not have to. It
is reported as two numbers: the share of wrong fields it flags (the catch rate) and the share
of right fields it flags (the false alarms that a reviewer pays for).

A failing rule flags every field it reads, because arithmetic says that one of them is wrong
and not which.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from legible.grade import DocGrade, parse_date, parse_number
from legible.schema import CorpusSchema, FieldKind, FieldSpec, GroupSpec
from legible.stats import Interval, ratio_ci


class SumRule(BaseModel):
    """`total` equals the sum of `parts`. A part is a scalar field, or `group.field` for
    the sum over that group's items. Blank parts count as zero; a blank total skips."""

    model_config = ConfigDict(frozen=True)

    kind: Literal["sum"] = "sum"
    name: str
    parts: tuple[str, ...]
    total: str
    tolerance: float = 0.005
    #: Parts that must be filled in for the rule to apply: a receipt that prints no subtotal
    #: says nothing about how its total was reached.
    requires: tuple[str, ...] = ()


class PatternRule(BaseModel):
    """A non-blank `field` matches `pattern` in full."""

    model_config = ConfigDict(frozen=True)

    kind: Literal["pattern"] = "pattern"
    name: str
    field: str
    pattern: str


class DateRule(BaseModel):
    """A non-blank date field parses as a date."""

    model_config = ConfigDict(frozen=True)

    kind: Literal["date"] = "date"
    name: str
    field: str


Rule = SumRule | PatternRule | DateRule


def _spec(schema: CorpusSchema, path: str) -> FieldSpec:
    head, _, tail = path.partition(".")
    for f in schema.fields:
        if f.name == head:
            if isinstance(f, GroupSpec):
                return f.field(tail)
            return f
    raise KeyError(f"{schema.corpus} has no field {path!r}")


#: The kinds a sum may read. NIST's amounts are codes, because the form prints dollars and
#: cents in separate boxes ("5140  00", "36237  -"); `parse_box_amount` reads them.
SUMMABLE = {FieldKind.PRICE, FieldKind.NUMBER, FieldKind.CODE}


def check_rules(schema: CorpusSchema, rules: Sequence[Rule]) -> None:
    """Refuse a rule that names a field the schema does not, or a sum over a non-number."""
    for rule in rules:
        paths = (*rule.parts, rule.total) if isinstance(rule, SumRule) else (rule.field,)
        for p in paths:
            spec = _spec(schema, p)
            if isinstance(rule, SumRule) and spec.kind not in SUMMABLE:
                raise ValueError(f"rule {rule.name} sums {p}, which is {spec.kind}")


_BOXES = re.compile(r"(\d+)(?:\s+(\d\d|-))?")


def parse_box_amount(value: str) -> float | None:
    """An amount a tax form prints in a dollars box and a cents box, as NIST SD2's answers
    keep it: "5140  00" is 5140.00, "36237  -" is 36237, "$5019  -" has a dollar sign, and
    "-2343  14" or "(4238  16)" is negative. Commas separate thousands."""
    s = value.strip().replace("$", "").replace(",", "")
    negative = False
    if s.startswith("(") and s.endswith(")"):
        negative, s = True, s[1:-1].strip()
    if s.startswith("-"):
        negative, s = True, s[1:].strip()
    m = _BOXES.fullmatch(s)
    if m is None:
        return None
    cents = m.group(2)
    number = float(m.group(1)) + (int(cents) / 100 if cents and cents != "-" else 0.0)
    return -number if negative else number


def _number(schema: CorpusSchema, path: str, value: object) -> float | None:
    if not isinstance(value, str) or not value.strip():
        return None
    spec = _spec(schema, path)
    if spec.kind is FieldKind.CODE:
        return parse_box_amount(value)
    return parse_number(value, spec.decimal_mark)


def _sum_part(schema: CorpusSchema, record: Mapping[str, Any], path: str) -> float | None:
    """The value of one part, or None when a printed value does not parse (the rule then
    fails, because an unparsable amount is a wrong amount)."""
    head, _, tail = path.partition(".")
    if not tail:
        value = record.get(head)
        if value is None or (isinstance(value, str) and not value.strip()):
            return 0.0
        return _number(schema, path, value)
    total = 0.0
    items = record.get(head)
    for item in items if isinstance(items, list) else []:
        value = item.get(tail) if isinstance(item, Mapping) else None
        if value is None or (isinstance(value, str) and not value.strip()):
            continue
        n = _number(schema, path, value)
        if n is None:
            return None
        total += n
    return total


def _filled(record: Mapping[str, Any], path: str) -> bool:
    head, _, tail = path.partition(".")
    value = record.get(head)
    if not tail:
        return isinstance(value, str) and bool(value.strip())
    return isinstance(value, list) and any(
        isinstance(i, Mapping) and isinstance(i.get(tail), str) and i[tail].strip() for i in value
    )


def applies(rule: Rule, record: Mapping[str, Any]) -> bool:
    """Whether a rule says anything about this record: a sum whose total (and every part it
    requires) is filled in, a pattern or date field with a value."""
    if isinstance(rule, SumRule):
        return _filled(record, rule.total) and all(_filled(record, p) for p in rule.requires)
    return _filled(record, rule.field)


def flagged(schema: CorpusSchema, rules: Sequence[Rule], record: Mapping[str, Any]) -> set[str]:
    """The field paths a predicted record's failing rules flag."""
    out: set[str] = set()
    for rule in rules:
        if isinstance(rule, SumRule):
            if not applies(rule, record):
                continue
            raw_total = record.get(rule.total)
            total = _number(schema, rule.total, raw_total)
            parts = [_sum_part(schema, record, p) for p in rule.parts]
            if (
                total is None
                or any(p is None for p in parts)
                or not math.isclose(
                    sum(p for p in parts if p is not None), total, abs_tol=rule.tolerance
                )
            ):
                out.update(rule.parts)
                out.add(rule.total)
        elif isinstance(rule, PatternRule):
            value = record.get(rule.field)
            if (
                isinstance(value, str)
                and value.strip()
                and not re.fullmatch(rule.pattern, value.strip())
            ):
                out.add(rule.field)
        else:
            value = record.get(rule.field)
            spec = _spec(schema, rule.field)
            if (
                isinstance(value, str)
                and value.strip()
                and parse_date(value, day_first=spec.day_first) is None
            ):
                out.add(rule.field)
    return out


class CatchRate(BaseModel):
    model_config = ConfigDict(frozen=True)

    catch_rate: Interval
    false_alarm_rate: Interval
    #: The catch rate among the wrong fields some rule reads: what the rules do where they
    #: look, apart from how much of the form they cover. None when no reads were given.
    reach_catch_rate: Interval | None = None


def read_by(rules: Sequence[Rule]) -> set[str]:
    """Every field path a set of rules reads."""
    out: set[str] = set()
    for rule in rules:
        out.update((*rule.parts, rule.total) if isinstance(rule, SumRule) else (rule.field,))
    return out


def catch_rate(
    grades: Sequence[DocGrade],
    flags: Mapping[str, set[str]],
    *,
    reads: Mapping[str, set[str]] | None = None,
    seed: int = 0,
) -> CatchRate:
    """Share of wrong fields flagged, and of right fields flagged, over documents.
    `flags` maps document id to the paths `flagged` returned for its prediction; `reads`,
    if given, maps it to the paths its rules read, for the catch rate where they look."""
    caught: list[float] = []
    wrong: list[float] = []
    alarms: list[float] = []
    right: list[float] = []
    reach_caught: list[float] = []
    reach_wrong: list[float] = []
    for g in grades:
        f = flags.get(g.doc_id, set())
        caught.append(float(sum(not o.correct and o.path in f for o in g.outcomes)))
        wrong.append(float(sum(not o.correct for o in g.outcomes)))
        alarms.append(float(sum(o.correct and o.path in f for o in g.outcomes)))
        right.append(float(sum(o.correct for o in g.outcomes)))
        if reads is not None:
            r = reads.get(g.doc_id, set())
            reach_caught.append(
                float(sum(not o.correct and o.path in f and o.path in r for o in g.outcomes))
            )
            reach_wrong.append(float(sum(not o.correct and o.path in r for o in g.outcomes)))
    return CatchRate(
        catch_rate=ratio_ci(caught, wrong, seed=seed),
        false_alarm_rate=ratio_ci(alarms, right, seed=seed),
        reach_catch_rate=ratio_ci(reach_caught, reach_wrong, seed=seed)
        if reads is not None
        else None,
    )
