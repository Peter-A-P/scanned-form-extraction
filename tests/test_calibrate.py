"""The degradation calibration's two measures, on hand-built OCR pages."""

from __future__ import annotations

from legible.arms.ocr import OcrPage, Preprocess, Word
from legible.calibrate import field_recall, page_words
from legible.schema import Record


def page(texts: list[str]) -> OcrPage:
    words = tuple(
        Word(text=t, left=10 * i, top=10, width=5, height=5, conf=90.0, block=1, par=1, line=1)
        for i, t in enumerate(texts)
    )
    return OcrPage(
        page_path="p.png",
        page_sha256="0" * 64,
        width=100,
        height=100,
        tesseract="test",
        preprocess=Preprocess(),
        seconds=1.0,
        words=words,
    )


def test_field_words_are_counted_with_multiplicity_letters_and_digits_only() -> None:
    truth: Record = {"a": "5140  00", "b": "Berry K. Boyle", "c": None, "d": "00"}
    ocr = page(["Form", "5140", "00", "Berry", "K.", "Boyl"])
    # 5140, 00, 00, Berry, K, Boyle: four of the six found, one 00 only once.
    assert field_recall(truth, ocr) == 4 / 6
    assert field_recall({"a": None}, ocr) is None
    assert page_words(page(["K.", "a-b"])) == ["K", "a", "b"]
