"""VRDU truth, splits and checksums, on records shaped like the real ones."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from legible.data.fetch import ChecksumMismatch, Pinned, digest, fetch, load_checksums, verify_file
from legible.data.split import SplitLeak
from legible.data.vrdu import (
    VrduSplit,
    check_split,
    headline_split_files,
    parse_record,
    parse_split_name,
)
from legible.grade import Outcome, grade_document
from legible.schema import SchemaDrift
from legible.schema.corpora import DEEPFORM


def entity(text: str, page: int = 0) -> list[Any]:
    return [text, [page, 0.1, 0.1, 0.2, 0.2], [[0, len(text)]]]


#: A page as VRDU stores it: dimension and tokens as Python reprs inside the JSON.
PAGE = {
    "dimension": "{'height': 1758, 'width': 2275}",
    "tokens": "[{'bbox': [0, 0.1, 0.1, 0.2, 0.2], 'text': 'KMSP'}]",
}

RECORD: dict[str, Any] = {
    "filename": "abc.pdf",
    "file_path": "ad-buy-form/main/pdfs/abc.pdf",
    "ocr": {"text": "KMSP 12/30/19 $5,625.00", "pages": [PAGE, PAGE]},
    "annotations": [
        ["property", [entity("KMSP\n"), entity("KMSP\n", 1)]],
        ["advertiser", [entity("Michael Bloomberg 2020, Inc\n"), entity("Bloomberg 2020\n", 1)]],
        ["gross_amount", [entity("$5,625.00\n")]],
        [
            ["channel", "program_desc", "program_start_date"],
            [[entity("9\n"), entity("Fox 9 AM News at 6am\n"), entity("02/17/20 ")]],
        ],
        [["sub_amount"], [[entity("$400.00\n")]]],
    ],
}


def test_record_becomes_truth_with_alternatives() -> None:
    doc = parse_record("deepform", RECORD)
    assert doc.pages == 2
    assert doc.frames[0].landscape and doc.frames[0].boxes == ((0.1, 0.1, 0.2, 0.2),)
    assert doc.truth["property"] == "KMSP"
    assert doc.truth["advertiser"] == "Michael Bloomberg 2020, Inc"
    assert doc.alternatives == {"advertiser": ["Bloomberg 2020"]}
    assert doc.truth["line_item"] == [
        {
            "channel": "9",
            "program_desc": "Fox 9 AM News at 6am",
            "program_start_date": "02/17/20",
            "program_end_date": None,
            "sub_amount": None,
        },
        {
            "channel": None,
            "program_desc": None,
            "program_start_date": None,
            "program_end_date": None,
            "sub_amount": "$400.00",
        },
    ]


def test_an_alternative_candidate_counts_as_right() -> None:
    doc = parse_record("deepform", RECORD)
    pred = dict(doc.truth, advertiser="Bloomberg 2020")
    g = grade_document(DEEPFORM, doc.doc_id, doc.truth, pred, alternatives=doc.alternatives)
    assert g.all_right
    g = grade_document(DEEPFORM, doc.doc_id, doc.truth, pred)
    assert [o.outcome for o in g.outcomes if o.path == "advertiser"] == [Outcome.WRONG_VALUE]


def test_unknown_annotation_is_refused() -> None:
    bad = dict(RECORD, annotations=[["station_manager", [entity("X")]]])
    with pytest.raises(SchemaDrift):
        parse_record("deepform", bad)
    with pytest.raises(SchemaDrift):
        parse_record("fara", RECORD)


def test_split_names_parse_as_the_evaluator_reads_them() -> None:
    assert parse_split_name(
        "fara", "FARA-lv3-unk_Short-Form-train_200-test_300-valid_100-SD_2.json"
    ) == (
        "unseen",
        "Short-Form",
        2,
        200,
    )
    assert parse_split_name(
        "deepform", "DeepForm-unk_template-train_200-test_159-valid_100-SD_0.json"
    ) == (
        "unseen",
        None,
        0,
        200,
    )
    assert parse_split_name(
        "deepform", "DeepForm-mixed_template-train_50-test_300-valid_100-SD_1.json"
    ) == (
        "mixed",
        None,
        1,
        50,
    )
    assert (
        parse_split_name("fara", "DeepForm-unk_template-train_200-test_159-valid_100-SD_0.json")
        is None
    )


def test_headline_files_are_train_200_at_three_seeds() -> None:
    fara = headline_split_files("fara", "unseen")
    assert len(fara) == 9  # three held-out templates at three seeds
    assert all("train_200" in p for p in fara)
    deepform = headline_split_files("deepform", "unseen")
    assert sorted(p.rsplit("-", 1)[1] for p in deepform) == ["SD_0.json", "SD_1.json", "SD_2.json"]
    assert len(headline_split_files("deepform", "mixed")) == 3


def split(train: tuple[str, ...], valid: tuple[str, ...], test: tuple[str, ...]) -> VrduSplit:
    return VrduSplit(
        corpus="deepform",
        file="x.json",
        level="unseen",
        template=None,
        seed=0,
        train=train,
        valid=valid,
        test=test,
    )


def test_split_overlap_and_unknown_documents_are_caught() -> None:
    known = {"a", "b", "c", "d"}
    check_split(split(("a",), ("b",), ("c", "d")), known)
    with pytest.raises(SplitLeak, match="train and test"):
        check_split(split(("a", "c"), ("b",), ("c",)), known)
    with pytest.raises(SplitLeak, match="not in the corpus"):
        check_split(split(("a",), ("b",), ("z",)), known)
    with pytest.raises(SplitLeak, match="twice"):
        check_split(split(("a", "a"), ("b",), ("c",)), known)


def test_git_blob_digest_matches_git() -> None:
    # `printf 'hello\n' | git hash-object --stdin`
    assert digest(b"hello\n", "git-blob") == "ce013625030ba8dba906f756967f9e9ca394464a"


def test_checksum_files_load() -> None:
    vrdu = load_checksums("vrdu")
    assert (
        vrdu.files["ad-buy-form/main/dataset.jsonl.gz"].digest
        == "224b1ea96e7d09e613855480745e342cf702744a"
    )
    assert sum(p.endswith(".pdf") for p in vrdu.files) == 1915 + 641
    assert len(load_checksums("cord").files) == 6


def test_a_tampered_file_is_refused(tmp_path: Path) -> None:
    data = b"hello\n"
    pinned = Pinned(path="x", size=len(data), digest=digest(data, "git-blob"))
    f = tmp_path / "x"
    f.write_bytes(data)
    verify_file(f, pinned, "git-blob")
    f.write_bytes(b"hellO\n")
    with pytest.raises(ChecksumMismatch):
        verify_file(f, pinned, "git-blob")


def test_fetch_trusts_nothing_on_disk_unverified(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("legible.data.fetch.ATTEMPTS", 1)
    data = b"hello\n"
    pinned = Pinned(path="x", size=len(data), digest=digest(data, "sha256"))
    dest = tmp_path / "x"
    dest.write_bytes(data)
    assert fetch("http://invalid.invalid/x", pinned, "sha256", dest) == dest  # verified, no network
    dest.write_bytes(b"corrupt")
    with pytest.raises(OSError):
        fetch("http://invalid.invalid/x", pinned, "sha256", dest)  # deleted, refetch fails
    assert not dest.exists()


def fara_split(train: tuple[str, ...], test: tuple[str, ...]) -> VrduSplit:
    return VrduSplit(
        corpus="fara",
        file="f.json",
        level="unseen",
        template="Amendment",
        seed=0,
        train=train,
        valid=(),
        test=test,
    )


def test_fara_unseen_templates_are_checked_from_file_names() -> None:
    from legible.data.vrdu import check_templates, fara_template

    assert fara_template("19410222_DLA Piper US LLP_Amendment_Amendment.pdf") == "Amendment"
    assert fara_template("2001_X, Inc._Dissemination Report.pdf") == "Dissemination Report"
    check_templates(fara_split(("a_Short-Form.pdf",), ("b_Amendment.pdf",)))
    with pytest.raises(SplitLeak, match="shares templates"):
        check_templates(fara_split(("a_Amendment.pdf",), ("b_Amendment.pdf",)))
    with pytest.raises(SplitLeak, match="not Amendment"):
        check_templates(fara_split(("a_Short-Form.pdf",), ("b_Dissemination Report.pdf",)))


def test_a_sideways_scan_is_turned_to_the_benchmarks_frame() -> None:
    """A portrait page whose text runs up the page, where the benchmark read it landscape
    with a word near the top left: turned so the word's box has ink."""
    import io

    from PIL import Image, ImageDraw

    from legible.data.render import Frame, orient

    landscape = Image.new("L", (300, 200), 255)
    ImageDraw.Draw(landscape).rectangle((20, 20, 80, 40), fill=0)
    portrait = landscape.rotate(270, expand=True)  # what the PDF holds
    buf = io.BytesIO()
    portrait.save(buf, format="PNG")
    frame = Frame(landscape=True, boxes=((20 / 300, 20 / 200, 80 / 300, 40 / 200),))
    data, rotation = orient(buf.getvalue(), frame)
    assert rotation == 90
    with Image.open(io.BytesIO(data)) as img:
        assert img.size == (300, 200) and img.getpixel((50, 30)) == 0
        assert img.tobytes() == landscape.tobytes()
    same, none = orient(buf.getvalue(), Frame(landscape=False, boxes=frame.boxes))
    assert none == 0 and same == buf.getvalue()
