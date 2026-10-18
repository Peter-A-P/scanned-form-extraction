"""No NIST submission in two splits; no shared template on the unseen-template split."""

from __future__ import annotations

import pytest

from legible.data.split import (
    SplitLeak,
    carve_dev,
    check_disjoint,
    check_unseen_templates,
    split_by_group,
)

# 90 submissions of 6 pages each, ids shaped like NIST's: submission then page.
DOCS = [f"f{s:04d}_{p:02d}" for s in range(90) for p in range(6)]


def submission(doc: str) -> str:
    return doc.split("_")[0]


def test_split_by_submission_keeps_submissions_whole() -> None:
    a = split_by_group(DOCS, submission, test=0.2, dev=0.1, salt="nist")
    check_disjoint(a, submission, what="submissions")
    assert set(a.values()) == {"train", "dev", "test"}


def test_page_level_split_is_caught() -> None:
    a = split_by_group(DOCS, lambda d: d, test=0.3, dev=0.0, salt="nist")
    with pytest.raises(SplitLeak, match="submissions"):
        check_disjoint(a, submission, what="submissions")


def test_adding_a_page_moves_no_other_page() -> None:
    before = split_by_group(DOCS, submission, test=0.2, dev=0.1, salt="nist")
    after = split_by_group([*DOCS, "f9999_00"], submission, test=0.2, dev=0.1, salt="nist")
    assert all(after[d] == before[d] for d in DOCS)


def test_dev_comes_from_train_only() -> None:
    a = split_by_group(DOCS, submission, test=0.2, dev=0.0, salt="nist")
    b = carve_dev(a, submission, fraction=0.15, salt="nist")
    assert {d for d, s in a.items() if s == "test"} == {d for d, s in b.items() if s == "test"}
    assert any(s == "dev" for s in b.values())
    check_disjoint(b, submission, what="submissions")


def test_unseen_templates_must_be_disjoint() -> None:
    check_unseen_templates({"t1", "t2"}, {"t3"}, corpus="adbuy")
    with pytest.raises(SplitLeak, match="t2"):
        check_unseen_templates({"t1", "t2"}, {"t2", "t3"}, corpus="adbuy")


def test_a_subset_takes_whole_documents_up_to_its_page_budget() -> None:
    from legible.data.subsets import draw

    pages = {f"d{i}": 1 + i % 3 for i in range(50)}
    chosen = draw("ceiling", sorted(pages), pages, 20)
    assert sum(pages[d] for d in chosen) <= 20 and len(chosen) >= 7
    assert chosen == draw("ceiling", sorted(pages, reverse=True), pages, 20)
    assert chosen != draw("repeat", sorted(pages), pages, 20)
