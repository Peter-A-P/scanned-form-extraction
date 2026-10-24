"""Arm F: Azure AI Document Intelligence, the managed document service a buyer is quoted first.

PLAN.md 2.2, added 2026-10-24. Two of the service's models are measured:

- **The prebuilt receipt model on CORD.** No training; its fields are mapped onto CORD's
  (`RECEIPT_FIELDS`), by name, with nothing learned from CORD's answers.
- **A custom neural model per training split** on FARA and DeepForm, and per NIST face. Each is
  trained on the training documents of the split arm B's fine-tune learned (at most
  `TRAIN_DOCS` of them, the first by id), so a FARA model has never seen the template it is
  tested on, exactly as the fine-tune has not.

**What the service is sent.** A document's pages as one multi-page TIFF, losslessly
compressed, at the resolution they were rendered (or degraded) at. The vision models are sent
each page scaled to their own limit; the service takes up to 10,000 pixels a side, so it gets
the page whole, which is what a buyer would send it.

**How a custom model is taught.** The service learns fields from labels drawn on its own OCR:
each training document is read once by the layout model (`prebuilt-layout`, billed per page
through the gateway), and each field of the document's truth is labelled on the words of that
reading whose text it is (`find_words`): the field's tokens, in order, consecutive on one page,
compared case-folded with surrounding punctuation stripped. A value the page's words do not
spell out is left unlabelled on that document rather than guessed at, and how many were found
is recorded (`LabelCoverage`). A table field (DeepForm's line items) is labelled row by row as
`line_item/<row>/<column>`, the service's own convention.

**What comes back.** The service's fields are read back into the corpus schema
(`to_record`): a field's `content`, the text as printed, which is what the corpus answers
transcribe, else its typed value; a table's rows into the schema's list. A field the model did
not return is null, as any arm's blank is.
"""

from __future__ import annotations

import base64
import io
import json
import re
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from boundary import ChatRequest
from PIL import Image
from pydantic import BaseModel, ConfigDict

from legible.schema import CorpusSchema, GroupSpec

#: The provider entry in boundary.yaml.
PROVIDER: Final = "azure-docintel"
#: Training documents per custom model, the first by id of the split's training part. FARA's
#: and DeepForm's splits have 200; NIST's faces between 40 and 600. Bounded because each
#: training document is read by the layout model first, at US$10 a 1,000 pages, and training
#: time grows with the set (ten free hours a month across every build).
TRAIN_DOCS: Final = {"fara": 100, "deepform": 100, "nist": 30}
LABELS_SCHEMA: Final = (
    "https://schema.cognitiveservices.azure.com/formrecognizer/2021-03-01/labels.json"
)
FIELDS_SCHEMA: Final = (
    "https://schema.cognitiveservices.azure.com/formrecognizer/2021-03-01/fields.json"
)


def model_id(dataset: str) -> str:
    """The custom model's id on the resource for a training set: `legible-<set>`, in the
    characters the service allows."""
    return "legible-" + re.sub(r"[^A-Za-z0-9._~-]", "-", dataset)


def custom_model(dataset: str) -> str:
    """The explicit gateway model for a training set's custom model."""
    return f"{PROVIDER}/custom/{model_id(dataset)}"


# -- the document ---------------------------------------------------------------------------


def document_tiff(images: Sequence[Path]) -> bytes:
    """Pages as one multi-page TIFF, deflate-compressed, so the service reads exactly the
    pixels every other arm reads."""
    if not images:
        raise ValueError("a document needs at least one page")
    frames = []
    for p in images:
        with Image.open(p) as img:
            if img.mode == "1":
                frames.append(img.copy())
            else:
                frames.append(img.convert("L") if img.mode in {"L", "LA"} else img.convert("RGB"))
    buf = io.BytesIO()
    frames[0].save(
        buf, format="TIFF", save_all=True, append_images=frames[1:], compression="tiff_deflate"
    )
    return buf.getvalue()


def analyze_request(model: str, tiff: bytes, pages: int) -> ChatRequest:
    """One document for the gateway's Document Intelligence adapter (boundary 1.6)."""
    return ChatRequest(
        model=model,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "document",
                        "source": {
                            "type": "base64",
                            "media_type": "image/tiff",
                            "data": base64.b64encode(tiff).decode("ascii"),
                        },
                    }
                ],
            }
        ],
        extra={"pages": pages},
    )


