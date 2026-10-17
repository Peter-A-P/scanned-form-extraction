"""Arm E: OCR plus rules. Tesseract's words, label anchors and patterns, nothing learned.

This is the pipeline most organisations built first and many still run: find the printed
label ("2. Registration No."), take the value beside it or under it, check it looks like what
the field holds. Its rules are written by hand for the templates in the training split, by
reading training pages, and for no other. On a template it was written for it should do well
and cost nothing; on one it was not written for it has no rule to apply. Measuring that drop is
why the arm is here (PLAN.md section 10, candidate 3).

How a field is found:

- A template is recognised by phrases on its first page. A document no rule set recognises
  gets no answer at all, which is what a rules engine does with a form it has never seen.
- Each field is a list of `Extract`s tried in order; the first that yields a value wins.
- An `Extract` finds the first line matching its anchor and takes either the words to the right
  of the anchor on that line, or the words on the next lines below it, within the anchor's
  column (up to the left edge of a header word named by `column_end`, if given).
- The taken text is kept only if the field's `value` pattern finds something in it.
- Rows (line items, receipt items) are lines matching a row pattern with named groups, between
  optional start and end anchors.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Literal

from pydantic import BaseModel, ConfigDict

from legible.arms.ocr import OcrPage, Word
from legible.schema import CorpusSchema, FieldSpec, Item, Record


class Line(BaseModel):
    model_config = ConfigDict(frozen=True)

    page: int
    words: tuple[Word, ...]
    page_height: int

    @property
    def text(self) -> str:
        return " ".join(w.text for w in self.words)

    @property
    def left(self) -> int:
        return min(w.left for w in self.words)

    @property
    def top(self) -> int:
        return min(w.top for w in self.words)

    @property
    def bottom(self) -> int:
        return max(w.top + w.height for w in self.words)


def lines_of(pages: Sequence[OcrPage]) -> list[Line]:
    """Every OCR line of a document, page by page, top to bottom."""
    out: list[Line] = []
    for i, page in enumerate(pages):
        grouped: dict[tuple[int, int, int], list[Word]] = {}
        for w in page.words:
            grouped.setdefault((w.block, w.par, w.line), []).append(w)
        ordered = sorted(
            grouped.values(), key=lambda ws: (min(w.top for w in ws), min(w.left for w in ws))
        )
        out.extend(
            Line(page=i, words=tuple(sorted(ws, key=lambda w: w.left)), page_height=page.height)
            for ws in ordered
        )
    return out


class Extract(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    anchor: str
    #: "match": the anchor's own match is the value (a date anywhere on a page).
    where: Literal["right", "below", "match"] = "right"
    #: Below only: how many lines under the anchor to read, and how far down, as a share of
    #: the page height, the first may start.
    lines: int = 1
    max_gap: float = 0.05
    #: A header on the anchor's line whose left edge ends this field's column.
    column_end: str | None = None
    #: Right only: a label later on the line that ends this value.
    stop: str | None = None
    #: The value must contain a match; group 1 if the pattern has one, else the match.
    value: str = r"\S.*\S|\S"
    #: Below only: lines to pass over (a column header), and a label at which each line's
    #: text is cut (the next field printed on the same line).
    skip: str | None = None
    cut: str | None = None
    page: int | None = None


class RowRule(BaseModel):
    """Repeated rows: every line between `start` and `end` matching `pattern` and not
    `exclude`, whose named groups are the group's field names. A row printed over two lines
    takes the groups of a `continuation` found on one of the next two lines."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    group: str
    pattern: str
    start: str | None = None
    end: str | None = None
    exclude: str | None = None
    continuation: str | None = None


