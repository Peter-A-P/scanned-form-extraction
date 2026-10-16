"""Field-level grading against the corpus label, and the miss taxonomy.

Grading is a program. No model is asked whether another model was right, here or anywhere
else in this project, because a judge that drifts makes every number downstream of it
unfalsifiable.

A wrong field is wrong in one of a few ways, and which way matters more than the accuracy
figure does. Reading the advertiser into the agency box is a different failure from copying a
number off the wrong line, and both are different from filling a box that is empty on the
page. The last is the one that matters most on a form a person trusts: an empty answer can be
routed to a clerk, an invented one goes into the record. So every miss is classified, and the
hallucination rate is reported beside accuracy, never folded into it.

What is scored: every field whose truth or prediction is non-blank. A field blank in both is
a correct abstention and is counted, but it is not in the accuracy denominator, because a
schema with many rarely-printed fields would otherwise score a model that answers nothing as
mostly right.
"""

from __future__ import annotations

import datetime as dt
import json
import math
import re
import unicodedata
from collections.abc import Iterator, Mapping, Sequence
from enum import StrEnum
from typing import Any, Final

import numpy as np
from pydantic import BaseModel, ConfigDict
from scipy.optimize import linear_sum_assignment

from legible.schema import CorpusSchema, FieldKind, FieldSpec, GroupSpec, Item, Record, SchemaDrift
from legible.stats import Interval, UnpairedItems, mean_ci, paired_ratio_delta_ci, ratio_ci


class Outcome(StrEnum):
    """What happened to one scored field. The misses are ordered most diagnostic first."""

    CORRECT = "correct"
    #: The output was not JSON, or the field did not hold a value of its declared type.
    MALFORMED = "malformed"
    #: The page carries the field and the prediction is blank.
    MISSING = "missing"
    #: The value predicted is the truth of a different field on the same page: the agency
    #: read into the advertiser box, the subtotal into the total.
    WRONG_FIELD = "wrong_field"
    #: The field is blank on the page and the prediction filled it with a value that appears
    #: nowhere in the page's text. Invented outright.
    INVENTED = "invented"
    #: The field is blank on the page and the prediction filled it with something that is
    #: on the page. A hallucination of the box, not of the text.
    BLANK_FILLED = "blank_filled"
    #: Wrong, and not in any of the ways above: a misread digit, a truncated name.
    WRONG_VALUE = "wrong_value"


#: The two outcomes reported as the hallucination rate.
HALLUCINATIONS: Final = frozenset({Outcome.INVENTED, Outcome.BLANK_FILLED})


class FieldOutcome(BaseModel):
    """One scored field. `index` is the truth item for group fields, or the prediction
    item when the prediction carried an item the truth does not."""

    model_config = ConfigDict(frozen=True)

    path: str
    index: int | None
    outcome: Outcome
    truth: str | None
    predicted: str | None
    confidence: float | None = None

    @property
    def correct(self) -> bool:
        return self.outcome is Outcome.CORRECT


class DocGrade(BaseModel):
    """Every scored field of one document, and what the output did outside the schema."""

    model_config = ConfigDict(frozen=True)

    doc_id: str
    outcomes: tuple[FieldOutcome, ...]
    #: Fields blank in both truth and prediction: correct abstentions, not scored.
    abstained: int
    #: The whole output failed to parse as a JSON object.
    unparsed: bool
    #: Keys the output carried that the schema does not name. Not scored and not credited;
    #: counted because a model that adds fields is ignoring the instruction.
    extra_keys: tuple[str, ...]

    @property
    def scored(self) -> int:
        return len(self.outcomes)

    @property
    def correct(self) -> int:
        return sum(o.correct for o in self.outcomes)

    @property
    def all_right(self) -> bool:
        """What a clerk experiences: a form that needs no correction."""
        return not self.unparsed and all(o.correct for o in self.outcomes)

    @property
    def hallucinated(self) -> int:
        return sum(o.outcome in HALLUCINATIONS for o in self.outcomes)


