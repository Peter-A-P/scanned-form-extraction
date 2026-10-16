"""CORD v2: photographed Indonesian receipts, CC BY 4.0, from the Hugging Face Hub at a pinned
commit with every shard's sha256 verified (legible/data/checksums/cord.json).

Truth is `gt_parse`, flattened to the schema in legible/schema/corpora.py:

- `menu` is a list of items, or a single dict when the receipt has one item; both become the
  `menu` group. An item's `sub` (a set meal's components) becomes a `sub_item` row, in
  order, because the grader aligns rows within a group and a component is scored as a row of
  its own; which parent it belonged to is not scored.
- `sub_total.*` and `total.*` are scalars. A few receipts print one of them twice (two tax
  lines, two cash tenders); the first is the truth and the rest are alternatives, so reading
  any printed value counts, as VRDU does with its candidates.
- `sub_total.etc` is `subtotal_etc`, so it cannot collide with a menu item's `etc`.

The splits are CORD's own: 800 train, 100 dev, 100 test. The images are PNG already and are
kept byte for byte; they are photographs, not scans, so there is no rasterising step.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from legible.data.fetch import fetch, load_checksums
from legible.data.render import PageEntry
from legible.schema import Item, Record, SchemaDrift
from legible.schema.corpora import CORD

CordSplit = Literal["train", "dev", "test"]
_SHARD_SPLIT: dict[str, CordSplit] = {"train": "train", "validation": "dev", "test": "test"}
_RENAME = {("sub_total", "etc"): "subtotal_etc"}


class CordDoc(BaseModel):
    model_config = ConfigDict(frozen=True)

    doc_id: str
    split: CordSplit
    truth: Record
    alternatives: dict[str, list[str]]


def shard_split(path: str) -> CordSplit:
    return _SHARD_SPLIT[Path(path).name.split("-")[0]]


def fetch_shards(raw_dir: Path) -> list[Path]:
    checksums = load_checksums("cord")
    base = f"https://huggingface.co/datasets/naver-clova-ix/cord-v2/resolve/{checksums.commit}/"
    return [
        fetch(base + p, checksums.get(p), checksums.algorithm, raw_dir / p)
        for p in sorted(checksums.files)
    ]


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _texts(value: Any) -> list[str]:
    return [str(v).strip() for v in _as_list(value) if str(v).strip()]


def parse_gt(doc_id: str, gt_parse: dict[str, Any]) -> tuple[Record, dict[str, list[str]]]:
    """`gt_parse` as a truth record and its alternatives. Refuses any key the schema lacks."""
    groups = {g.name: g for g in CORD.groups}
    scalars = {f.name for f in CORD.scalars}
    truth: Record = {g: [] for g in groups}
    alternatives: dict[str, list[str]] = {}

    def row(group: str, raw: dict[str, Any]) -> Item:
        spec = groups[group]
        unknown = set(raw) - {f.name for f in spec.fields} - ({"sub"} if group == "menu" else set())
        if unknown:
            raise SchemaDrift(f"{doc_id}: {group} carries {sorted(unknown)}")
        item: Item = {}
        for f in spec.fields:
            texts = _texts(raw.get(f.name))
            item[f.name] = " ".join(texts) if texts else None
        return item

    for section, body in gt_parse.items():
        if section in {"menu", "void_menu"}:
            for raw in _as_list(body):
                rows = truth[section]
                assert isinstance(rows, list)
                rows.append(row(section, raw))
                if section == "menu":
                    for sub in _as_list(raw.get("sub")):
                        subs = truth["sub_item"]
                        assert isinstance(subs, list)
                        subs.append(row("sub_item", sub))
        elif section in {"sub_total", "total"}:
            for key, value in _as_list(body)[0].items() if body else ():
                name = _RENAME.get((section, key), key)
                if name not in scalars:
                    raise SchemaDrift(f"{doc_id}: {section}.{key} is not a CORD field")
                texts = list(dict.fromkeys(_texts(value)))
                if texts:
                    truth[name] = texts[0]
                    if len(texts) > 1:
                        alternatives[name] = texts[1:]
        else:
            raise SchemaDrift(f"{doc_id}: gt_parse section {section!r} is not a CORD section")
    CORD.check_record(truth, what=f"truth for {doc_id}")
    return truth, alternatives


def read_shard(path: Path, pages_dir: Path | None) -> Iterator[tuple[CordDoc, PageEntry | None]]:
    """Every receipt of one verified shard; with `pages_dir`, its image written there."""
    import pyarrow.parquet as pq

    split = shard_split(str(path))
    table = pq.read_table(path)
    for image, gt_text in zip(
        table.column("image").to_pylist(), table.column("ground_truth").to_pylist(), strict=True
    ):
        gt = json.loads(gt_text)
        doc_id = f"{split}-{int(gt['meta']['image_id']):04d}"
        truth, alternatives = parse_gt(doc_id, gt["gt_parse"])
        entry = None
        if pages_dir is not None:
            data: bytes = image["bytes"]
            rel = f"cord/{doc_id}/p00.png"
            dest = pages_dir / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
            size = gt["meta"]["image_size"]
            entry = PageEntry(
                corpus="cord",
                doc_id=doc_id,
                page=0,
                path=rel,
                width=int(size["width"]),
                height=int(size["height"]),
                sha256=hashlib.sha256(data).hexdigest(),
            )
        yield CordDoc(doc_id=doc_id, split=split, truth=truth, alternatives=alternatives), entry