class TemplateRules(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    #: Phrases, any of which on the first page identifies the template.
    detect: tuple[str, ...]
    fields: dict[str, tuple[Extract, ...]]
    rows: tuple[RowRule, ...] = ()


def _words_after(line: Line, match_end: int) -> list[Word]:
    """The words whose text starts at or after a character offset of the line's text."""
    out, offset = [], 0
    for w in line.words:
        if offset >= match_end:
            out.append(w)
        offset += len(w.text) + 1
    return out


def _value(text: str, pattern: str) -> str | None:
    m = re.search(pattern, text, re.IGNORECASE)
    if m is None:
        return None
    found = (m.group(1) if m.groups() else m.group(0)).strip(" :;,|")
    return found or None


def apply_extract(lines: Sequence[Line], ex: Extract) -> str | None:
    for i, line in enumerate(lines):
        if ex.page is not None and line.page != ex.page:
            continue
        m = re.search(ex.anchor, line.text, re.IGNORECASE)
        if m is None:
            continue
        if ex.where == "match":
            found = (m.group(1) if m.groups() else m.group(0)).strip()
            if found:
                return found
            continue
        if ex.where == "right":
            words = _words_after(line, m.end())
            text = " ".join(w.text for w in words)
            if ex.stop:
                text = re.split(ex.stop, text, maxsplit=1, flags=re.IGNORECASE)[0]
            found = _value(text, ex.value)
            if found:
                return found
            continue
        anchor_words = _words_after(line, m.start())
        x0 = (anchor_words[0].left if anchor_words else line.left) - 60
        x1 = 10**9
        if ex.column_end:
            for w in _words_after(line, m.end()):
                if re.search(ex.column_end, w.text, re.IGNORECASE):
                    x1 = w.left - 10
                    break
        taken: list[str] = []
        # The gap is measured from the last line passed, so a line of another column between
        # the anchor and its value (a registration number printed on its own) does not count
        # as distance.
        previous = line.bottom
        for below in lines[i + 1 :]:
            if below.page != line.page:
                break
            if not taken and below.top - previous > ex.max_gap * line.page_height:
                break
            previous = below.bottom
            words = [w for w in below.words if x0 <= w.left < x1]
            text = " ".join(w.text for w in words)
            if ex.cut:
                text = re.split(ex.cut, text, maxsplit=1, flags=re.IGNORECASE)[0].strip()
            if text and ex.skip and re.search(ex.skip, text, re.IGNORECASE):
                continue
            if text:
                taken.append(text)
            if len(taken) == ex.lines:
                break
        found = _value(" ".join(taken), ex.value)
        if found:
            return found
    return None


#: How much of the first page is the form's title block. Body text quotes other forms'
#: names ("every registration statement, short form registration statement, ..."), so the
#: template is read from the top only.
HEADER_LINES = 12


def detect(lines: Sequence[Line], rule_sets: Sequence[TemplateRules]) -> TemplateRules | None:
    first = " ".join(line.text for line in [x for x in lines if x.page == 0][:HEADER_LINES])
    for rules in rule_sets:
        if any(re.search(p, first, re.IGNORECASE) for p in rules.detect):
            return rules
    return None


def apply_rows(lines: Sequence[Line], rule: RowRule) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    inside = rule.start is None
    for i, line in enumerate(lines):
        text = line.text
        if not inside:
            inside = re.search(rule.start or "", text, re.IGNORECASE) is not None
            continue
        if rule.end and re.search(rule.end, text, re.IGNORECASE):
            if rule.start is None:
                break
            inside = False
            continue
        if rule.exclude and re.search(rule.exclude, text, re.IGNORECASE):
            continue
        m = re.search(rule.pattern, text, re.IGNORECASE)
        if not m:
            continue
        row = {k: v.strip() for k, v in m.groupdict().items() if v and v.strip()}
        if rule.continuation:
            for nxt in lines[i + 1 : i + 3]:
                c = re.search(rule.continuation, nxt.text, re.IGNORECASE)
                if c:
                    row.update({k: v.strip() for k, v in c.groupdict().items() if v and v.strip()})
                    break
        rows.append(row)
    return rows


def read(
    schema: CorpusSchema, pages: Sequence[OcrPage], rule_sets: Sequence[TemplateRules]
) -> Record | None:
    """Arm E's answer for one document, or None when no rule set recognises it."""
    lines = lines_of(pages)
    rules = detect(lines, rule_sets)
    if rules is None:
        return None
    out: Record = {}
    for f in schema.fields:
        if isinstance(f, FieldSpec):
            value = None
            for ex in rules.fields.get(f.name, ()):
                value = apply_extract(lines, ex)
                if value:
                    break
            out[f.name] = value
        else:
            items: list[Item] = []
            for rule in rules.rows:
                if rule.group == f.name:
                    for row in apply_rows(lines, rule):
                        items.append({g.name: row.get(g.name) for g in f.fields})
            out[f.name] = items
    schema.check_record(out, what=f"arm E output ({rules.name})")
    return out
