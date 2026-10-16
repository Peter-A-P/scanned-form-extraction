"""The committed summary of a corpus's headline splits: which files, how many documents and
pages in each part, and the union every evaluated arm reads.

The arms read each test document once, over the union of the three seeds' test sets, and
each seed's number is graded from those reads; so the union's page count is what a full arm
costs, and it is recorded here before anything is spent.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

from legible.data.vrdu import VrduDoc, VrduSplit


def write_splits(
    path: Path, corpus: str, docs: Sequence[VrduDoc], splits: Sequence[VrduSplit]
) -> None:
    pages = {d.doc_id: d.pages for d in docs}

    def count(ids: Sequence[str]) -> dict[str, int]:
        return {"documents": len(ids), "pages": sum(pages[i] for i in ids)}

    union_test = sorted({i for s in splits for i in s.test})
    union_valid = sorted({i for s in splits for i in s.valid})
    out = {
        "corpus": corpus,
        "documents": len(docs),
        "pages": sum(pages.values()),
        "files": [
            {
                "file": s.file,
                "level": s.level,
                "template": s.template,
                "seed": s.seed,
                "train": count(s.train),
                "valid": count(s.valid),
                "test": count(s.test),
            }
            for s in splits
        ],
        "union": {"test": count(union_test), "valid": count(union_valid)},
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8", newline="\n")
