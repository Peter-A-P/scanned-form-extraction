"""Running arm E over a split: stored OCR in, one answer per document out.

Each split file is its own run, because on FARA's unseen-template files the rule sets
available differ by file: the rules for the held-out template are not loaded. An answer is the
rules' record, or null when no rule set recognised the document. The OCR seconds of the
document's pages are kept beside it, because OCR is all arm E costs.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from legible.arms.ocr_run import load, stored
from legible.arms.rule_sets import CORD, DEEPFORM, fara_rules
from legible.arms.rules import TemplateRules, detect, lines_of, read
from legible.data.render import PageEntry
from legible.data.vrdu import VrduSplit, fara_template
from legible.schema import Record
from legible.schema.corpora import SCHEMAS


class RulesRead(BaseModel):
    model_config = ConfigDict(frozen=True)

    doc_id: str
    output: Record | None
    ocr_seconds: float
    rule_set: str | None


def answer(read: RulesRead) -> Record:
    """What arm E answered, for grading. A document no rule set recognised answers nothing:
    every field it should have read is missing, not malformed, because nothing unreadable was
    returned. Field accuracy is the same either way; the miss taxonomy is not."""
    return read.output if read.output is not None else {}


def rule_sets_for(corpus: str, split: VrduSplit | None) -> tuple[TemplateRules, ...]:
    if corpus == "fara":
        if split is None:
            raise ValueError("FARA's rules depend on the split's training templates")
        return fara_rules({fara_template(d) for d in split.train})
    return (DEEPFORM,) if corpus == "deepform" else (CORD,)


def run(
    root: Path,
    corpus: str,
    doc_ids: Sequence[str],
    pages: dict[str, list[PageEntry]],
    rule_sets: Sequence[TemplateRules],
    level: int,
    out: Path,
) -> int:
    """Answer every document; refuses to start if any page's OCR is missing."""
    missing = [
        e.path for d in doc_ids for e in pages[d] if not stored(root, level, e.path).exists()
    ]
    if missing:
        raise FileNotFoundError(
            f"{len(missing)} pages have no OCR at level {level}, first {missing[:3]}"
        )
    schema = SCHEMAS[corpus]
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="\n") as f:
        for d in doc_ids:
            ocr = [load(root, level, e.path) for e in sorted(pages[d], key=lambda e: e.page)]
            record = read(schema, ocr, rule_sets)
            found = detect(lines_of(ocr), rule_sets) if record is not None else None
            recognised = found.name if found else None
            row = RulesRead(
                doc_id=d,
                output=record,
                ocr_seconds=sum(p.seconds for p in ocr),
                rule_set=recognised,
            )
            f.write(row.model_dump_json() + "\n")
    return len(doc_ids)


def read_run(path: Path) -> list[RulesRead]:
    with path.open(encoding="utf-8") as f:
        return [RulesRead.model_validate(json.loads(line)) for line in f if line.strip()]


def run_nist(
    root: Path,
    doc_ids: Sequence[str],
    pages: dict[str, list[PageEntry]],
    level: int,
    out: Path,
) -> int:
    """Arm E on NIST faces: each page read with the committed zones (`legible.arms.zonal`).
    `rule_set` names the face the page was read as, which may not be its true face."""
    from legible.arms.zonal import load_rules
    from legible.arms.zonal import read as read_zones

    rules = load_rules()
    missing = [
        e.path for d in doc_ids for e in pages[d] if not stored(root, level, e.path).exists()
    ]
    if missing:
        raise FileNotFoundError(
            f"{len(missing)} pages have no OCR at level {level}, first {missing[:3]}"
        )
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="\n") as f:
        for d in doc_ids:
            (entry,) = pages[d]
            page = load(root, level, entry.path)
            face, record = read_zones(page, rules)
            row = RulesRead(
                doc_id=d, output=record if face else None, ocr_seconds=page.seconds, rule_set=face
            )
            f.write(row.model_dump_json() + "\n")
    return len(doc_ids)
