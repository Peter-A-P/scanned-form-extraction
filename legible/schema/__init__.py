"""One schema per corpus, and the single definition every other stage reads from.

The prompt an arm is given, the JSON target a fine-tune is trained on and the grader that
scores the answer are three views of the same field list. If they drift apart the numbers
stop meaning what they say: a field the prompt never asked for is scored as missing, a field
the training target carries but the grader does not is learned and never measured. So each
of them is built from a `CorpusSchema`, each stored artefact (a prompt file, a training set,
a run's predictions) records the schema's fingerprint and field names, and loading one whose
fingerprint or names differ from the current schema raises `SchemaDrift` rather than
continuing on a definition nobody wrote.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Iterator, Mapping, Sequence
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

#: A field's value as truth or prediction: the printed text, or None when the page does
#: not carry it. Repeated groups (line items) are a list of such mappings.
Scalar = str | None
Item = dict[str, Scalar]
Value = Scalar | list[Item]
Record = dict[str, Value]


class SchemaDrift(Exception):
    """A stored artefact names fields, or carries a fingerprint, the current schema does not."""


class FieldKind(StrEnum):
    """How a field's value is compared with the truth. One matcher per kind, in grade.py,
    each VRDU's own where VRDU has one."""

    #: Free text: descriptions, titles, organisations. Letters and digits compared exactly.
    STRING = "string"
    #: A person's or registrant's name. Compared with whitespace removed, case kept.
    NAME = "name"
    #: An identifier: a registration number, a contract number, a tax id. Digits only,
    #: compared exactly, because a digit off is a different record.
    CODE = "code"
    #: A postal address. Within three edits.
    ADDRESS = "address"
    #: A calendar date in any of the formats forms print. Compared as a date.
    DATE = "date"
    #: A count or a quantity. Compared as a number.
    NUMBER = "number"
    #: An amount of money. Currency marks and thousands separators removed, within a cent.
    PRICE = "price"


class FieldSpec(BaseModel):
    """One scalar field."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    kind: FieldKind
    description: str
    #: For DATE: read 03/04/2021 as 3 April rather than 4 March. US forms print month first.
    day_first: bool = False
    #: For PRICE and NUMBER: the decimal mark the corpus prints, or None when amounts are
    #: whole units and every '.' or ',' is a thousands separator (Indonesian receipts).
    decimal_mark: Literal[".", ","] | None = "."


class GroupSpec(BaseModel):
    """A repeated group: line items on an ad-buy order or a receipt."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    description: str
    fields: tuple[FieldSpec, ...]

    @model_validator(mode="after")
    def _unique(self) -> GroupSpec:
        _require_unique(f.name for f in self.fields)
        return self

    def field(self, name: str) -> FieldSpec:
        for f in self.fields:
            if f.name == name:
                return f
        raise KeyError(f"{self.name} has no field {name!r}")


