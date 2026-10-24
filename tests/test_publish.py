"""Publishing: no card, no upload; private unless asked; the card is the one for this run."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

import pytest

from legible.cards import (
    CardFacts,
    Measured,
    TrainingCounts,
    read_front_matter,
    render,
    training_counts,
)
from legible.publish import HubUploader, PublishRefused, publish
from legible.report import Row
from legible.schema.corpora import FARA
from legible.stats import Interval
from legible.train.dataset import TrainingHeader, TrainingRow
from legible.train.recipe import chosen

CONFIG = chosen("2b", "cord")
RUN = CONFIG.run_id


class FakeUploader:
    def __init__(self) -> None:
        self.repos: list[tuple[str, bool]] = []
        self.commits: list[tuple[str, list[str], str]] = []

    def create_repo(self, repo_id: str, *, private: bool) -> str:
        self.repos.append((repo_id, private))
        return f"someone/{repo_id}"

    def commit(self, repo_id: str, files: Sequence[tuple[str, Path]], message: str) -> str:
        self.commits.append((repo_id, [p for p, _ in files], message))
        return f"https://huggingface.co/{repo_id}/commit/abc"


def _adapter(tmp_path: Path, run_id: str = RUN) -> Path:
    adapter = tmp_path / "models" / run_id / "adapter"
    adapter.mkdir(parents=True)
    (adapter / "adapter_config.json").write_text(
        json.dumps({"base_model_name_or_path": CONFIG.base.repo}), encoding="utf-8"
    )
    (adapter / "adapter_model.safetensors").write_bytes(b"weights")
    (adapter / "run.json").write_text(json.dumps({"run_id": run_id}), encoding="utf-8")
    (adapter / "README.md").write_text("PEFT's stub card", encoding="utf-8")
    return adapter


def _card(tmp_path: Path, run_id: str = RUN, publishable: bool = True) -> Path:
    card = tmp_path / "cards" / f"{run_id}.md"
    card.parent.mkdir(parents=True, exist_ok=True)
    card.write_text(
        "---\n"
        f"base_model: {CONFIG.base.repo}\n"
        "library_name: peft\n"
        f"legible_run_id: {run_id}\n"
        f"legible_publishable: {'true' if publishable else 'false'}\n"
        "---\n\n# A card\n\n## Failure modes\n",
        encoding="utf-8",
    )
    return card


def test_no_card_no_upload(tmp_path: Path) -> None:
    fake = FakeUploader()
    with pytest.raises(PublishRefused, match="no card"):
        publish(_adapter(tmp_path), tmp_path / "cards" / f"{RUN}.md", "legible-x", fake)
    assert fake.repos == [] and fake.commits == []


def test_private_by_default_and_the_card_is_the_readme(tmp_path: Path) -> None:
    fake = FakeUploader()
    done = publish(_adapter(tmp_path), _card(tmp_path), f"legible-{RUN}", fake)
    assert fake.repos == [(f"legible-{RUN}", True)]
    assert done.private and done.repo_id == f"someone/legible-{RUN}"
    # One commit: the adapter's files and the card as README, never PEFT's stub README.
    [(repo, files, message)] = fake.commits
    assert repo == f"someone/legible-{RUN}"
    assert sorted(files) == [
        "README.md",
        "adapter_config.json",
        "adapter_model.safetensors",
        "run.json",
    ]
    assert RUN in message and done.card_sha256[:12] in message


def test_public_only_when_asked(tmp_path: Path) -> None:
    fake = FakeUploader()
    publish(_adapter(tmp_path), _card(tmp_path), "r", fake, private=False)
    assert fake.repos == [("r", False)]


def test_card_for_another_run_is_refused(tmp_path: Path) -> None:
    fake = FakeUploader()
    other = chosen("4b", "cord").run_id
    with pytest.raises(PublishRefused, match="card is for"):
        publish(_adapter(tmp_path), _card(tmp_path, run_id=other), "r", fake)
    assert fake.repos == []


def test_card_marked_not_for_upload_is_refused(tmp_path: Path) -> None:
    fake = FakeUploader()
    with pytest.raises(PublishRefused, match="not for upload"):
        publish(_adapter(tmp_path), _card(tmp_path, publishable=False), "r", fake)
    assert fake.repos == []


def test_no_token_no_upload(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HF_TOKEN", raising=False)
    with pytest.raises(PublishRefused, match="HF_TOKEN"):
        HubUploader()


def _interval(p: float) -> Interval:
    return Interval(point=p, low=p - 0.01, high=p + 0.01, n=100)


def test_rendered_card_has_hub_front_matter_and_plain_text() -> None:
    def r(label: str, acc: float, cost: float) -> Measured:
        return Measured(
            Row(label, 100, 0, _interval(acc), _interval(0.3), _interval(0.02), _interval(cost)),
            _interval(0.01),
        )

    facts = CardFacts(
        run_id=RUN,
        config=CONFIG,
        table="cord",
        schemas=[FARA],
        prompt_version=1,
        counts=TrainingCounts(800, 800, 800, {}, 0),
        record=None,
        test_name="CORD's 100 test receipts",
        own=[
            r("B, Gemma 4 E2B fine-tuned (this adapter)", 0.75, 0.11),
            r("C, Gemma 4 E2B untuned on the image", 0.40, 0.14),
            r("A, GPT-6.1 Sol on the image", 0.88, 4.59),
        ],
        gated_size="4b",
    )
    card = render(facts)
    meta = read_front_matter(card)
    assert meta["base_model"] == CONFIG.base.repo
    assert meta["base_model_revision"] == CONFIG.base.revision
    assert meta["library_name"] == "peft" and meta["license"] == "apache-2.0"
    assert meta["datasets"] == ["naver-clova-ix/cord-v2"]
    assert meta["legible_run_id"] == RUN and meta["legible_publishable"] is True
    assert card.isascii()
    assert "## Failure modes" in card and "## Training data and its licences" in card
    assert "GPT-6.1 Sol" in card and "-13.0 points" in card
    assert "Not gated" in card


def test_nist_counts_follow_the_training_order() -> None:
    config = chosen("2b", "nist", volume=3)

    def header(face: str, n: int) -> tuple[TrainingHeader, list[TrainingRow]]:
        h = TrainingHeader(
            corpus=face,
            schema_fingerprint="x",
            fields=(),
            prompt_version=1,
            instruction="",
            split_file=face,
            rows=n,
        )
        rows = [TrainingRow(doc_id=f"{face}-{i}", pages=("p",), target="{}") for i in range(n)]
        return h, rows

    counts = training_counts(config, [header("nist_1040_1", 3), header("nist_sch_d_1", 3)])
    assert counts.available == 6 and counts.documents == 3 and counts.pages == 3
    assert sum(counts.by_group.values()) == 3
    assert counts.over_limit == counts.by_group.get("nist_sch_d_1", 0)