# --- Normalisation and matchers -------------------------------------------------------------
#
# The matchers are VRDU's own (match_utils.py in google-research/vrdu, Apache-2.0, read
# 2026-10-16), reimplemented here so that a VRDU number means what the benchmark means, and
# extended where CORD and NIST need it. The extensions widen what parses; none changes a
# VRDU verdict on a pair of values VRDU itself parses:
#
# - STRING is GeneralStringMatch: everything but ASCII letters and digits deleted, then an
#   exact, case-sensitive comparison.
# - NAME is NameMatch: whitespace deleted, then exact. Case and punctuation count.
# - CODE is NumericalStringMatch: everything but digits deleted, then exact.
# - ADDRESS is AddressMatch: an edit distance of at most 3.
# - PRICE is PriceMatch, within 0.01. Extended: currency words, thousands separators by the
#   field's decimal mark (CORD prints whole rupiah as 45.000), parentheses as negative.
# - DATE is DateMatch: the same date, or the same year with day and month swapped; when
#   either side does not parse, the STRING comparison. Extended: more printed formats.
# - NUMBER is not in VRDU: a count, parsed like a price and compared exactly.
#
# Typographic quotes and dashes are folded to their plain forms first, named by code point
# so the source stays ASCII.

_FOLD: Final = str.maketrans(
    {
        0x2018: "'",
        0x2019: "'",
        0x201C: '"',
        0x201D: '"',
        0x2010: "-",
        0x2011: "-",
        0x2012: "-",
        0x2013: "-",
        0x2014: "-",
        0x00A0: " ",
    }
)
_SPACE = re.compile(r"\s+")
_NOT_ASCII_ALNUM = re.compile(r"[^0-9a-zA-Z]")
_NOT_DIGIT = re.compile(r"[^0-9]")
_NON_ALNUM = re.compile(r"[\W_]+")
ADDRESS_EDITS: Final = 3
PRICE_TOLERANCE: Final = 0.01


def _clean(value: str) -> str:
    """NFKC, plain quotes and dashes, stripped, one space between words: what every VRDU
    matcher does before anything else."""
    return _SPACE.sub(" ", unicodedata.normalize("NFKC", value).translate(_FOLD)).strip()


def normalise_string(value: str) -> str:
    """GeneralStringMatch's form: ASCII letters and digits only, case kept."""
    return _NOT_ASCII_ALNUM.sub("", _clean(value))


def _squash(value: str) -> str:
    """Letters and digits only, case folded, for the on-the-page and wrong-field checks."""
    return _NON_ALNUM.sub("", unicodedata.normalize("NFKC", value).casefold())


def edit_distance(a: str, b: str) -> int:
    """Levenshtein distance, for addresses."""
    if len(a) < len(b):
        a, b = b, a
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        current = [i]
        for j, cb in enumerate(b, 1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (ca != cb)))
        previous = current
    return previous[-1]


_CURRENCY = re.compile(r"(?i)\b(?:rp|idr|usd|us|cad|ca)\b|[$\u20ac\u00a3\u00a5]")


_NUMERIC_CORE = re.compile(r"(-?)(\d[\d.,]*\d|\d)")


def _parse_auto(value: str) -> float | None:
    """A receipt's number, as printed among other marks: `Rp.99.999`, `@12,000`, `2x`,
    `(Qty=2.00)`. The first run of digits and separators is the number. A last separator
    followed by one or two digits is the decimal mark; every other separator groups
    thousands, so 60.000 and 60,000 are sixty thousand and 2.00 is two."""
    m = _NUMERIC_CORE.search(_clean(value))
    if m is None:
        return None
    sign, core = m.groups()
    tail = re.search(r"[.,](\d{1,2})$", core)
    if tail:
        whole = re.sub(r"[.,]", "", core[: tail.start()])
        number = float(f"{whole or 0}.{tail.group(1)}")
    else:
        number = float(re.sub(r"[.,]", "", core))
    return -number if sign else number


