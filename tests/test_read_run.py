"""Arm D's runner: requests from stored OCR, a run that refuses to change mid-way, dev first."""

from __future__ import annotations

from pathlib import Path

import pytest

from legible.arms.frontier import Read, RunDir
from legible.arms.ocr import OcrPage, Preprocess, Word
from legible.arms.ocr_run import stored
from legible.arms.read_run import (
    MAX_TOKENS,
    DevFirst,
    RunMismatch,
    RunSpec,
    open_run,
    outputs,
    prompt_for,
    requests_for,
    require_dev,
    run_dir,
)
from legible.data.render import PageEntry

SPEC = RunSpec(
    arm="d",
    corpus="cord",
    part="dev",
    level=0,
    route="quality",
    vendor="anthropic",
    model="claude-sonnet-5-5",
    prompt_version=1,
    max_tokens=MAX_TOKENS["cord"],
)


def entry(doc: str, page: int) -> PageEntry:
    return PageEntry(
        corpus="cord",
        doc_id=doc,
        page=page,
        path=f"cord/{doc}/p{page:02d}.png",
        width=1000,
        height=1000,
        sha256="0" * 64,
    )


def store(root: Path, e: PageEntry, text: str) -> None:
    words = tuple(
        Word(text=t, left=100 * i, top=100, width=50, height=20, conf=90.0, block=1, par=1, line=1)
        for i, t in enumerate(text.split())
    )
    page = OcrPage(
        page_path=e.path,
        page_sha256=e.sha256,
        width=e.width,
        height=e.height,
        tesseract="test",
        preprocess=Preprocess(),
        seconds=1.0,
        words=words,
    )
    path = stored(root, 0, e.path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(page.model_dump_json(), encoding="utf-8")


def read(doc: str, text: str | None) -> Read:
    return Read(
        doc_id=doc,
        text=text,
        status="200",
        cost_usd=0.01,
        input_tokens=1,
        output_tokens=1,
        latency_ms=1.0,
        ledger_id=1,
        model_returned="m",
    )


def test_requests_carry_each_documents_pages_in_order(tmp_path: Path) -> None:
    pages = {"a": [entry("a", 1), entry("a", 0)]}
    store(tmp_path, pages["a"][0], "second page")
    store(tmp_path, pages["a"][1], "TOTAL 60.000")
    prompt = prompt_for("cord", 1)
    r = requests_for(tmp_path, SPEC, prompt, ["a"], pages)["a"]
    content = r.messages[0]["content"]
    assert content[0]["text"].startswith("--- page 1 ---\nTOTAL")
    assert "--- page 2 ---" in content[0]["text"]
    assert content[-1]["text"] == prompt.text and "OCR text" in prompt.text
    assert r.model == "anthropic/claude-sonnet-5-5" and r.max_tokens == MAX_TOKENS["cord"]


def test_a_page_without_ocr_stops_the_run_before_any_request(tmp_path: Path) -> None:
    pages = {"a": [entry("a", 0)], "b": [entry("b", 0)]}
    store(tmp_path, pages["a"][0], "x")
    with pytest.raises(FileNotFoundError, match="1 pages have no OCR"):
        requests_for(tmp_path, SPEC, prompt_for("cord", 1), ["a", "b"], pages)


def test_a_run_resumes_only_as_it_was_begun(tmp_path: Path) -> None:
    path = run_dir(tmp_path, SPEC)
    open_run(path, SPEC, prompt_for("cord", 1))
    open_run(path, SPEC, prompt_for("cord", 1))
    with pytest.raises(RunMismatch, match="begun as"):
        open_run(path, SPEC.model_copy(update={"model": "claude-haiku-5-5"}), prompt_for("cord", 1))
    with pytest.raises(RunMismatch, match="prompt has changed"):
        open_run(path, SPEC, prompt_for("cord", 1).model_copy(update={"text": "other words"}))


def test_test_waits_for_a_finished_dev_run_with_the_same_prompt(tmp_path: Path) -> None:
    prompt = prompt_for("cord", 1)
    test = SPEC.model_copy(update={"part": "test"})
    with pytest.raises(DevFirst, match="no finished dev run"):
        require_dev(tmp_path, test, ["d1", "d2"], prompt)
    dev = open_run(run_dir(tmp_path, SPEC), SPEC, prompt)
    dev.add_reads([read("d1", "{}")])
    with pytest.raises(DevFirst, match="no finished dev run"):
        require_dev(tmp_path, test, ["d1", "d2"], prompt)
    dev.add_reads([read("d2", "{}")])
    require_dev(tmp_path, test, ["d1", "d2"], prompt)
    with pytest.raises(DevFirst, match="prompt differs"):
        require_dev(tmp_path, test, ["d1", "d2"], prompt.model_copy(update={"text": "tuned"}))


def test_outputs_parse_each_reply_or_say_none(tmp_path: Path) -> None:
    run = RunDir(tmp_path / "r")
    run.add_reads(
        [read("a", '```json\n{"total_price": "60.000"}\n```'), read("b", "sorry"), read("c", None)]
    )
    assert outputs(tmp_path / "r") == {"a": {"total_price": "60.000"}, "b": None, "c": None}


def test_arm_a_sends_each_page_image_and_the_image_prompt(tmp_path: Path) -> None:
    import io

    from PIL import Image

    from legible.arms.read_run import chunks, request_bytes

    pages = {d: [entry(d, 0), entry(d, 1)] for d in ("a", "b", "c")}
    for es in pages.values():
        for e in es:
            out = io.BytesIO()
            Image.new("L", (40, 40), 255).save(out, format="PNG")
            path = tmp_path / "pages" / e.path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(out.getvalue())
    spec = SPEC.model_copy(update={"arm": "a"})
    prompt = prompt_for("cord", 1, "a")
    assert "page images" in prompt.text
    r = requests_for(tmp_path, spec, prompt, ["a"], pages)["a"]
    content = r.messages[0]["content"]
    assert [b["type"] for b in content] == ["image", "image", "text"]
    one = request_bytes(r)
    batches = list(chunks(tmp_path, spec, prompt, ["a", "b", "c"], pages, max_bytes=int(one * 2.5)))
    assert [list(b) for b in batches] == [["a", "b"], ["c"]]


def test_an_arm_d_run_does_not_resume_as_arm_a(tmp_path: Path) -> None:
    path = run_dir(tmp_path, SPEC)
    open_run(path, SPEC, prompt_for("cord", 1))
    with pytest.raises(RunMismatch, match="begun as"):
        open_run(path, SPEC.model_copy(update={"arm": "a"}), prompt_for("cord", 1))


def test_nist_budget_grows_past_dev_for_the_frontier_only() -> None:
    from legible.arms.read_run import max_tokens_for

    assert max_tokens_for("nist_1040_1", "anthropic", "dev") == 3072
    assert max_tokens_for("nist_1040_1", "anthropic", "test") == 8192
    assert max_tokens_for("nist_1040_1", "openai", "curve") == 8192
    assert max_tokens_for("nist_1040_1", "google", "test") == 8192 + 4096
    assert max_tokens_for("nist_1040_1", "selfhosted", "test") == 3072
    assert max_tokens_for("fara", "anthropic", "test") == MAX_TOKENS["fara"]
