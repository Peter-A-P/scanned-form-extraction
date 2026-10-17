"""NIST SD2's answer files, schemas and split, without the archive."""

from __future__ import annotations

import pytest

from legible.data.nist import (
    NistDoc,
    NistSplitRow,
    arm_sample,
    check_split,
    parse_fmt,
    split,
    split_rows,
    truth_of,
)
from legible.data.split import SplitLeak
from legible.schema.corpora import NIST_FACES, NIST_SCHEMAS, nist_name

FMT = (
    "sch_a\n"
    "SchA_L_H1 Berry K. Boyle\n"
    "SchA_L_H2 A57  00  3582\n"
    "SchA_1a 5140  00\n"
    "SchA_1b_V1 Duke W. Daws\n"
    "\ton, 41 Gilmer Lane\n"
    "SchA_2\n"
)


def test_a_wrapped_value_is_joined_and_empty_fields_are_none() -> None:
    face, values = parse_fmt(FMT)
    assert face == "sch_a"
    assert values["SchA_1b_V1"] == "Duke W. Dawson, 41 Gilmer Lane"
    truth = truth_of(face, values)
    assert truth[nist_name("SchA_L_H1")] == "Berry K. Boyle"
    assert truth[nist_name("SchA_1a")] == "5140  00"
    assert truth[nist_name("SchA_2")] is None


def test_every_face_has_a_schema_without_its_check_marks() -> None:
    assert {k.removeprefix("nist_") for k in NIST_SCHEMAS} == {f.lower() for f in NIST_FACES}
    names = NIST_SCHEMAS["nist_1040_1"].names()
    assert nist_name("1040_1_7") in names
    assert nist_name("1040_1_6a") not in names  # a check box


def docs(n: int) -> list[NistDoc]:
    return [
        NistDoc(doc_id=f"r{s:04d}_{k:02d}", submission=f"r{s:04d}", face="sch_a", truth={})
        for s in range(n)
        for k in range(3)
    ]


def test_no_submission_straddles_two_parts() -> None:
    parts = split([d.doc_id for d in docs(400)])
    by_sub: dict[str, set[str]] = {}
    for d, p in parts.items():
        by_sub.setdefault(d.split("_")[0], set()).add(p)
    assert all(len(p) == 1 for p in by_sub.values())
    assert {"train", "dev", "test"} == set(parts.values())


def test_the_samples_come_from_test_and_the_curve_from_the_sample() -> None:
    rows = split_rows(docs(900))
    check_split(rows)
    sample = [d for d, r in rows.items() if r.arm_test]
    assert len(sample) == 500 and sum(r.curve for r in rows.values()) == 300
    bad = dict(rows)
    some = next(d for d, r in rows.items() if r.part == "train")
    bad[some] = NistSplitRow(face="sch_a", part="train", arm_test=True)
    with pytest.raises(SplitLeak, match="test sample"):
        check_split(bad)
    with pytest.raises(ValueError, match="fewer than"):
        arm_sample(["r0000_00"])