def parse_number(value: str, decimal_mark: str | None) -> float | None:
    """A printed amount as a number, or None when it is not one.

    `decimal_mark` None means amounts are whole units and every '.' or ',' separates
    thousands; "auto" reads a receipt's mixed conventions (see _parse_auto).
    Parentheses and a trailing minus are negative, as accounts print them.
    """
    if decimal_mark == "auto":
        return _parse_auto(value)
    s = _CURRENCY.sub("", _clean(value)).strip()
    negative = False
    if s.startswith("(") and s.endswith(")"):
        negative, s = True, s[1:-1]
    s = s.replace(" ", "")
    if s.endswith("-"):
        negative, s = True, s[:-1]
    if s.startswith("-"):
        negative, s = not negative, s[1:]
    if decimal_mark is None:
        s = s.replace(".", "").replace(",", "")
    elif decimal_mark == ".":
        s = s.replace(",", "")
    else:
        s = s.replace(".", "").replace(",", ".")
    if not re.fullmatch(r"\d+(?:\.\d+)?|\.\d+", s):
        return None
    number = float(s)
    return -number if negative else number


_ORDINAL = re.compile(r"(?<=\d)(st|nd|rd|th)\b", re.IGNORECASE)
_NAMED_FORMATS: Final = (
    "%B %d %Y",
    "%b %d %Y",
    "%d %B %Y",
    "%d %b %Y",
    "%B %d %y",
    "%b %d %y",
    "%d %b %y",
    "%Y %B %d",
    "%A %B %d %Y",
    "%a %b %d %Y",
)
_NUMERIC_DATE = re.compile(r"^(\d{1,4})[/.\-](\d{1,2})[/.\-](\d{1,4})$")
_MONTH_DAY = re.compile(r"^(\d{1,2})/(\d{1,2})$")


def parse_date(value: str, *, day_first: bool) -> dt.date | None:
    """A printed date as a date, or None. Numeric dates are read year first when the first
    part has four digits, otherwise month first unless the field says day first. A bare
    month and day is year 1900, as VRDU reads it."""
    s = _SPACE.sub("", _clean(value))
    m = _NUMERIC_DATE.match(s)
    if m:
        a, b, c = m.groups()
        if len(a) == 4:
            y, mo, d = int(a), int(b), int(c)
        else:
            mo, d = (int(b), int(a)) if day_first else (int(a), int(b))
            y = int(c)
            if len(c) == 2:
                y += 2000 if y < 69 else 1900
            elif len(c) != 4:
                return None
        try:
            return dt.date(y, mo, d)
        except ValueError:
            return None
    m = _MONTH_DAY.match(s)
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        mo, d = (b, a) if day_first else (a, b)
        try:
            return dt.date(1900, mo, d)
        except ValueError:
            return None
    # A named month: commas, periods and ordinal suffixes are decoration.
    s = _clean(value).replace(",", " ").replace(".", " ")
    s = _SPACE.sub(" ", _ORDINAL.sub("", s)).strip()
    for fmt in _NAMED_FORMATS:
        try:
            return dt.datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def values_match(spec: FieldSpec, predicted: str, truth: str) -> bool:
    """Whether a prediction matches the truth under the field's matcher."""
    match spec.kind:
        case FieldKind.STRING:
            return normalise_string(predicted) == normalise_string(truth)
        case FieldKind.NAME:
            return _SPACE.sub("", _clean(predicted)) == _SPACE.sub("", _clean(truth))
        case FieldKind.CODE:
            return _NOT_DIGIT.sub("", _clean(predicted)) == _NOT_DIGIT.sub("", _clean(truth))
        case FieldKind.ADDRESS:
            return edit_distance(_clean(predicted), _clean(truth)) <= ADDRESS_EDITS
        case FieldKind.DATE:
            p = parse_date(predicted, day_first=spec.day_first)
            t = parse_date(truth, day_first=spec.day_first)
            if p is None or t is None:
                return normalise_string(predicted) == normalise_string(truth)
            return p == t or (p.year == t.year and (p.month, p.day) == (t.day, t.month))
        case FieldKind.PRICE | FieldKind.NUMBER:
            pn = parse_number(predicted, spec.decimal_mark)
            tn = parse_number(truth, spec.decimal_mark)
            if pn is None or tn is None:
                return False
            if spec.kind is FieldKind.PRICE:
                # A hair over the tolerance, so that a cent off in binary floating point is
                # still within a cent, as VRDU's comparison intends.
                return abs(pn - tn) <= PRICE_TOLERANCE + 1e-9
            return math.isclose(pn, tn, rel_tol=0.0, abs_tol=1e-9)


