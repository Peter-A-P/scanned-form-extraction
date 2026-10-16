"""The fine-tuning set: one row per training document, its page images, the instruction and
the JSON target, all from one schema.

The instruction is the same prompt the other arms are sent (legible.prompt), so the fine-tune
is measured on the question it was trained on and nothing else; the target is the schema's
canonical JSON of the truth (CorpusSchema.target). The set's header records the schema
fingerprint, the prompt version and the split file it was drawn from, and loading a set
whose schema has changed since is refused, so a model is never trained on a definition the
grader no longer uses.

Only train documents are written. A document id from the split's valid or test part in a
training set is a leak, and `write_training_set` refuses one.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator, Sequence
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from legible.data.split import SplitLeak
from legible.prompt import build_prompt
from legible.schema import CorpusSchema, Record, all_names


class TrainingRow(BaseModel):
    model_config = ConfigDict(frozen=True)

    doc_id: str
    #: Page images relative to the data root's pages directory, in page order.
    pages: tuple[str, ...]
    target: str


class TrainingHeader(BaseModel):
    model_config = ConfigDict(frozen=True)

    corpus: str
    schema_fingerprint: str
    fields: tuple[str, ...]
    prompt_version: int
    instruction: str
    split_file: str
    rows: int


def write_training_set(
    path: Path,
    schema: CorpusSchema,
    split_file: str,
    docs: Iterable[tuple[str, Record, Sequence[str]]],
    *,
    held_out: set[str],
) -> int:
    """Write (doc_id, truth, page paths) rows. Refuses any document in `held_out`."""
    prompt = build_prompt(schema)
    rows = []
    for doc_id, truth, pages in docs:
        if doc_id in held_out:
            raise SplitLeak(f"{doc_id} is held out of {split_file} and cannot be trained on")
        rows.append(TrainingRow(doc_id=doc_id, pages=tuple(pages), target=schema.target(truth)))
    header = TrainingHeader(
        corpus=schema.corpus,
        schema_fingerprint=schema.fingerprint(),
        fields=tuple(all_names(schema.fields)),
        prompt_version=prompt.version,
        instruction=prompt.text,
        split_file=split_file,
        rows=len(rows),
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        f.write(header.model_dump_json() + "\n")
        for row in rows:
            f.write(row.model_dump_json() + "\n")
    return len(rows)


def read_training_set(
    path: Path, schema: CorpusSchema
) -> tuple[TrainingHeader, Iterator[TrainingRow]]:
    """A stored set, refused if the schema it was built from is not the current one."""
    with path.open(encoding="utf-8") as f:
        header = TrainingHeader.model_validate_json(f.readline())
    schema.require_aligned(
        header.fields, header.schema_fingerprint, what=f"training set {path.name}"
    )

    def rows() -> Iterator[TrainingRow]:
        with path.open(encoding="utf-8") as f:
            next(f)
            for line in f:
                row = TrainingRow.model_validate_json(line)
                schema.check_record(json.loads(row.target), what=f"target for {row.doc_id}")
                yield row

    return header, rows()
