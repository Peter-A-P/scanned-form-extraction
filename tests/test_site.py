"""The demo site's build: registration forms never shown, the grader's flags carried as the
grader set them, boxes placed where the degraded page put the field, and JSON a browser
parses."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from PIL import Image, ImageFilter

from legible.data.render import PageEntry
from legible.degrade import degrade, skew_angle
from legible.grade import grade_document
from legible.report import ARMS, ReviewTable, Truth
from legible.review import ReviewResult, Threshold
from legible.schema import Record
from legible.site import build
from legible.stats import Interval
from tests.schemas import ORDER

TRUTH: Record = {
    "advertiser": "Smith for Senate",
    "agency": "Blue Ridge Media",
    "contract_num": "12345-A",
    "flight_from": "03/15/2021",
    "gross_amount": "$12,500.00",
    "product": None,
    "line_item": [
        {"program": "Morning News", "start": "03/15/2021", "amount": "$1,000.00"},
        {"program": "Evening News", "start": "03/16/2021", "amount": "$2,500.00"},
    ],
}
PAGE = "Smith for Senate Blue Ridge Media 12345-A 03/15/2021 Morning News Evening News"
#: Two of the boxes a loader gives: a scalar, and a line item's field by its truth index.
BOXES: dict[str, build.Box] = {
    "advertiser": (0, 0.1, 0.1, 0.4, 0.15),
    "line_item[1].amount": (0, 0.6, 0.5, 0.8, 0.55),
}
OUTPUT: dict[str, Any] = {
    "advertiser": "Smith for Senate",
    "agency": "Blue Ridge",
    "contract_num": "12345-A",
    "flight_from": "03/15/2021",
    "gross_amount": "$12,000.00",
    "product": "Political ad",
    "line_item": [
        {"program": "Evening News", "start": "03/16/2021", "amount": "$2,500.00"},
        {"program": "Morning News", "start": "03/15/2021", "amount": "$1,900.00"},
        {"program": "Late Show", "start": "03/17/2021", "amount": "$9,000.00"},
    ],
}


def entry(corpus: str, doc: str = "d1", width: int = 400, height: int = 600) -> PageEntry:
    return PageEntry(
        corpus=corpus,
        doc_id=doc,
        page=0,
        path=f"{corpus}/{doc}/p00.png",
        width=width,
        height=height,
        sha256="0" * 64,
    )


def truth() -> Truth:
    return Truth(ORDER, TRUTH, {}, PAGE, 1)


# --- Registration forms are never shown -----------------------------------------------------


@pytest.mark.parametrize("corpus", ["fara", "FARA", "somethingelse"])
def test_an_unshown_corpus_is_refused(corpus: str) -> None:
    with pytest.raises(build.RegistrationImage):
        build.refuse_unshown(corpus)


def test_a_registration_page_image_is_refused_before_it_is_read(tmp_path: Path) -> None:
    # The page does not exist: the refusal must come before any attempt to open it.
    with pytest.raises(build.RegistrationImage):
        build.page_image(tmp_path, entry("fara"), 0)
    with pytest.raises(build.RegistrationImage):
        build.write_images(tmp_path, [entry("fara")], (0,), tmp_path / "out")
    assert not list((tmp_path / "out").rglob("*.jpg"))


def test_a_registration_page_record_is_refused() -> None:
    with pytest.raises(build.RegistrationImage):
        build.page_record(
            corpus="fara",
            doc_id="d1",
            entries=[entry("fara")],
            truth=truth(),
            boxes={},
            levels=(0,),
            reads={0: {}},
            images={0: []},
        )


def test_the_finished_site_is_checked_for_registration_images(tmp_path: Path) -> None:
    (tmp_path / "img").mkdir()
    (tmp_path / "img" / "nist-r0000_00-p00-l0.jpg").write_bytes(b"x")
    build.check_output(tmp_path)
    (tmp_path / "img" / "fara-anything-p00-l0.jpg").write_bytes(b"x")
    with pytest.raises(build.RegistrationImage):
        build.check_output(tmp_path)


def test_the_finished_site_is_checked_for_registration_page_records(tmp_path: Path) -> None:
    build.dump(tmp_path / "data" / "pages" / "cord-test-0001.json", {"corpus": "cord"})
    build.check_output(tmp_path)
    build.dump(tmp_path / "data" / "pages" / "x.json", {"corpus": "fara"})
    with pytest.raises(build.RegistrationImage):
        build.check_output(tmp_path)


def test_shown_pages_are_written_small(tmp_path: Path) -> None:
    e = entry("nist", width=2560, height=3300)
    (tmp_path / "pages" / e.path).parent.mkdir(parents=True)
    Image.new("1", (2560, 3300), 1).save(tmp_path / "pages" / e.path)
    names = build.write_images(tmp_path, [e], (0, 2), tmp_path / "out")
    assert names == {0: ["img/nist-d1-p00-l0.jpg"], 2: ["img/nist-d1-p00-l2.jpg"]}
    with Image.open(tmp_path / "out" / names[2][0]) as img:
        assert img.width == build.MAX_WIDTH
    # A degraded copy is made in memory; nothing is written under the data root.
    assert not (tmp_path / "degraded").exists()


# --- The grader's flags, as the grader set them ---------------------------------------------


def test_the_page_record_carries_the_graders_outcomes() -> None:
    label = ARMS[0].label
    rec = build.page_record(
        corpus="deepform",
        doc_id="d1",
        entries=[entry("deepform")],
        truth=truth(),
        boxes=BOXES,
        levels=(0,),
        reads={0: {label: {"d1": OUTPUT}}},
        images={0: ["img/deepform-d1-p00-l0.jpg"]},
    )
    fields = rec["reads"]["0"][label]["fields"]
    g = grade_document(ORDER, "d1", TRUTH, OUTPUT, page_text=PAGE)
    assert [f["correct"] for f in fields] == [o.correct for o in g.outcomes]
    assert [f["outcome"] for f in fields] == [o.outcome.value for o in g.outcomes]
    assert [(f["read"], f["truth"]) for f in fields] == [(o.predicted, o.truth) for o in g.outcomes]
    assert rec["reads"]["0"][label]["correct"] == g.correct
    # Some right, some wrong, so the flags are not all one way by accident.
    assert {f["correct"] for f in fields} == {True, False}
    by_key = {f["key"]: f for f in fields if f["key"]}
    # The rows come back in another order; each field is keyed by the truth item it was
    # paired with, so the second truth row's amount (read off the first predicted row) is
    # placed at that row's box.
    assert by_key["line_item[1].amount"]["item"] == 1
    assert by_key["line_item[1].amount"]["correct"] is True
    assert by_key["line_item[0].amount"]["correct"] is False
    assert by_key["advertiser"]["correct"] is True
    # The invented third row and the filled blank product carry no truth, so no place.
    extra = [f for f in fields if f["truth"] is None]
    assert extra and all(f["key"] is None for f in extra)
    assert rec["boxes"]["0"] == {k: v for k, v in BOXES.items()}


def test_an_arm_that_has_not_read_the_page_is_not_graded() -> None:
    rec = build.page_record(
        corpus="cord",
        doc_id="d1",
        entries=[entry("cord")],
        truth=truth(),
        boxes={},
        levels=(0,),
        reads={0: {ARMS[0].label: {"other": OUTPUT}, ARMS[1].label: None}},
        images={0: ["img/cord-d1-p00-l0.jpg"]},
    )
    assert all(v is None for v in rec["reads"]["0"].values())


def test_a_failed_call_is_graded_as_the_grader_grades_it() -> None:
    label = ARMS[0].label
    rec = build.page_record(
        corpus="cord",
        doc_id="d1",
        entries=[entry("cord")],
        truth=truth(),
        boxes={},
        levels=(0,),
        reads={0: {label: {"d1": None}}},
        images={0: ["img/cord-d1-p00-l0.jpg"]},
    )
    read = rec["reads"]["0"][label]
    assert read["unparsed"] is True and read["correct"] == 0 and read["scored"] > 0


# --- Boxes on the degraded page -------------------------------------------------------------


def _dark_centre(img: Image.Image) -> tuple[float, float]:
    """The centre of the one dark block, with the scattered noise blurred away."""
    smooth = np.asarray(img.convert("L").filter(ImageFilter.GaussianBlur(radius=4)), dtype=float)
    ys, xs = np.nonzero(smooth < 100)
    return float(xs.mean()), float(ys.mean())


def test_a_box_follows_the_skew_degrade_applies() -> None:
    w, h = 800, 1000
    page_id = next(
        f"nist/r{i:04d}_00/p00.png"
        for i in range(100)
        if abs(skew_angle(f"nist/r{i:04d}_00/p00.png", 4)) > 2.0
    )
    pixels = np.full((h, w), 255, dtype=np.uint8)
    x1, y1, x2, y2 = 60, 80, 120, 140
    pixels[y1:y2, x1:x2] = 0
    out = degrade(Image.fromarray(pixels), page_id, 4)
    box = build.turn_box((0, x1 / w, y1 / h, x2 / w, y2 / h), skew_angle(page_id, 4), w, h)
    want = ((box[1] + box[3]) / 2 * w, (box[2] + box[4]) / 2 * h)
    got = _dark_centre(out)
    unturned = ((x1 + x2) / 2, (y1 + y2) / 2)
    assert math.dist(got, want) < 4
    # The skew moved the field by more than the tolerance, so the test can fail.
    assert math.dist(got, unturned) > 10


def test_a_level_without_skew_leaves_the_box_alone() -> None:
    assert skew_angle("p", 0) == 0.0
    assert build.turn_box((0, 0.1, 0.2, 0.3, 0.4), 0.0, 100, 100) == (0, 0.1, 0.2, 0.3, 0.4)


def test_box_keys_follow_the_truth_item() -> None:
    g = grade_document(ORDER, "d1", TRUTH, OUTPUT, page_text=PAGE)
    keys = {build.box_key(o) for o in g.outcomes}
    assert {"advertiser", "line_item[0].program", "line_item[1].amount"} <= keys


# --- Choice of pages and the JSON -----------------------------------------------------------


def test_pages_are_chosen_from_the_set_alone() -> None:
    ids = [f"test-{i:04d}" for i in range(100)]
    first = build.choose(ids)
    assert first == build.choose(list(reversed(ids))) == sorted(first)
    assert len(first) == build.PER_CORPUS
    assert build.choose(ids[:3]) == ids[:3]


def test_json_has_no_nan() -> None:
    nan = Interval(point=math.nan, low=math.nan, high=math.nan, n=0)
    assert build.interval(nan) is None
    result = ReviewResult(
        threshold=Threshold(
            target=0.99, value=0.5, dev_accepted_accuracy=1.0, dev_review_rate=0.99
        ),
        review_rate=Interval(point=1.0, low=1.0, high=1.0, n=10),
        accepted_accuracy=nan,
    )
    table = ReviewTable("t", "n", [("CORD", result), ("NIST", None)], "miss")
    out = build.review_json(table)
    assert out["rows"][0]["accepted_text"] == "none accepted on test"
    assert out["rows"][1]["sent_text"] == "not yet measured"
    json.loads(json.dumps(out, allow_nan=False))
    with pytest.raises(ValueError):
        build.dump(Path("unused.json"), {"x": math.nan})


# --- The front page's story -----------------------------------------------------------------


def test_the_architecture_diagrams_are_the_one_exception_to_the_image_check(tmp_path: Path) -> None:
    build.copy_assets(tmp_path)
    for name in build.DIAGRAMS:
        assert (tmp_path / "architecture" / name).is_file()
    build.check_output(tmp_path)
    # The exception is by name and place: the same file anywhere else is refused.
    (tmp_path / "img").mkdir()
    (tmp_path / "img" / "system.svg").write_text("<svg/>", encoding="utf-8")
    with pytest.raises(build.RegistrationImage):
        build.check_output(tmp_path)


def test_every_asset_the_pages_load_is_copied(tmp_path: Path) -> None:
    import re

    build.copy_assets(tmp_path)
    for page in ("index.html", "architecture.html"):
        html = (tmp_path / page).read_text(encoding="utf-8")
        for ref in re.findall(r'(?:src|href)="([^":#]+)"', html):
            assert (tmp_path / ref).is_file(), f"{page} loads {ref}, which the build does not copy"
    css = (tmp_path / "style.css").read_text(encoding="utf-8")
    for ref in re.findall(r"url\(([^)]+)\)", css):
        assert (tmp_path / ref).is_file()


def test_the_pages_load_nothing_from_another_origin_and_nothing_inline() -> None:
    import re

    for page in ("index.html", "architecture.html"):
        html = (build.SOURCE / page).read_text(encoding="utf-8")
        # The policy allows no inline style or script, and no origin but the site's own.
        assert "<style" not in html and " style=" not in html
        assert not re.search(r"<script(?![^>]*\bsrc=)", html)
        for tag in ("script", "link", "img"):
            for url in re.findall(rf'<{tag}\b[^>]*\b(?:src|href)="([^"]+)"', html):
                assert "://" not in url, f"{page} loads {url}"


def test_arms_are_named_without_their_letter_and_input() -> None:
    assert build.arm_short("A, Claude Sonnet 5.5 on the image") == "Claude Sonnet 5.5"
    assert (
        build.arm_short("D, Claude Sonnet 5.5 on the OCR text") == "Claude Sonnet 5.5 on OCR text"
    )
    assert build.arm_short("F, Azure Document Intelligence") == "Azure Document Intelligence"
    assert {build.arm_json(a)["kind"] for a in ARMS} == set(build.ARM_KIND.values())


def test_only_the_registration_form_adapters_have_no_public_link() -> None:
    assert build.hub_url("2b-fara-unseen-amendment-s0-v1120-s0-d12371af07") is None
    assert build.hub_url("4b-cord-v1120-s0-7695d3c79b") == (
        "https://huggingface.co/Peter-A-P/legible-4b-cord-v1120-s0-7695d3c79b"
    )


def _record(rows: list[int], steps: int, left_out: int = 0) -> dict[str, Any]:
    return {
        "run_id": "2b-nist-x",
        "config": {
            "size": "2b", "dataset": "nist", "rank": 64, "alpha": 128, "learning_rate": 1e-4,
            "epochs": 1, "visual_tokens": 1120, "max_seq_len": 12288, "grad_accum": 8,
        },
        "datasets": [{"rows": n} for n in rows],
        "started_at": "2026-10-18T10:00:00Z",
        "finished_at": "2026-10-18T10:30:00Z",
        "steps": steps,
        "seconds_per_step": 18.0,
        "train_loss": 0.1,
        "left_out": left_out,
    }  # fmt: skip


def test_the_documents_trained_on_are_what_the_steps_saw() -> None:
    # NIST's run reads the first 800 of a 3,850-face set: the steps decide, not the set.
    (big,) = build.training_json([_record([620, 3230], steps=97)])
    assert big["documents"] == 776 and big["minutes"] == pytest.approx(30.0)
    # A set read whole, less the documents left out for length.
    (small,) = build.training_json([_record([200], steps=25, left_out=2)])
    assert small["documents"] == 198


def test_pages_read_counts_answered_pages_over_every_run(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    a = runs / "arm-a" / "quality" / "p1" / "level0" / "deepform" / "test"
    a.mkdir(parents=True)
    (a / "reads.jsonl").write_text(
        '{"doc_id":"d1","text":"{}"}\n{"doc_id":"d2","text":null}\n', encoding="utf-8"
    )
    e = runs / "arm-e" / "level0" / "cord"
    e.mkdir(parents=True)
    (e / "test.jsonl").write_text('{"doc_id":"c1","output":{}}\n', encoding="utf-8")
    old = runs / "archive" / "arm-a" / "deepform"
    old.mkdir(parents=True)
    (old / "reads.jsonl").write_text('{"doc_id":"d1","text":"{}"}\n', encoding="utf-8")
    pages = {("deepform", "d1"): 3, ("deepform", "d2"): 2, ("cord", "c1"): 1}
    out = build.pages_read(runs, pages)
    # d1's three pages and c1's one; the failed read and the archived run are not counted.
    assert out == {"pages": 4, "documents": 2, "by_arm": {"a": 3, "e": 1}}


# --- The calculator's JavaScript ------------------------------------------------------------

NODE = __import__("shutil").which("node")

RUNNER = """
const B = require(process.argv[1]);
const cases = JSON.parse(require("fs").readFileSync(0, "utf8"));
const out = cases.map((c) => {
  const p = B.breakEven(c.inputs, c.utilisation);
  return { volume: p.volumePerMonth, gpus: p.gpus, cost: p.monthlyCost, perPage: p.selfHostedUsdPerCall };
});
process.stdout.write(JSON.stringify(out));
"""


@pytest.mark.skipif(NODE is None, reason="Node is not installed")
def test_the_calculator_gives_the_pythons_break_even() -> None:
    import datetime as dt
    import subprocess

    from legible.bench.breakeven import BreakEvenInputs, break_even
    from legible.bench.cost import GpuPrice, PriceKind

    grid = [
        (rate, pps, api, fixed, u)
        for rate in (0.27, 0.5, 2.5)
        for pps in (0.05, 0.37, 7.86)
        for api in (0.00018, 0.0016, 0.03)
        for fixed in (0.0, 900.0)
        for u in (0.1, 0.5, 0.9)
    ]
    cases = [
        {
            "inputs": {"usdPerHour": rate, "requestsPerSecond": pps, "apiUsdPerCall": api,
                       "fixedUsdPerMonth": fixed, "hoursPerMonth": 730.5, "secondsPerHour": 3600.0},
            "utilisation": u,
        }
        for rate, pps, api, fixed, u in grid
    ]  # fmt: skip
    assert NODE is not None
    result = subprocess.run(
        [NODE, "-e", RUNNER, str(build.SOURCE / "breakeven.js")],
        input=json.dumps(cases),
        capture_output=True,
        text=True,
        check=True,
    )
    kinds = set()
    for (rate, pps, api, fixed, u), js in zip(grid, json.loads(result.stdout), strict=True):
        price = GpuPrice(
            gpu="RTX 3090", provider="RunPod", kind=PriceKind.ON_DEMAND, usd_per_hour=rate,
            checked=dt.date(2026, 10, 23), source="test",
        )  # fmt: skip
        py = break_even(
            BreakEvenInputs(
                price=price, pages_per_second=pps, api_usd_per_page=api, fixed_usd_per_month=fixed
            ),
            u,
        )
        assert js["perPage"] == pytest.approx(py.self_hosted_usd_per_page, rel=1e-12)
        assert js["gpus"] == py.gpus_at_break_even
        if py.volume_per_month is None:
            assert js["volume"] is None
            kinds.add("never")
        else:
            assert js["volume"] == pytest.approx(py.volume_per_month, rel=1e-12)
            assert js["cost"] == pytest.approx(py.monthly_cost_at_break_even, rel=1e-12)
            kinds.add("one card" if py.gpus_at_break_even == 1 else "more cards")
    # The grid has to reach every branch, or agreeing on it proves less than it says.
    assert kinds == {"never", "one card", "more cards"}
