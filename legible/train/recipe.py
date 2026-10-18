"""Arm B's recipe: what one fine-tune is, and which ones the plan needs.

06's recipe with a vision encoder (PLAN.md section 2.3): Gemma 4 E2B and E4B, QLoRA on the
4-bit base, the vision tower frozen, adapters on the language layers and on the projector
that maps the vision tower into them. A `TrainConfig` is the whole of a run, and its id is a
hash of its contents, so the same recipe resumes rather than starting a second copy.

The bases are 06's, at the revisions 06 resolved on 2026-09-21; their instruction models are
arm C, and give the base its chat template.
"""

from __future__ import annotations

import hashlib
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field

Size = Literal["2b", "4b"]
#: Visual tokens per page image: Gemma 4's processor offers 70, 140, 280, 560 and 1,120. The
#: card recommends the top of the range for document parsing; 560 is the ablation, because it
#: halves the cost per page if accuracy holds.
VisualTokens = Literal[560, 1120]


class Base(BaseModel):
    model_config = ConfigDict(frozen=True)

    repo: str
    revision: str
    instruct_repo: str
    instruct_revision: str


#: As 06 recorded them (smallprint/train/recipe.py at 3adf4fad, docs/models.md there).
BASES: Final[dict[Size, Base]] = {
    "2b": Base(
        repo="google/gemma-4-E2B",
        revision="d29ff6b45f081a49ee2733a859c9c9c2d95d1a6f",
        instruct_repo="google/gemma-4-E2B-it",
        instruct_revision="3e22461f65e89153144f8adb70e3b8c2cc9845a7",
    ),
    "4b": Base(
        repo="google/gemma-4-E4B",
        revision="411aa17b749aa952df1359d2dcea73917a544d9a",
        instruct_repo="google/gemma-4-E4B-it",
        instruct_revision="ee0ef6023621cff504d758262d4e04895a5af4a2",
    ),
}

#: Adapters on the language model's attention and MLP projections and on the vision
#: projector (`embed_vision.embedding_projection`), never on the vision or audio towers.
TARGET_MODULES: Final = (
    r"^(?!.*(?:vision_tower|audio_tower|embed_audio))"
    r".*(?:\.(?:q|k|v|o|gate|up|down)_proj|embed_vision\.embedding_projection)$"
)


class TrainConfig(BaseModel):
    """One QLoRA run on page images, entire."""

    model_config = ConfigDict(frozen=True)

    size: Size
    #: The training set file it reads (legible/train/dataset.py), by name.
    dataset: str
    #: 06's chosen recipes: 2B at rank 64 and 1e-4, 4B at rank 16 and 2e-4, one epoch.
    rank: int = Field(ge=1)
    alpha: int = Field(ge=1)
    learning_rate: float = Field(gt=0)
    epochs: int = 1
    batch_size: int = 1
    grad_accum: int = 8
    warmup_ratio: float = 0.03
    dropout: float = 0.05
    visual_tokens: VisualTokens = 1120
    #: Training documents used: None for all, else the first n in the set's order (the
    #: data-volume ablation).
    volume: int | None = None
    max_seq_len: int = 12_288
    save_steps: int = 25
    seed: int = 0

    @property
    def base(self) -> Base:
        return BASES[self.size]

    @property
    def run_id(self) -> str:
        digest = hashlib.sha256(self.model_dump_json().encode()).hexdigest()[:10]
        return f"{self.size}-{self.dataset}-v{self.visual_tokens}-s{self.seed}-{digest}"


#: DeepForm trains at 560 visual tokens a page. Its orders run to eleven pages, and at 1,120
#: the 2B ran out of memory on a 24 GB card at the third step of its first run (2026-10-18),
#: with the documents over 12,288 tokens already left out. 560 is the plan's own ablation
#: value, and the README says which budget each corpus's fine-tune read at.
VISUAL_TOKENS_FOR: Final[dict[str, VisualTokens]] = {"deepform": 560}


def chosen(size: Size, dataset: str, *, seed: int = 0, **changes: object) -> TrainConfig:
    """06's chosen recipe for a size on a training set, with any ablation's changes."""
    rank, lr = (64, 1e-4) if size == "2b" else (16, 2e-4)
    corpus = dataset.split("-")[0]
    base = TrainConfig(
        size=size,
        dataset=dataset,
        rank=rank,
        alpha=2 * rank,
        learning_rate=lr,
        visual_tokens=VISUAL_TOKENS_FOR.get(corpus, 1120),
    )
    return base.model_copy(update={"seed": seed, **changes})