def _holds_type(spec: FieldSpec, value: str) -> bool:
    """Whether a value is of its field's type at all: only dates and numbers can fail."""
    if spec.kind is FieldKind.DATE:
        return parse_date(value, day_first=spec.day_first) is not None
    if spec.kind in {FieldKind.PRICE, FieldKind.NUMBER}:
        return parse_number(value, spec.decimal_mark) is not None
    return True


# --- Parsing an arm's output ----------------------------------------------------------------

_FENCE = re.compile(r"^```[a-zA-Z]*\s*|\s*```$")


def parse_output(text: str) -> dict[str, Any] | None:
    """The JSON object an arm returned, or None. Tolerates a code fence and prose around the
    object, because some vendors add them even when asked not to; anything else is None."""
    s = _FENCE.sub("", text.strip())
    start, end = s.find("{"), s.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        obj = json.loads(s[start : end + 1])
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) else None


def _as_text(value: object) -> tuple[str | None, bool]:
    """(text, ok). Numbers are accepted as their printed form; a list or object where a
    scalar belongs is not ok."""
    if value is None:
        return None, True
    if isinstance(value, bool):
        return None, False
    if isinstance(value, str):
        return (value if value.strip() else None), True
    if isinstance(value, int | float):
        return format(value, "g") if isinstance(value, float) else str(value), True
    return None, False


# --- Grading one document -------------------------------------------------------------------


def _blank(value: object) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


class _Context:
    """What a single field's classification needs from the rest of the page."""

    def __init__(self, schema: CorpusSchema, truth: Record, page_text: str | None) -> None:
        self.page = _squash(page_text) if page_text is not None else None
        self.truth_values: list[tuple[str, str]] = []
        for f in schema.fields:
            v = truth.get(f.name)
            if isinstance(f, FieldSpec):
                if isinstance(v, str) and v.strip():
                    self.truth_values.append((f.name, v))
            elif isinstance(v, list):
                for i, item in enumerate(v):
                    for g in f.fields:
                        sv = item.get(g.name)
                        if isinstance(sv, str) and sv.strip():
                            self.truth_values.append((f"{f.name}[{i}].{g.name}", sv))

    def on_page(self, value: str) -> bool:
        """Whether a value's letters and digits appear in the page text. Without page text
        nothing can be called invented, so every value counts as on the page."""
        if self.page is None:
            return True
        squashed = _squash(value)
        return not squashed or squashed in self.page

    def other_field(self, value: str, own: str) -> bool:
        squashed = _squash(value)
        return bool(squashed) and any(
            key != own and _squash(v) == squashed for key, v in self.truth_values
        )


def _classify(
    spec: FieldSpec,
    predicted: str | None,
    truth: str | None,
    ok: bool,
    own_key: str,
    ctx: _Context,
    alternatives: Sequence[str] = (),
) -> Outcome | None:
    """None for a correct abstention, otherwise the outcome. `alternatives` are further
    truth candidates: VRDU records each place a value is printed, and matching any counts."""
    if not ok:
        return Outcome.MALFORMED
    if truth is None and predicted is None:
        return None
    if predicted is None:
        return Outcome.MISSING
    if truth is not None and any(values_match(spec, predicted, c) for c in (truth, *alternatives)):
        return Outcome.CORRECT
    if truth is not None and not _holds_type(spec, predicted) and _holds_type(spec, truth):
        return Outcome.MALFORMED
    if ctx.other_field(predicted, own_key):
        return Outcome.WRONG_FIELD
    if truth is None:
        # Only a blank box can be invented: a wrong value where the page carries one is a
        # misread, however far off, and a misread is by definition not on the page.
        return Outcome.BLANK_FILLED if ctx.on_page(predicted) else Outcome.INVENTED
    return Outcome.WRONG_VALUE


def _item_texts(group: GroupSpec, item: object) -> tuple[dict[str, str | None], set[str]]:
    """A predicted item's fields as text, and the names that were not scalars."""
    texts: dict[str, str | None] = {}
    bad: set[str] = set()
    raw = item if isinstance(item, Mapping) else {}
    for g in group.fields:
        text, ok = _as_text(raw.get(g.name))
        texts[g.name] = text
        if not ok:
            bad.add(g.name)
    return texts, bad