# -- labels for training --------------------------------------------------------------------

_EDGE = re.compile(r"^[\W_]+|[\W_]+$", re.UNICODE)


def norm_token(text: str) -> str:
    """A token as labels are matched: NFKC, case-folded, surrounding punctuation stripped."""
    return _EDGE.sub("", unicodedata.normalize("NFKC", text).casefold())


def find_words(
    value: str, pages: Sequence[Mapping[str, Any]], used: set[tuple[int, int]] | None = None
) -> list[tuple[int, int]] | None:
    """The (page index, word index) of the words that spell `value`, consecutive on one page,
    or None. Tokens that are only punctuation are skipped on both sides; `used` words are not
    matched again, so two fields with the same value label two different places."""
    want = [t for t in (norm_token(w) for w in value.split()) if t]
    if not want:
        return None
    taken = used or set()
    for pi, page in enumerate(pages):
        words = page.get("words") or []
        tokens = [(wi, norm_token(str(w.get("content", "")))) for wi, w in enumerate(words)]
        tokens = [(wi, t) for wi, t in tokens if t]
        for start in range(len(tokens) - len(want) + 1):
            window = tokens[start : start + len(want)]
            if all(t == w for (_, t), w in zip(window, want, strict=True)) and not any(
                (pi, wi) in taken for wi, _ in window
            ):
                return [(pi, wi) for wi, _ in window]
    return None


def _box(word: Mapping[str, Any], page: Mapping[str, Any]) -> list[float]:
    """A word's polygon as the labels file takes it: eight numbers, each over the page's
    width or height."""
    poly = [float(v) for v in word["polygon"]]
    w, h = float(page["width"]), float(page["height"])
    return [round(v / (w if i % 2 == 0 else h), 6) for i, v in enumerate(poly)]


class LabelCoverage(BaseModel):
    """How many of a training set's filled truth values were found on the page's words."""

    model_config = ConfigDict(frozen=True)

    documents: int
    values: int
    labelled: int

    @property
    def share(self) -> float:
        return self.labelled / self.values if self.values else 0.0


def _values(schema: CorpusSchema, record: Mapping[str, Any]) -> Iterable[tuple[str, str]]:
    """(label, value) for every filled value of a truth record, tables row by row."""
    for f in schema.fields:
        value = record.get(f.name)
        if isinstance(f, GroupSpec):
            for row, item in enumerate(value if isinstance(value, list) else []):
                for col in f.fields:
                    v = item.get(col.name) if isinstance(item, Mapping) else None
                    if isinstance(v, str) and v.strip():
                        yield f"{f.name}/{row}/{col.name}", v
        elif isinstance(value, str) and value.strip():
            yield f.name, value


def labels(
    schema: CorpusSchema, document: str, record: Mapping[str, Any], analyze: Mapping[str, Any]
) -> tuple[dict[str, Any], int, int]:
    """The labels file for one training document, from its truth and its layout reading.
    Returns (labels file, filled values, values labelled)."""
    pages = analyze.get("pages") or []
    used: set[tuple[int, int]] = set()
    out: list[dict[str, Any]] = []
    total = found = 0
    for label, value in _values(schema, record):
        total += 1
        hit = find_words(value, pages, used)
        if hit is None:
            continue
        found += 1
        used.update(hit)
        out.append(
            {
                "label": label,
                "value": [
                    {
                        "page": pi + 1,
                        "text": str(pages[pi]["words"][wi]["content"]),
                        "boundingBoxes": [_box(pages[pi]["words"][wi], pages[pi])],
                    }
                    for pi, wi in hit
                ],
            }
        )
    return {"$schema": LABELS_SCHEMA, "document": document, "labels": out}, total, found


def fields_file(schema: CorpusSchema) -> dict[str, Any]:
    """The training set's fields.json: every schema field a string, tables as arrays of
    objects."""
    fields: list[dict[str, Any]] = []
    definitions: dict[str, Any] = {}
    for f in schema.fields:
        if isinstance(f, GroupSpec):
            item = f"{f.name}_object"
            fields.append(
                {"fieldKey": f.name, "fieldType": "array", "fieldFormat": "not-specified",
                 "itemType": item, "fields": None}
            )  # fmt: skip
            definitions[item] = {
                "fieldKey": item,
                "fieldType": "object",
                "fieldFormat": "not-specified",
                "itemType": None,
                "fields": [
                    {
                        "fieldKey": c.name,
                        "fieldType": "string",
                        "fieldFormat": "not-specified",
                        "itemType": None,
                        "fields": None,
                    }
                    for c in f.fields
                ],
            }
        else:
            fields.append(
                {"fieldKey": f.name, "fieldType": "string", "fieldFormat": "not-specified",
                 "itemType": None, "fields": None}
            )  # fmt: skip
    return {"$schema": FIELDS_SCHEMA, "fields": fields, "definitions": definitions}


