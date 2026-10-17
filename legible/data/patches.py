"""Label corrections from the hand audit, applied by the loaders and never silently.

A label the audit marked wrong, with the value the page actually shows, becomes a patch in
`legible/data/patches.json`, written by `legible data audit-report` from
docs/audit/decisions.json and committed. The loaders apply every patch to the truth they
return and name the patched fields on the document, so a result that a patch changed can say
so. The benchmark's other candidates for a patched field are dropped with it: they are the
same misreading, recorded at another place on the page.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from functools import cache
from importlib import resources
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from legible.data.audit import Decision
from legible.schema import Record


class Patch(BaseModel):
    model_config = ConfigDict(frozen=True)

    corpus: str
    doc_id: str
    key: str
    value: str


def patches_from(decisions: Sequence[Decision]) -> list[Patch]:
    """A patch for every label marked wrong with a corrected value."""
    out = []
    for d in decisions:
        if d.verdict != "wrong" or not d.corrected:
            continue
        corpus, rest = d.label_id.split("/", 1)
        doc_id, key = rest.rsplit("/", 1)
        out.append(Patch(corpus=corpus, doc_id=doc_id, key=key, value=d.corrected))
    return sorted(out, key=lambda p: (p.corpus, p.doc_id, p.key))


def write_patches(path: Path, patches: Sequence[Patch]) -> None:
    path.write_text(
        json.dumps([p.model_dump() for p in patches], indent=1) + "\n",
        encoding="utf-8",
        newline="\n",
    )


@cache
def _all() -> tuple[Patch, ...]:
    source = resources.files("legible.data").joinpath("patches.json")
    if not source.is_file():
        return ()
    return tuple(Patch.model_validate(p) for p in json.loads(source.read_text("utf-8")))


_ITEM = re.compile(r"^(?P<group>[a-z_]+)\[(?P<index>\d+)\]\.(?P<field>[a-z_]+)$")


def apply(
    corpus: str,
    doc_id: str,
    truth: Record,
    alternatives: Mapping[str, list[str]],
    patches: Sequence[Patch] | None = None,
) -> tuple[Record, dict[str, list[str]], tuple[str, ...]]:
    """(truth, alternatives, patched keys) with every patch for this document applied."""
    mine = [
        p
        for p in (_all() if patches is None else patches)
        if p.corpus == corpus and p.doc_id == doc_id
    ]
    if not mine:
        return truth, dict(alternatives), ()
    out: Record = {
        k: ([dict(i) for i in v] if isinstance(v, list) else v) for k, v in truth.items()
    }
    alts = dict(alternatives)
    for p in mine:
        m = _ITEM.match(p.key)
        if m:
            items = out.get(m["group"])
            index = int(m["index"])
            if not isinstance(items, list) or index >= len(items):
                raise KeyError(f"patch {p.key} for {doc_id}: no such line item")
            items[index][m["field"]] = p.value
        else:
            if p.key not in out:
                raise KeyError(f"patch {p.key} for {doc_id}: no such field in the truth")
            out[p.key] = p.value
            alts.pop(p.key, None)
    return out, alts, tuple(p.key for p in mine)
