"""The instruction every reading arm is given, built from the corpus schema.

One template for every arm and vendor: the vision arms get it with the page images, the
OCR-text arm with the positioned text, the small models with the images at training and at
inference. What differs between arms is the input, never the question. A prompt is stored
with the schema fingerprint and the field names it was built from, and a stored prompt whose
schema has since changed is refused (SchemaDrift) rather than sent.

Prompt versions are iterated on dev only; the version used for each test run is recorded in
the run, so a test number names the exact words that produced it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from legible.schema import CorpusSchema, FieldSpec, all_names

PROMPT_VERSION = 1

Source = Literal["images", "ocr_text"]
_SOURCE: dict[Source, str] = {
    "images": "the page images",
    "ocr_text": (
        "the OCR text of the pages below, in which each line of the page is one line of text "
        "and each word sits at the column of its position across the page"
    ),
}

_TEMPLATE = """You are reading {what}

Extract the fields below from {source} and answer with one JSON object and nothing
else: no explanation and no code fence.

Rules:
- Copy each value exactly as it is printed: keep its spelling, punctuation, currency marks,
  separators and date format. Do not reformat, translate or compute anything.
- Use null for a field the document does not show. Never guess a value that is not printed.
- {groups_rule}
- Use only the keys listed. Every key must be present.

Fields:
{fields}

The answer must satisfy this JSON Schema:
{schema}"""


class Prompt(BaseModel):
    model_config = ConfigDict(frozen=True)

    corpus: str
    version: int
    source: Source
    schema_fingerprint: str
    fields: tuple[str, ...]
    text: str


def _describe(spec: FieldSpec, indent: str) -> str:
    return f"{indent}- {spec.name} ({spec.kind.value}): {spec.description}"


def build_prompt(
    schema: CorpusSchema, source: Source = "images", version: int = PROMPT_VERSION
) -> Prompt:
    lines = []
    for f in schema.fields:
        if isinstance(f, FieldSpec):
            lines.append(_describe(f, ""))
        else:
            lines.append(
                f"- {f.name}: a list; each entry is {f.description[0].lower() + f.description[1:]}"
            )
            lines.extend(_describe(g, "    ") for g in f.fields)
    groups_rule = (
        "For a list, give one entry per row printed, in the order printed, with null for a "
        "column that row does not show; use [] when there are no rows."
        if schema.groups
        else "Each field holds one value."
    )
    text = _TEMPLATE.format(
        source=_SOURCE[source],
        what=schema.description[0].lower() + schema.description[1:],
        groups_rule=groups_rule,
        fields="\n".join(lines),
        schema=json.dumps(schema.json_schema(), separators=(",", ":")),
    )
    return Prompt(
        corpus=schema.corpus,
        version=version,
        source=source,
        schema_fingerprint=schema.fingerprint(),
        fields=tuple(all_names(schema.fields)),
        text=text,
    )


def save_prompt(prompt: Prompt, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(prompt.model_dump_json(indent=2) + "\n", encoding="utf-8", newline="\n")


def load_prompt(path: Path, schema: CorpusSchema) -> Prompt:
    """A stored prompt, refused if the schema it was built from is not the current one."""
    prompt = Prompt.model_validate_json(path.read_text(encoding="utf-8"))
    schema.require_aligned(prompt.fields, prompt.schema_fingerprint, what=f"prompt {path.name}")
    return prompt
