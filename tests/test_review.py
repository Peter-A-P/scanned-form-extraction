"""The review-rate arithmetic on confidence streams with known answers."""

from __future__ import annotations

import math

import pytest

from legible.grade import DocGrade, FieldOutcome, Outcome
from legible.review import choose_threshold, review


def doc(doc_id: str, fields: list[tuple[float | None, bool]]) -> DocGrade:
    return DocGrade(
        doc_id=doc_id,
        outcomes=tuple(
            FieldOutcome(
                path=f"f{i}",
                index=None,
                outcome=Outcome.CORRECT if right else Outcome.WRONG_VALUE,
                truth="t",
                predicted="t" if right else "x",
                confidence=c,
            )
            for i, (c, right) in enumerate(fields)
        ),
        abstained=0,
        unparsed=False,
        extra_keys=(),
    )


def stream() -> list[DocGrade]:
    """100 fields in 10 documents: confidence 0.9 and up always right (80 fields), 0.5 right
    half the time (20 fields)."""
    docs = []
    for d in range(10):
        fields: list[tuple[float | None, bool]] = [(0.9 + d / 100, True)] * 8
        fields += [(0.5, True), (0.5, False)]
        docs.append(doc(str(d), fields))
    return docs


def test_threshold_excludes_the_unreliable_band() -> None:
    t = choose_threshold(stream(), target=0.99)
    assert t.value == pytest.approx(0.9)
    assert t.dev_accepted_accuracy == 1.0
    assert t.dev_review_rate == pytest.approx(0.2)


def test_a_lower_target_accepts_the_band() -> None:
    # Everything accepted is 90 right of 100: 0.9 accuracy, so a 0.9 target accepts all.
    t = choose_threshold(stream(), target=0.9)
    assert t.value == pytest.approx(0.5)
    assert t.dev_review_rate == 0


def test_unreachable_target_reviews_everything() -> None:
    always_half = [doc("a", [(0.8, True), (0.8, False)])]
    t = choose_threshold(always_half, target=0.99)
    assert math.isinf(t.value)
    r = review(always_half, always_half, target=0.99)
    assert r.review_rate.point == 1.0


def test_fields_without_confidence_go_to_review() -> None:
    test = [doc("a", [(None, True), (0.95, True)])]
    r = review(stream(), test, target=0.99)
    assert r.review_rate.point == pytest.approx(0.5)
    assert r.accepted_accuracy.point == 1.0


def test_threshold_from_dev_is_applied_to_test_unchanged() -> None:
    # On test the 0.9 band is wrong a tenth of the time; the result reports that rather
    # than re-tuning.
    test = [doc(str(d), [(0.95, i != 0) for i in range(10)]) for d in range(10)]
    r = review(stream(), test, target=0.99)
    assert r.threshold.value == pytest.approx(0.9)
    assert r.review_rate.point == 0
    assert r.accepted_accuracy.point == pytest.approx(0.9)


def test_the_table_says_when_a_dev_threshold_accepts_nothing_on_test() -> None:
    import math

    from legible.report import review_table
    from legible.review import ReviewResult, Threshold
    from legible.stats import Interval

    nothing = Interval(point=math.nan, low=math.nan, high=math.nan, n=10)
    r = ReviewResult(
        threshold=Threshold(
            target=0.99, value=0.9999, dev_accepted_accuracy=1.0, dev_review_rate=0.99
        ),
        review_rate=Interval(point=1.0, low=1.0, high=1.0, n=10),
        accepted_accuracy=nothing,
    )
    row = review_table([("DeepForm", r)])[2]
    assert "none accepted on test" in row and "nan" not in row
