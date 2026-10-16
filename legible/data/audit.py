"""The 200-label hand audit, done before the first frontier run.

VRDU and CORD are human-annotated, and a benchmark's labels are not its truth just because
they are its labels. Two hundred labels are drawn, fixed by a seed, across the three corpora:
FARA 60, DeepForm 80 (its line items included, where annotation is hardest), CORD 60. Each is
shown to Peter as the label's text beside the crop of the page it was annotated on, and he
marks it right, wrong (with the value the page actually shows) or unreadable. The disagreement
rate is published per corpus with its interval (docs/audit.md). A label the audit overturns
is corrected through a recorded patch file, never silently; the patch is applied by the
loaders and named in every result it changes.

Registration-form crops are shown only on the local worksheet, never published.
"""

from __future__ import annotations

import base64
import hashlib
import html
import io
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Literal

from PIL import Image
from pydantic import BaseModel, ConfigDict

from legible.stats import Interval, mean_ci

QUOTAS: dict[str, int] = {"fara": 60, "deepform": 80, "cord": 60}
SEED = "audit-2026-10-16"
Box = tuple[int, float, float, float, float]


class Label(BaseModel):
    """One annotated value and where it is printed."""

    model_config = ConfigDict(frozen=True)

    corpus: str
    doc_id: str
    key: str
    value: str
    box: Box

    @property
    def label_id(self) -> str:
        return f"{self.corpus}/{self.doc_id}/{self.key}"


class Decision(BaseModel):
    model_config = ConfigDict(frozen=True)

    label_id: str
    verdict: Literal["right", "wrong", "unreadable"]
    #: The value the page shows, for a label marked wrong.
    corrected: str | None = None


def labels_of(
    corpus: str, doc_id: str, truth_boxes: Mapping[str, Box], values: Mapping[str, str]
) -> list[Label]:
    """Every label of a document that has both a value and a box."""
    return [
        Label(corpus=corpus, doc_id=doc_id, key=k, value=values[k], box=b)
        for k, b in sorted(truth_boxes.items())
        if values.get(k)
    ]


def flat_values(truth: Mapping[str, object]) -> dict[str, str]:
    """A truth record's values keyed as the boxes are: `field` or `group[i].field`."""
    out: dict[str, str] = {}
    for name, value in truth.items():
        if isinstance(value, list):
            for i, item in enumerate(value):
                if isinstance(item, Mapping):
                    for field, v in item.items():
                        if isinstance(v, str) and v:
                            out[f"{name}[{i}].{field}"] = v
        elif isinstance(value, str) and value:
            out[name] = value
    return out


def _rank(label: Label) -> str:
    return hashlib.sha256(f"{SEED}:{label.label_id}".encode()).hexdigest()


def sample(labels: Sequence[Label], quotas: Mapping[str, int] = QUOTAS) -> list[Label]:
    """The audit sample: per corpus, the labels with the lowest seeded hash, at most one per
    document so that one odd form cannot dominate a corpus's rate.

    Where a corpus has both, half the quota is scalar fields and half line-item fields, with
    the rate reported for each: line items outnumber the header fields eleven to one on
    DeepForm, and a uniform draw would audit almost nothing a headline number rests on.
    """
    out: list[Label] = []
    for corpus, quota in quotas.items():
        pool = sorted((x for x in labels if x.corpus == corpus), key=_rank)
        strata = [[x for x in pool if "[" not in x.key], [x for x in pool if "[" in x.key]]
        strata = [s for s in strata if s]
        shares = [
            quota // len(strata) + (1 if i < quota % len(strata) else 0) for i in range(len(strata))
        ]
        seen_docs: set[str] = set()
        for stratum, share in zip(strata, shares, strict=True):
            taken = 0
            for label in stratum:
                if taken == share:
                    break
                if label.doc_id in seen_docs:
                    continue
                seen_docs.add(label.doc_id)
                out.append(label)
                taken += 1
        if len(seen_docs) < quota:
            raise ValueError(f"{corpus}: {len(seen_docs)} documents with labels, quota {quota}")
    return out