class CorpusSchema(BaseModel):
    """The fields of one corpus: what is asked, what is trained on, what is graded."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    corpus: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    version: int = Field(ge=1)
    description: str
    fields: tuple[FieldSpec | GroupSpec, ...]

    @model_validator(mode="after")
    def _unique(self) -> CorpusSchema:
        _require_unique(f.name for f in self.fields)
        return self

    @property
    def scalars(self) -> tuple[FieldSpec, ...]:
        return tuple(f for f in self.fields if isinstance(f, FieldSpec))

    @property
    def groups(self) -> tuple[GroupSpec, ...]:
        return tuple(f for f in self.fields if isinstance(f, GroupSpec))

    def names(self) -> frozenset[str]:
        """Every field path: scalars by name, group members as `group.field`."""
        return frozenset(_paths(self))

    def fingerprint(self) -> str:
        """sha256 of the canonical definition. Changes whenever any field, kind or option does."""
        canonical = json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()

    def json_schema(self) -> dict[str, Any]:
        """The JSON Schema an arm's output must satisfy. Every value is a string or null:
        the model copies what is printed, and the grader does the parsing."""

        def scalar(f: FieldSpec) -> dict[str, Any]:
            return {"type": ["string", "null"], "description": f.description}

        props: dict[str, Any] = {}
        for f in self.fields:
            if isinstance(f, FieldSpec):
                props[f.name] = scalar(f)
            else:
                props[f.name] = {
                    "type": "array",
                    "description": f.description,
                    "items": {
                        "type": "object",
                        "properties": {g.name: scalar(g) for g in f.fields},
                        "required": [g.name for g in f.fields],
                        "additionalProperties": False,
                    },
                }
        return {
            "type": "object",
            "properties": props,
            "required": [f.name for f in self.fields],
            "additionalProperties": False,
        }

    def target(self, truth: Record) -> str:
        """The training target for one page: canonical JSON, keys in schema order.

        Refuses a truth record that names a field the schema does not, so a loader bug
        cannot quietly teach a model a field the grader will never score.
        """
        self.check_record(truth, what="truth record")
        out: dict[str, Value] = {}
        for f in self.fields:
            if isinstance(f, FieldSpec):
                v = truth.get(f.name)
                out[f.name] = v if isinstance(v, str) else None
            else:
                raw = truth.get(f.name)
                items = raw if isinstance(raw, list) else []
                out[f.name] = [{g.name: item.get(g.name) for g in f.fields} for item in items]
        return json.dumps(out, ensure_ascii=False, separators=(",", ":"))

    def check_record(self, record: Mapping[str, Any], *, what: str) -> None:
        """Raise SchemaDrift if a record names a field outside the schema."""
        groups = {g.name for g in self.groups}
        unknown = set(_record_paths(record, groups)) - self.names()
        if unknown:
            raise SchemaDrift(
                f"{what} names fields the {self.corpus} schema does not: {sorted(unknown)}"
            )

    def require_aligned(self, names: Iterable[str], fingerprint: str | None, *, what: str) -> None:
        """Refuse a stored artefact built from a different definition of this schema.

        `names` are the field paths the artefact was built with; `fingerprint` the schema
        fingerprint it recorded. Both must match: the names catch a hand-edited prompt, the
        fingerprint catches a changed matcher or option behind an unchanged name.
        """
        got = frozenset(names)
        want = self.names()
        if got != want:
            raise SchemaDrift(
                f"{what} was built for fields the {self.corpus} schema does not have: "
                f"missing {sorted(want - got)}, extra {sorted(got - want)}"
            )
        if fingerprint is not None and fingerprint != self.fingerprint():
            raise SchemaDrift(
                f"{what} was built from {self.corpus} schema {fingerprint[:12]}, "
                f"current is {self.fingerprint()[:12]}; rebuild it"
            )


def _require_unique(names: Iterable[str]) -> None:
    seen: set[str] = set()
    for n in names:
        if n in seen:
            raise ValueError(f"field {n!r} defined twice")
        seen.add(n)


def _paths(schema: CorpusSchema) -> Iterator[str]:
    for f in schema.fields:
        if isinstance(f, FieldSpec):
            yield f.name
        else:
            for g in f.fields:
                yield f"{f.name}.{g.name}"


def _record_paths(record: Mapping[str, Any], groups: set[str]) -> Iterator[str]:
    for key, value in record.items():
        if isinstance(value, list):
            for item in value:
                if isinstance(item, Mapping):
                    for sub in item:
                        yield f"{key}.{sub}"
        elif key not in groups or value is not None:
            # A group may be null (no line items printed); anything else under its name,
            # or any other unknown key, is reported.
            yield key


def all_names(fields: Sequence[FieldSpec | GroupSpec]) -> list[str]:
    """Field paths in schema order, for prompts and reports that list them."""
    out: list[str] = []
    for f in fields:
        if isinstance(f, FieldSpec):
            out.append(f.name)
        else:
            out.extend(f"{f.name}.{g.name}" for g in f.fields)
    return out
