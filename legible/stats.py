"""The intervals every reported number carries.

Resampling is over documents, never over fields: the fields of one form are not independent
(a skewed scan gets several wrong at once), and resampling fields would treat them as if they
were and report an interval too narrow. Paired comparisons refuse two runs that did not grade
the same documents, which is the mistake they exist to make impossible. Carried over from
06's grader, where the same two rules held.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import numpy as np
from pydantic import BaseModel, ConfigDict

RESAMPLES = 10_000


class Interval(BaseModel):
    """A point estimate and its 95% bootstrap interval."""

    model_config = ConfigDict(frozen=True)

    point: float
    low: float
    high: float
    n: int

    def __str__(self) -> str:
        return f"{self.point:.1%} ({self.low:.1%} to {self.high:.1%}, n = {self.n:,})"


class UnpairedItems(ValueError):
    """Two runs compared as paired did not grade the same documents."""


def _percentile_interval(means: np.ndarray) -> tuple[float, float]:
    low, high = np.percentile(means, [2.5, 97.5])
    return float(low), float(high)


def ratio_ci(
    numerators: Sequence[float],
    denominators: Sequence[float],
    *,
    resamples: int = RESAMPLES,
    seed: int = 0,
) -> Interval:
    """sum(numerators) / sum(denominators) with documents as the resampling unit.

    Field accuracy is a ratio, correct fields over scored fields, summed over documents that
    carry different numbers of fields. Resampling documents and recomputing the ratio keeps a
    forty-line ad-buy order from counting as one field and a three-field registration as one
    document's worth of fields at the same time.
    """
    num = np.asarray(numerators, dtype=float)
    den = np.asarray(denominators, dtype=float)
    if num.shape != den.shape:
        raise ValueError("numerators and denominators must be the same length")
    n = int(num.size)
    if n == 0 or den.sum() == 0:
        return Interval(point=float("nan"), low=float("nan"), high=float("nan"), n=n)
    rng = np.random.default_rng(seed)
    draws = rng.integers(0, n, size=(resamples, n))
    d = den[draws].sum(axis=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        ratios = num[draws].sum(axis=1) / d
    ratios = ratios[d > 0]
    low, high = _percentile_interval(ratios)
    return Interval(point=float(num.sum() / den.sum()), low=low, high=high, n=n)


def mean_ci(values: Sequence[float], *, resamples: int = RESAMPLES, seed: int = 0) -> Interval:
    """The mean of per-document values, e.g. the every-field-right rate."""
    return ratio_ci(values, [1.0] * len(values), resamples=resamples, seed=seed)


def paired_ratio_delta_ci(
    a: Mapping[str, tuple[float, float]],
    b: Mapping[str, tuple[float, float]],
    *,
    resamples: int = RESAMPLES,
    seed: int = 0,
) -> Interval:
    """The paired difference of two ratios, `a - b`, over the same documents.

    Each mapping is document id to (numerator, denominator). The same resampled documents
    are drawn for both arms on every replicate, which is what makes it paired.
    """
    if a.keys() != b.keys():
        only_a = sorted(a.keys() - b.keys())[:3]
        only_b = sorted(b.keys() - a.keys())[:3]
        raise UnpairedItems(
            f"paired comparison needs identical documents: {len(a)} against {len(b)}, "
            f"first differences {only_a} / {only_b}"
        )
    ids = sorted(a)
    n = len(ids)
    if n == 0:
        return Interval(point=float("nan"), low=float("nan"), high=float("nan"), n=0)
    an = np.array([a[i][0] for i in ids], dtype=float)
    ad = np.array([a[i][1] for i in ids], dtype=float)
    bn = np.array([b[i][0] for i in ids], dtype=float)
    bd = np.array([b[i][1] for i in ids], dtype=float)
    rng = np.random.default_rng(seed)
    draws = rng.integers(0, n, size=(resamples, n))
    with np.errstate(invalid="ignore", divide="ignore"):
        deltas = an[draws].sum(1) / ad[draws].sum(1) - bn[draws].sum(1) / bd[draws].sum(1)
    deltas = deltas[np.isfinite(deltas)]
    low, high = _percentile_interval(deltas)
    point = float(an.sum() / ad.sum() - bn.sum() / bd.sum())
    return Interval(point=point, low=low, high=high, n=n)