def _align(
    group: GroupSpec, truth: Sequence[Item], pred: Sequence[dict[str, str | None]]
) -> list[tuple[int, int]]:
    """Pair truth items with predicted items to maximise matching fields.

    Order on the page is not order in the answer: a model that lists the line items bottom
    to top has read them all, and should be scored as if it had.
    """
    if not truth or not pred:
        return []
    score = np.zeros((len(truth), len(pred)))
    for i, t in enumerate(truth):
        for j, p in enumerate(pred):
            for g in group.fields:
                tv, pv = t.get(g.name), p.get(g.name)
                if isinstance(tv, str) and pv is not None and values_match(g, pv, tv):
                    score[i, j] += 1
    rows, cols = linear_sum_assignment(score, maximize=True)
    return [(int(r), int(c)) for r, c in zip(rows, cols, strict=True)]


def grade_document(
    schema: CorpusSchema,
    doc_id: str,
    truth: Record,
    output: str | Mapping[str, Any] | None,
    *,
    page_text: str | None = None,
    confidences: Mapping[str, float] | None = None,
    alternatives: Mapping[str, Sequence[str]] | None = None,
) -> DocGrade:
    """Grade one document's output against its truth.

    `output` is the arm's raw text, an already parsed object, or None when the call failed.
    `page_text` is the page's own text from the corpus annotation, used only to tell a
    blank box filled from the page from one filled with a value the page does not carry.
    `confidences` are keyed by field path, with group fields as `group[j].field` where j is
    the item's position in the prediction. `alternatives` are further truth candidates for
    scalar fields, by name.
    """
    alts = alternatives or {}
    unknown_alts = set(alts) - {f.name for f in schema.scalars}
    if unknown_alts:
        raise SchemaDrift(
            f"alternatives for {doc_id} name non-scalar fields {sorted(unknown_alts)}"
        )
    schema.check_record(truth, what=f"truth for {doc_id}")
    parsed = (
        parse_output(output)
        if isinstance(output, str)
        else (dict(output) if output is not None else None)
    )
    ctx = _Context(schema, truth, page_text)
    conf = confidences or {}
    outcomes: list[FieldOutcome] = []
    abstained = 0

    def record(
        path: str,
        index: int | None,
        outcome: Outcome | None,
        t: str | None,
        p: str | None,
        key: str,
    ) -> None:
        nonlocal abstained
        if outcome is None:
            abstained += 1
        else:
            outcomes.append(
                FieldOutcome(
                    path=path,
                    index=index,
                    outcome=outcome,
                    truth=t,
                    predicted=p,
                    confidence=conf.get(key),
                )
            )

    if parsed is None:
        for path, index, value in _truth_fields(schema, truth):
            record(path, index, Outcome.MALFORMED, value, None, path)
        return DocGrade(
            doc_id=doc_id, outcomes=tuple(outcomes), abstained=0, unparsed=True, extra_keys=()
        )

    extra = tuple(sorted(k for k in parsed if k not in {f.name for f in schema.fields}))

    for f in schema.fields:
        if isinstance(f, FieldSpec):
            tv = truth.get(f.name)
            t = tv if isinstance(tv, str) and tv.strip() else None
            p, ok = _as_text(parsed.get(f.name))
            outcome = _classify(f, p, t, ok, f.name, ctx, alts.get(f.name, ()))
            record(f.name, None, outcome, t, p, f.name)
            continue

        raw_truth = truth.get(f.name)
        truth_items: list[Item] = raw_truth if isinstance(raw_truth, list) else []
        raw_pred = parsed.get(f.name)
        if raw_pred is not None and not isinstance(raw_pred, list):
            for i, item in enumerate(truth_items):
                for g in f.fields:
                    tv = item.get(g.name)
                    if not _blank(tv):
                        record(
                            f"{f.name}.{g.name}",
                            i,
                            Outcome.MALFORMED,
                            tv,
                            None,
                            f"{f.name}.{g.name}",
                        )
            continue
        pred_items = [_item_texts(f, item) for item in (raw_pred or [])]
        pairs = _align(f, truth_items, [texts for texts, _ in pred_items])
        paired_truth = {i for i, _ in pairs}
        paired_pred = {j for _, j in pairs}
        for i, j in pairs:
            texts, bad = pred_items[j]
            for g in f.fields:
                tv = truth_items[i].get(g.name)
                t = tv if isinstance(tv, str) and tv.strip() else None
                own = f"{f.name}[{i}].{g.name}"
                outcome = _classify(g, texts[g.name], t, g.name not in bad, own, ctx)
                record(
                    f"{f.name}.{g.name}", i, outcome, t, texts[g.name], f"{f.name}[{j}].{g.name}"
                )
        for i, item in enumerate(truth_items):
            if i in paired_truth:
                continue
            for g in f.fields:
                tv = item.get(g.name)
                if isinstance(tv, str) and tv.strip():
                    record(f"{f.name}.{g.name}", i, Outcome.MISSING, tv, None, "")
        for j, (texts, bad) in enumerate(pred_items):
            if j in paired_pred:
                continue
            for g in f.fields:
                p = texts[g.name]
                if p is None and g.name not in bad:
                    continue
                outcome = _classify(g, p, None, g.name not in bad, f"{f.name}[+{j}].{g.name}", ctx)
                record(f"{f.name}.{g.name}", j, outcome, None, p, f"{f.name}[{j}].{g.name}")

    return DocGrade(
        doc_id=doc_id,
        outcomes=tuple(outcomes),
        abstained=abstained,
        unparsed=False,
        extra_keys=extra,
    )


