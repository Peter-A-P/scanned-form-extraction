"""The review rate: how many fields a person still checks for the rest to be right.

Each arm gives every field a confidence. A threshold is chosen on dev: the lowest at which
the fields accepted (confidence at or above it) are at least the target accuracy, which is
the threshold that sends the fewest fields to a person on dev. That threshold is then applied
to test, once, and the two numbers reported are the share of test fields routed to review and
the accuracy of the fields that were not, each with its interval over documents. A test
accuracy below the target is reported as it is, not re-tuned: that is the honest cost of a
threshold chosen on other pages.

A field with no confidence goes to review. So does every field of an arm whose threshold
could not reach the target on dev.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict

from legible.grade import DocGrade, FieldOutcome
from legible.stats import Interval, ratio_ci

TARGET: float = 0.99


class Threshold(BaseModel):
    model_config = ConfigDict(frozen=True)

    target: float
    #: math.inf when no threshold reached the target on dev.
    value: float
    dev_accepted_accuracy: float
    dev_review_rate: float


class ReviewResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    threshold: Threshold
    review_rate: Interval
    accepted_accuracy: Interval


def _accepted(o: FieldOutcome, threshold: float) -> bool:
    return o.confidence is not None and o.confidence >= threshold


def choose_threshold(dev: Sequence[DocGrade], *, target: float = TARGET) -> Threshold:
    """The lowest confidence threshold at which the accepted dev fields reach the target."""
    fields = [o for g in dev for o in g.outcomes]
    scored = [(o.confidence, o.correct) for o in fields if o.confidence is not None]
    total = len(fields)
    # Sweep from the highest confidence down, accumulating; ties enter together.
    scored.sort(key=lambda pair: pair[0], reverse=True)
    best: Threshold | None = None
    accepted = right = 0
    i = 0
    while i < len(scored):
        c = scored[i][0]
        while i < len(scored) and scored[i][0] == c:
            accepted += 1
            right += scored[i][1]
            i += 1
        if right / accepted >= target:
            best = Threshold(
                target=target,
                value=c,
                dev_accepted_accuracy=right / accepted,
                dev_review_rate=1 - accepted / total,
            )
    if best is None:
        return Threshold(
            target=target, value=math.inf, dev_accepted_accuracy=math.nan, dev_review_rate=1.0
        )
    return best


def review(
    dev: Sequence[DocGrade], test: Sequence[DocGrade], *, target: float = TARGET, seed: int = 0
) -> ReviewResult:
    """Choose the threshold on dev and measure what it does on test."""
    threshold = choose_threshold(dev, target=target)
    reviewed: list[float] = []
    fields: list[float] = []
    right: list[float] = []
    accepted: list[float] = []
    for g in test:
        acc = [o for o in g.outcomes if _accepted(o, threshold.value)]
        reviewed.append(float(g.scored - len(acc)))
        fields.append(float(g.scored))
        right.append(float(sum(o.correct for o in acc)))
        accepted.append(float(len(acc)))
    return ReviewResult(
        threshold=threshold,
        review_rate=ratio_ci(reviewed, fields, seed=seed),
        accepted_accuracy=ratio_ci(right, accepted, seed=seed),
    )
