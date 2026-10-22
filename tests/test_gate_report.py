"""Reading the gate's decisions back for the README, without re-deciding anything."""

from __future__ import annotations

from pathlib import Path

from legible.report import gate_table, read_gate

DECISION = """## Gate: {verdict}

Spec `legible-cord-test` (85c4886cf43e965c).

Baseline `A, Gemini 3.8 Flash on the image`, candidate `B, Gemma 4 E4B fine-tuned on the image`.

| Suite | Paired items | Baseline | Candidate | Difference | Margin | Holm p | Verdict |
|---|---:|---|---|---|---:|---:|---|
| total_price | 99 | 93.9% (88.9 to 98.0) | 92.9% (87.9 to 97.0) | {a} | -3% | {p} | {v1} |
| tax_price | 43 | 95.3% (88.4 to 100.0) | 81.4% (69.8 to 93.0) | {b} | -3% | {p} | {v2} |
"""


def write(tmp: Path, **kw: str) -> Path:
    d = tmp / "legible-cord-test-4b-vs-best"
    d.mkdir()
    (d / "decision.txt").write_text(DECISION.format(**kw), encoding="utf-8")
    return d / "decision.txt"


def test_a_pass_with_nothing_decided_is_not_reported_as_a_pass(tmp_path: Path) -> None:
    f = write(
        tmp_path, verdict="PASS", a="-1.0%", b="-14.0%", p="not decided", v1="warn", v2="warn"
    )
    r = read_gate(f)
    assert r.verdict == "PASS" and r.counts == {"warn": 2} and r.blocks == []
    row = gate_table([r], {"legible-cord-test": "CORD"})[2]
    assert "no decision" in row and "**pass**" not in row


def test_blocks_are_listed_worst_first(tmp_path: Path) -> None:
    f = write(
        tmp_path,
        verdict="BLOCK",
        a="-1.0% (-8.1 to +5.1)",
        b="-14.0% (-23.3 to -2.3)",
        p="1.000",
        v1="block",
        v2="block",
    )
    r = read_gate(f)
    assert [s for s, _ in r.blocks] == ["tax_price", "total_price"]
    assert r.baseline == "A, Gemini 3.8 Flash on the image"
    assert "**block**" in gate_table([r], {"legible-cord-test": "CORD"})[2]
