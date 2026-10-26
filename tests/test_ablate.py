"""The ablation list: each run is one change to a measured recipe, and none collides with it."""

from __future__ import annotations

from pathlib import Path

from legible.report import ARMS, TABLE_SETS, Arm, arm_dirs
from legible.train.ablate import HEADLINE_SETS, MULTI, ablations, find
from legible.train.recipe import Size, chosen


def test_the_headline_run_ids_are_unchanged() -> None:
    # The stored runs are found by these ids; adding the ablations must not move them.
    assert chosen("2b", "nist").run_id == "2b-nist-v1120-s0-a72f03d21f"
    assert chosen("2b", "cord").run_id == "2b-cord-v1120-s0-f83ed25a5c"


def test_every_ablation_is_new_and_distinct() -> None:
    runs = ablations()
    ids = [a.config.run_id for a in runs]
    assert len(ids) == len(set(ids)) == 11
    sizes: tuple[Size, ...] = ("2b", "4b")
    headline = {chosen(s, ds).run_id for s in sizes for ds in HEADLINE_SETS}
    assert not headline & set(ids)


def test_each_changes_one_thing() -> None:
    for a in ablations():
        c = a.config
        base = chosen("2b", c.dataset) if c.dataset != MULTI else None
        assert c.size == "2b" and c.seed == 0
        if a.kind == "visual-tokens":
            assert base is not None and c.model_copy(update={"visual_tokens": 1120}) == base
        elif a.kind == "volume":
            assert base is not None and base.volume in {None, 800}
            assert c.volume in {400, 200}
        else:
            # NIST's prompts need the longer sequence wherever its faces are trained.
            assert c.max_seq_len == 16_384 and c.volume is None


def test_only_the_visual_token_runs_read_the_bad_scans() -> None:
    kinds = {a.kind: a.level0_only for a in ablations()}
    assert kinds == {"visual-tokens": False, "volume": True, "multi-corpus": True}


def test_find() -> None:
    first = ablations()[0]
    assert find(first.config.run_id) == first
    assert find(chosen("2b", "cord").run_id) is None


def test_an_ablation_arm_reads_its_own_runs(tmp_path: Path) -> None:
    e2b = next(a for a in ARMS if a.arm == "b" and a.size == "2b")
    small = Arm("x", "b", None, size="2b", changes=(("visual_tokens", 560),))
    multi = Arm("y", "b", None, size="2b", dataset=MULTI)
    for tbl in ("cord", "fara-unseen"):
        assert len(arm_dirs(tmp_path, small, ["c"], "test", 0, tbl)) == len(TABLE_SETS[tbl])
        assert arm_dirs(tmp_path, small, ["c"], "test", 0, tbl) != arm_dirs(
            tmp_path, e2b, ["c"], "test", 0, tbl
        )
    (only,) = arm_dirs(tmp_path, multi, ["fara"], "test", 0, "fara-mixed")
    assert only.parts[-5] == chosen("2b", MULTI).run_id
