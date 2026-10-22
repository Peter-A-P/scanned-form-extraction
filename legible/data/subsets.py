"""The three test subsets the plan names, drawn once and committed (`manifests/subsets.json`).

- **ceiling**: about 600 pages the top Anthropic tier (Claude Opus 5.5) reads, to show how
  far above the quality model the frontier goes (PLAN.md section 7).
- **repeat**: about 200 pages the quality model reads a second time, so a difference between
  arms can be set against how much one arm differs from itself (the noise floor).
- **vrdu_curve**: about 150 VRDU pages read at degradation levels 2 and 4 beside level 0, the
  curve's check on real scans (PLAN.md section 2.5).

Every subset is drawn from the headline test documents only, in a fixed hash order per subset,
whole documents at a time until the page budget is reached, so a stranger draws the same pages.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path

#: Pages per subset and corpus.
BUDGETS: Mapping[str, Mapping[str, int]] = {
    "ceiling": {"fara": 200, "deepform": 150, "cord": 50, "nist": 200},
    "repeat": {"fara": 70, "deepform": 50, "cord": 30, "nist": 50},
    "vrdu_curve": {"fara": 75, "deepform": 75},
}


def _order(subset: str, doc_id: str) -> str:
    return hashlib.sha256(f"legible-subset/{subset}/{doc_id}".encode()).hexdigest()


def draw(subset: str, docs: Sequence[str], pages: Mapping[str, int], budget: int) -> list[str]:
    """Whole documents in the subset's hash order while they fit the page budget."""
    chosen: list[str] = []
    total = 0
    for d in sorted(docs, key=lambda d: _order(subset, d)):
        if total + pages[d] > budget:
            continue
        chosen.append(d)
        total += pages[d]
        if total == budget:
            break
    return sorted(chosen)


def build(
    test_docs: Mapping[str, Sequence[str]], pages: Mapping[str, int]
) -> dict[str, dict[str, list[str]]]:
    """Every subset, per corpus, from each corpus's headline test documents."""
    return {
        subset: {c: draw(subset, test_docs[c], pages, budget) for c, budget in per.items()}
        for subset, per in BUDGETS.items()
    }


def write(path: Path, subsets: Mapping[str, Mapping[str, Sequence[str]]]) -> None:
    path.write_text(
        json.dumps({"source": "legible.data.subsets.build", "subsets": subsets}, indent=1) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def read(path: Path) -> dict[str, dict[str, list[str]]]:
    raw: dict[str, dict[str, list[str]]] = json.loads(path.read_text(encoding="utf-8"))["subsets"]
    return raw
