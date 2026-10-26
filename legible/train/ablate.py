"""The ablations (PLAN.md 2.3, as changed 2026-10-26): what one change to the recipe does,
each run on E2B at seed 0 and compared with the seed-0 E2B already measured.

- **Visual tokens:** 560 against 1,120 on every headline training set, because 560 halves
  the image's share of a page's cost if accuracy holds.
- **Data volume:** half and a quarter of what the headline model trained on, for NIST (800
  faces) and CORD (800 receipts).
- **One model for every corpus:** FARA's and DeepForm's mixed-template sets, CORD and NIST's
  800 faces in one run, against the specialists on the tables they share.

Each ablation is a `TrainConfig` the recipe already describes, so its run id, its resume and
its reads are those of any other fine-tune.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from legible.train.recipe import VOLUME_FOR, TrainConfig, chosen

#: The training set name of the multi-corpus run.
MULTI: Final = "all"

#: The sets the multi-corpus model learns from, in `train sets`' names; "nist" is the twenty
#: faces' sets, cut to the headline's 800 as the NIST model was.
MULTI_SETS: Final = ("fara-mixed-s0", "deepform-mixed-s0", "cord", "nist")

#: The headline training sets, each read by its own seed-0 model (report.TABLE_SETS).
HEADLINE_SETS: Final = (
    "fara-unseen-amendment-s0",
    "fara-unseen-dissemination_report-s0",
    "fara-unseen-short-form-s0",
    "deepform-unseen-s0",
    "cord",
    "nist",
)

#: Training documents in the headline model of each corpus the volume curve is run on.
FULL_VOLUME: Final = {"nist": VOLUME_FOR["nist"], "cord": 800}


@dataclass(frozen=True)
class Ablation:
    """One run: which ablation it belongs to, and its recipe."""

    kind: str
    config: TrainConfig

    @property
    def level0_only(self) -> bool:
        """Whether its reads stop at the clean pages. The volume and multi-corpus runs answer
        a question about clean pages; the visual-token runs read every level the headline
        model read, since the plan expects the budget to matter on bad scans."""
        return self.kind != "visual-tokens"


def ablations() -> list[Ablation]:
    """Every ablation run, in the order they are trained."""
    out = [Ablation("visual-tokens", chosen("2b", ds, visual_tokens=560)) for ds in HEADLINE_SETS]
    for corpus, full in FULL_VOLUME.items():
        out += [Ablation("volume", chosen("2b", corpus, volume=full // d)) for d in (2, 4)]
    out.append(Ablation("multi-corpus", chosen("2b", MULTI)))
    return out


def find(run_id: str) -> Ablation | None:
    """The ablation a run id belongs to, if it is one."""
    return next((a for a in ablations() if a.config.run_id == run_id), None)
