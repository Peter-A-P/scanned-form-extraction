"""Splits, the dev carve-out, and the leakage checks that run on every build.

VRDU and CORD come with their own splits and those are honoured, so that "unseen template"
means what the benchmark means. NIST SD2 does not, and its 5,590 pages are 900 simulated
submissions of a twelve-form tax package: pages of one submission share a name, an address
and the numbers that carry from schedule to return. A page-level split would put a
submission's Schedule B in train and its 1040 in test. So NIST is split by submission, and
the dev set is carved from train by the same rule.

Assignment is by hash of the group key, not by a shuffled list, so that adding a page to the
corpus does not move any other page between splits.
"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping
from typing import Final, Literal

Split = Literal["train", "dev", "test"]
SPLITS: Final[tuple[Split, ...]] = ("train", "dev", "test")


class SplitLeak(Exception):
    """A group (a NIST submission, a VRDU template on the unseen split) is in two splits."""


def _unit(key: str, salt: str) -> float:
    """A stable number in [0, 1) for a key."""
    digest = hashlib.sha256(f"{salt}:{key}".encode()).digest()
    return int.from_bytes(digest[:8], "big") / 2**64


def split_by_group(
    doc_ids: Iterable[str],
    group_of: Callable[[str], str],
    *,
    test: float,
    dev: float,
    salt: str,
) -> dict[str, Split]:
    """Assign every document to a split by its group, so a group never straddles two."""
    if not (0 < test < 1 and 0 <= dev < 1 and test + dev < 1):
        raise ValueError("test and dev must be fractions that leave room for train")
    out: dict[str, Split] = {}
    for doc in doc_ids:
        u = _unit(group_of(doc), salt)
        out[doc] = "test" if u < test else "dev" if u < test + dev else "train"
    return out


def carve_dev(
    assignment: Mapping[str, Split],
    group_of: Callable[[str], str],
    *,
    fraction: float,
    salt: str,
) -> dict[str, Split]:
    """Move a share of train's groups to dev, for thresholds and prompt iteration, so that
    test is touched once per arm. Test is never read here."""
    if not 0 < fraction < 1:
        raise ValueError("fraction must be between 0 and 1")
    out = dict(assignment)
    for doc, split in assignment.items():
        if split == "train" and _unit(group_of(doc), f"dev:{salt}") < fraction:
            out[doc] = "dev"
    return out


def check_disjoint(
    assignment: Mapping[str, Split], group_of: Callable[[str], str], *, what: str
) -> None:
    """Raise SplitLeak if any group has documents in more than one split."""
    splits_of: defaultdict[str, set[Split]] = defaultdict(set)
    for doc, split in assignment.items():
        splits_of[group_of(doc)].add(split)
    leaked = sorted(g for g, s in splits_of.items() if len(s) > 1)
    if leaked:
        raise SplitLeak(f"{len(leaked)} {what} in more than one split, first {leaked[:5]}")


def check_unseen_templates(
    train_templates: Iterable[str], test_templates: Iterable[str], *, corpus: str
) -> None:
    """The unseen-template claim: no template in test was in train (or dev)."""
    shared = sorted(set(train_templates) & set(test_templates))
    if shared:
        raise SplitLeak(f"{corpus} unseen-template split shares templates {shared[:5]}")