def crop(page_png: bytes, box: Box, *, margin: float = 0.04) -> bytes:
    """The label's region with some page around it, as PNG."""
    _, x1, y1, x2, y2 = box
    with Image.open(io.BytesIO(page_png)) as img:
        w, h = img.size
        region = (
            max(0, int((x1 - margin) * w)),
            max(0, int((y1 - margin) * h)),
            min(w, int((x2 + margin) * w)),
            min(h, int((y2 + margin) * h)),
        )
        out = io.BytesIO()
        img.crop(region).save(out, format="PNG")
        return out.getvalue()


def worksheet(labels: Sequence[Label], crops: Mapping[str, bytes]) -> str:
    """A self-contained local HTML page: each label beside its crop, three choices, and a
    button that saves the decisions as JSON for docs/audit/decisions.json."""
    rows = []
    for i, label in enumerate(labels):
        img = base64.b64encode(crops[label.label_id]).decode("ascii")
        lid = html.escape(label.label_id, quote=True)
        rows.append(
            f'<section data-id="{lid}"><h2>{i + 1}. {html.escape(label.corpus)} '
            f"<code>{html.escape(label.key)}</code></h2>"
            f'<img src="data:image/png;base64,{img}" alt="crop">'
            f"<p>Label: <strong>{html.escape(label.value)}</strong></p>"
            + "".join(
                f'<label><input type="radio" name="v{i}" value="{v}"> {v}</label> '
                for v in ("right", "wrong", "unreadable")
            )
            + f'<input type="text" name="c{i}" placeholder="what the page shows, if wrong"></section>'
        )
    script = """
document.getElementById('save').onclick = () => {
  const out = [];
  document.querySelectorAll('section').forEach((s, i) => {
    const v = s.querySelector('input[name=v' + i + ']:checked');
    if (!v) return;
    const c = s.querySelector('input[name=c' + i + ']').value.trim();
    out.push({label_id: s.dataset.id, verdict: v.value, corrected: v.value === 'wrong' ? c || null : null});
  });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([JSON.stringify(out, null, 1)], {type: 'application/json'}));
  a.download = 'decisions.json';
  a.click();
  document.getElementById('count').textContent = out.length + ' of ' + document.querySelectorAll('section').length + ' saved';
};"""
    style = (
        "body{font:16px system-ui,sans-serif;max-width:900px;margin:0 auto;padding:16px;background:#fff;color:#111}"
        "section{border-top:1px solid #ccc;padding:12px 0}img{max-width:100%;border:1px solid #999}"
        "input[type=text]{width:100%;margin-top:6px}code{background:#eee;padding:0 4px}"
        "#bar{position:sticky;top:0;background:#fff;padding:8px 0}"
    )
    return (
        "<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width'>"
        f"<title>Label audit</title><style>{style}</style></head><body>"
        "<div id='bar'><button id='save'>Save decisions</button> <span id='count'></span></div>"
        "<h1>Label audit: is the label what the page shows?</h1>"
        + "".join(rows)
        + f"<script>{script}</script></body></html>"
    )


class AuditReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    corpus: str
    #: "all", "fields" (scalars) or "line items".
    stratum: str
    audited: int
    disagreement: Interval
    unreadable: int


def report(labels: Sequence[Label], decisions: Sequence[Decision]) -> list[AuditReport]:
    """Disagreement rate (wrong over audited, unreadable excluded) per corpus, overall and
    for scalar fields and line items apart where a corpus has both."""
    by_id = {d.label_id: d for d in decisions}
    missing = [x.label_id for x in labels if x.label_id not in by_id]
    if missing:
        raise ValueError(f"{len(missing)} labels have no decision, first {missing[:3]}")
    out = []
    for corpus in QUOTAS:
        mine = [x for x in labels if x.corpus == corpus]
        groups = {
            "all": mine,
            "fields": [x for x in mine if "[" not in x.key],
            "line items": [x for x in mine if "[" in x.key],
        }
        for stratum, members in groups.items():
            if not members or (stratum != "all" and len(members) == len(mine)):
                continue
            ds = [by_id[x.label_id] for x in members]
            judged = [d for d in ds if d.verdict != "unreadable"]
            out.append(
                AuditReport(
                    corpus=corpus,
                    stratum=stratum,
                    audited=len(judged),
                    disagreement=mean_ci([float(d.verdict == "wrong") for d in judged]),
                    unreadable=len(ds) - len(judged),
                )
            )
    return out


def read_decisions(path: Path) -> list[Decision]:
    return [Decision.model_validate(d) for d in json.loads(path.read_text(encoding="utf-8"))]