def ocr_file(analyze: Mapping[str, Any]) -> dict[str, Any]:
    """The `.ocr.json` a training document carries: the layout reading as the service's own
    analyze response wraps it."""
    return {"status": "succeeded", "analyzeResult": dict(analyze)}


# -- reading the answer back ----------------------------------------------------------------


def _text(field: Mapping[str, Any] | None) -> str | None:
    """A field's text as printed, else its typed value as a string."""
    if not isinstance(field, Mapping):
        return None
    content = field.get("content")
    if isinstance(content, str) and content.strip():
        return content
    for key in ("valueString", "valueDate", "valueNumber", "valueInteger", "valuePhoneNumber"):
        v = field.get(key)
        if v is not None and str(v).strip():
            return str(v)
    return None


def _rows(field: Mapping[str, Any] | None) -> list[Mapping[str, Any]]:
    if not isinstance(field, Mapping):
        return []
    items = field.get("valueArray")
    out = []
    for item in items if isinstance(items, list) else []:
        obj = item.get("valueObject") if isinstance(item, Mapping) else None
        if isinstance(obj, Mapping):
            out.append(obj)
    return out


def document_fields(analyze: Mapping[str, Any]) -> Mapping[str, Any]:
    """The first document's fields, or none."""
    docs = analyze.get("documents")
    if isinstance(docs, list) and docs and isinstance(docs[0], Mapping):
        fields = docs[0].get("fields")
        if isinstance(fields, Mapping):
            return fields
    return {}


def to_record(schema: CorpusSchema, analyze: Mapping[str, Any]) -> dict[str, Any]:
    """A custom model's answer in the corpus schema."""
    fields = document_fields(analyze)
    out: dict[str, Any] = {}
    for f in schema.fields:
        if isinstance(f, GroupSpec):
            rows = [
                {c.name: _text(r.get(c.name)) for c in f.fields} for r in _rows(fields.get(f.name))
            ]
            out[f.name] = [r for r in rows if any(v is not None for v in r.values())]
        else:
            out[f.name] = _text(fields.get(f.name))
    return out


#: The prebuilt receipt model's fields onto CORD's, by what each names. Fields the receipt
#: model has no counterpart for (CORD's sub-items, voided items, service charges, payment
#: lines other than the total) stay null.
RECEIPT_FIELDS: Final[Mapping[str, str]] = {
    "subtotal_price": "Subtotal",
    "tax_price": "TotalTax",
    "total_price": "Total",
}
RECEIPT_ITEM_FIELDS: Final[Mapping[str, str]] = {
    "nm": "Description",
    "cnt": "Quantity",
    "unitprice": "Price",
    "price": "TotalPrice",
}


def receipt_record(schema: CorpusSchema, analyze: Mapping[str, Any]) -> dict[str, Any]:
    """The prebuilt receipt model's answer in CORD's schema (`RECEIPT_FIELDS`)."""
    fields = document_fields(analyze)
    out: dict[str, Any] = {}
    for f in schema.fields:
        if isinstance(f, GroupSpec):
            out[f.name] = []
        else:
            src = RECEIPT_FIELDS.get(f.name)
            out[f.name] = _text(fields.get(src)) if src else None
    menu = next(g for g in schema.fields if isinstance(g, GroupSpec) and g.name == "menu")
    items = []
    for row in _rows(fields.get("Items")):
        item: dict[str, Any] = {c.name: None for c in menu.fields}
        for ours, theirs in RECEIPT_ITEM_FIELDS.items():
            item[ours] = _text(row.get(theirs))
        if any(v is not None for v in item.values()):
            items.append(item)
    out["menu"] = items
    return out


def answer_text(record: Mapping[str, Any]) -> str:
    """A record as the stored read's text, compact JSON as every arm's answer is graded."""
    return json.dumps(record, ensure_ascii=False, separators=(",", ":"))
