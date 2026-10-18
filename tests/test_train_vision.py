"""Arm B's example building, without the GPU stack: the loss on the answer alone, the
adapters' targets, and a run id that follows the recipe."""

from __future__ import annotations

import re

import pytest

from legible.train.recipe import TARGET_MODULES, chosen
from legible.train.vision import IGNORE, loss_tokens, mask_prompt, messages


def test_a_document_is_its_pages_then_the_instruction_then_the_answer() -> None:
    chat = messages("Read it.", 2, '{"a": 1}')
    assert [c["type"] for c in chat[0]["content"]] == ["image", "image", "text"]
    assert chat[1]["role"] == "assistant" and chat[1]["content"][0]["text"] == '{"a": 1}'
    assert len(messages("Read it.", 1, None)) == 1


def test_the_loss_falls_on_the_answer_alone() -> None:
    labels = mask_prompt([5, 6, 7, 8, 9, 0], 3, pad_id=0)
    assert labels == [IGNORE, IGNORE, IGNORE, 8, 9, IGNORE]
    assert loss_tokens(labels) == (2, 6)
    with pytest.raises(RuntimeError, match="falls on 0"):
        loss_tokens(mask_prompt([1, 2], 2, None))


def test_adapters_go_on_the_language_layers_and_projector_only() -> None:
    target = re.compile(TARGET_MODULES)
    assert target.match("model.language_model.layers.3.self_attn.q_proj")
    assert target.match("model.language_model.layers.3.mlp.down_proj")
    assert target.match("model.embed_vision.embedding_projection")
    assert not target.match("model.vision_tower.encoder.layers.0.self_attn.q_proj")
    assert not target.match("model.audio_tower.layers.0.q_proj")


def test_the_run_id_changes_with_the_recipe() -> None:
    a = chosen("2b", "fara-unseen-amendment-s0")
    assert (a.rank, a.alpha, a.learning_rate) == (64, 128, 1e-4)
    assert chosen("4b", "x").rank == 16
    assert a.run_id == chosen("2b", "fara-unseen-amendment-s0").run_id
    assert a.run_id != chosen("2b", "fara-unseen-amendment-s0", visual_tokens=560).run_id