def _truth_fields(schema: CorpusSchema, truth: Record) -> Iterator[tuple[str, int | None, str]]:
    """Every non-blank truth field, for an output that did not parse at all."""
    for f in schema.fields:
        v = truth.get(f.name)
        if isinstance(f, FieldSpec):
            if isinstance(v, str) and v.strip():
                yield f.name, None, v
        elif isinstance(v, list):
            for i, item in enumerate(v):
                for g in f.fields:
                    sv = item.get(g.name)
                    if isinstance(sv, str) and sv.strip():
                        yield f"{f.name}.{g.name}", i, sv


# --- Summaries ------------------------------------------------------------------------------


class Summary(BaseModel):
    """One arm on one set of documents: the numbers section 1 of the plan reports."""

    model_config = ConfigDict(frozen=True)

    documents: int
    fields_scored: int
    accuracy: Interval
    all_right: Interval
    hallucination: Interval
    unparsed: Interval
    misses: dict[str, int]


def summarise(grades: Sequence[DocGrade], *, seed: int = 0) -> Summary:
    """Accuracy, every-field-right, hallucination and unparsed rates, each with its
    interval over documents, and the count of every miss by kind."""
    misses = {o.value: 0 for o in Outcome if o is not Outcome.CORRECT}
    for g in grades:
        for o in g.outcomes:
            if o.outcome is not Outcome.CORRECT:
                misses[o.outcome.value] += 1
    scored = [float(g.scored) for g in grades]
    return Summary(
        documents=len(grades),
        fields_scored=int(sum(scored)),
        accuracy=ratio_ci([float(g.correct) for g in grades], scored, seed=seed),
        all_right=mean_ci([float(g.all_right) for g in grades], seed=seed),
        hallucination=ratio_ci([float(g.hallucinated) for g in grades], scored, seed=seed),
        unparsed=mean_ci([float(g.unparsed) for g in grades], seed=seed),
        misses=misses,
    )


def accuracy_delta(a: Sequence[DocGrade], b: Sequence[DocGrade], *, seed: int = 0) -> Interval:
    """Paired field-accuracy difference `a - b`. Raises UnpairedItems unless both arms
    graded the same documents."""
    for run in (a, b):
        ids = [g.doc_id for g in run]
        if len(ids) != len(set(ids)):
            raise UnpairedItems("a run graded the same document twice; pairing would drop one")
    return paired_ratio_delta_ci(
        {g.doc_id: (float(g.correct), float(g.scored)) for g in a},
        {g.doc_id: (float(g.correct), float(g.scored)) for g in b},
        seed=seed,
    )
