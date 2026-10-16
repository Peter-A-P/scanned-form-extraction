"""VRDU: the registration forms (FARA) and the ad-buy forms (DeepForm).

Fetched from the benchmark's own repository at a pinned commit, every file verified against
its git blob SHA (legible/data/checksums/vrdu.json). Truth is read from `dataset.jsonl.gz`:
a scalar field's first annotated occurrence is its truth and every other distinct text it
was annotated with is an alternative, because VRDU counts a match with any of them; a line
item is one annotation with one candidate. Splits are the benchmark's split files, so that
"unseen template" means what VRDU means.

Headline splits, decided 2026-10-16: train size 200, the largest VRDU publishes, at all three
of its seeds. For FARA the unseen-template level is three files per seed, one per held-out
template; for DeepForm one file per seed, whose test set is the smallest of its train sizes
(159, 157 and 153 documents). The mixed-template files at the same size and seeds carry the
gap.
"""

from __future__ import annotations

import gzip
import json
import re
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Literal
from urllib.parse import quote

from pydantic import BaseModel, ConfigDict

from legible.data.fetch import fetch, load_checksums
from legible.data.split import SplitLeak, check_unseen_templates
from legible.schema import CorpusSchema, Item, Record, SchemaDrift
from legible.schema.corpora import DEEPFORM, FARA

VrduCorpus = Literal["fara", "deepform"]
DIRECTORY: dict[VrduCorpus, str] = {"fara": "registration-form", "deepform": "ad-buy-form"}
SCHEMA: dict[VrduCorpus, CorpusSchema] = {"fara": FARA, "deepform": DEEPFORM}
FARA_TEMPLATES = ("Amendment", "Dissemination_Report", "Short-Form")
SEEDS = (0, 1, 2)
TRAIN_SIZE = 200

_SPLIT_NAME = re.compile(
    r"^(?P<corpus>FARA|DeepForm)-(?P<level>lv1-single_[A-Za-z_-]+|lv2-mixed_template|lv3-unk_[A-Za-z_-]+"
    r"|kno_template|mixed_template|unk_template)-train_(?P<train>\d+)-test_(?P<test>\d+)"
    r"-valid_(?P<valid>\d+)-SD_(?P<seed>\d)\.json$"
)


class VrduDoc(BaseModel):
    """One document: its truth, the alternatives VRDU accepts, and the annotation's text."""

    model_config = ConfigDict(frozen=True)

    corpus: VrduCorpus
    doc_id: str
    pages: int
    truth: Record
    alternatives: dict[str, list[str]]
    text: str


class VrduSplit(BaseModel):
    """One benchmark split file, read."""

    model_config = ConfigDict(frozen=True)

    corpus: VrduCorpus
    file: str
    level: Literal["single", "mixed", "unseen"]
    #: For FARA's single and unseen levels, the template the file is about.
    template: str | None
    seed: int
    train: tuple[str, ...]
    valid: tuple[str, ...]
    test: tuple[str, ...]


def base_url(commit: str) -> str:
    return f"https://raw.githubusercontent.com/google-research-datasets/vrdu/{commit}/"


def headline_split_files(corpus: VrduCorpus, level: Literal["unseen", "mixed"]) -> list[str]:
    """The split files the reported numbers come from, by the names the repository uses."""
    checksums = load_checksums("vrdu")
    prefix = f"{DIRECTORY[corpus]}/few_shot-splits/"
    out = []
    for path in sorted(checksums.files):
        if not path.startswith(prefix):
            continue
        split = parse_split_name(corpus, path.removeprefix(prefix))
        if split is not None and split[0] == level and split[2] in SEEDS and split[3] == TRAIN_SIZE:
            out.append(path)
    return out


def parse_split_name(corpus: VrduCorpus, name: str) -> tuple[str, str | None, int, int] | None:
    """(level, template, seed, train size) from a split file name, or None for another corpus."""
    m = _SPLIT_NAME.match(name)
    if m is None or (m["corpus"] == "FARA") != (corpus == "fara"):
        return None
    raw = m["level"]
    template: str | None = None
    if raw.startswith("lv1-single_"):
        level, template = "single", raw.removeprefix("lv1-single_")
    elif raw.startswith("lv3-unk_"):
        level, template = "unseen", raw.removeprefix("lv3-unk_")
    elif raw in {"lv2-mixed_template", "mixed_template"}:
        level = "mixed"
    elif raw == "unk_template":
        level = "unseen"
    else:
        level = "single"
    return level, template, int(m["seed"]), int(m["train"])


def fetch_files(paths: list[str], raw_dir: Path) -> list[Path]:
    """Fetch and verify repository files into `raw_dir`, keeping the repository's layout."""
    checksums = load_checksums("vrdu")
    base = base_url(checksums.commit)

    def one(p: str) -> Path:
        # FARA file names carry spaces and punctuation; the URL path is quoted, the file on
        # disk keeps the repository's name.
        return fetch(base + quote(p), checksums.get(p), checksums.algorithm, raw_dir / p)

    # Eight at a time: raw.githubusercontent.com serves small files quickly and thousands of
    # them one by one take most of an hour.
    with ThreadPoolExecutor(max_workers=8) as pool:
        return list(pool.map(one, paths))


def _text(entity: list[Any]) -> str:
    return str(entity[0]).strip()


def parse_record(corpus: VrduCorpus, record: dict[str, Any]) -> VrduDoc:
    """One `dataset.jsonl` line as truth. Refuses a field the schema does not name."""
    schema = SCHEMA[corpus]
    scalars = {f.name for f in schema.scalars}
    group = schema.groups[0] if schema.groups else None
    truth: Record = {}
    alternatives: dict[str, list[str]] = {}
    items: list[Item] = []
    for name, candidates in record["annotations"]:
        if isinstance(name, list):
            if group is None:
                raise SchemaDrift(f"{corpus} has no line items, {record['filename']} has one")
            unknown = set(name) - {g.name for g in group.fields}
            if unknown:
                raise SchemaDrift(f"{record['filename']} line item names {sorted(unknown)}")
            (candidate,) = candidates
            item: Item = dict.fromkeys((g.name for g in group.fields), None)
            for sub, entity in zip(name, candidate, strict=True):
                item[sub] = _text(entity)
            items.append(item)
            continue
        if name not in scalars:
            raise SchemaDrift(f"{record['filename']} annotates {name!r}, not a {corpus} field")
        texts = list(dict.fromkeys(t for t in (_text(c) for c in candidates) if t))
        if texts:
            truth[name] = texts[0]
            if len(texts) > 1:
                alternatives[name] = texts[1:]
    if group is not None:
        truth[group.name] = items
    schema.check_record(truth, what=f"truth for {record['filename']}")
    return VrduDoc(
        corpus=corpus,
        doc_id=record["filename"],
        pages=len(record["ocr"]["pages"]),
        truth=truth,
        alternatives=alternatives,
        text=record["ocr"]["text"],
    )


def read_dataset(corpus: VrduCorpus, raw_dir: Path) -> Iterator[VrduDoc]:
    """Every document of a corpus, from the fetched (and so verified) annotation file."""
    path = raw_dir / DIRECTORY[corpus] / "main" / "dataset.jsonl.gz"
    with gzip.open(path, "rt", encoding="utf-8") as f:
        for line in f:
            yield parse_record(corpus, json.loads(line))


def read_split(corpus: VrduCorpus, path: Path) -> VrduSplit:
    parsed = parse_split_name(corpus, path.name)
    if parsed is None:
        raise ValueError(f"{path.name} is not a {corpus} split file")
    level, template, seed, _ = parsed
    raw = json.loads(path.read_text(encoding="utf-8"))
    return VrduSplit(
        corpus=corpus,
        file=path.name,
        level=level,
        template=template,
        seed=seed,
        train=tuple(raw["train"]),
        valid=tuple(raw["valid"]),
        test=tuple(raw["test"]),
    )


def check_split(split: VrduSplit, known: set[str]) -> None:
    """No document in two parts of a split, and every document one the corpus has."""
    parts = {"train": set(split.train), "valid": set(split.valid), "test": set(split.test)}
    for name, docs in parts.items():
        if len(docs) != len(getattr(split, name)):
            raise SplitLeak(f"{split.file}: a document is listed twice in {name}")
    for a, b in (("train", "valid"), ("train", "test"), ("valid", "test")):
        shared = parts[a] & parts[b]
        if shared:
            raise SplitLeak(
                f"{split.file}: {len(shared)} documents in both {a} and {b}, first {sorted(shared)[:3]}"
            )
    missing = set().union(*parts.values()) - known
    if missing:
        raise SplitLeak(
            f"{split.file}: {len(missing)} documents not in the corpus, first {sorted(missing)[:3]}"
        )


def fara_template(doc_id: str) -> str:
    """A FARA document's template, which its file name ends with: `..._Amendment.pdf`,
    `..._Dissemination Report.pdf`, `..._Short-Form.pdf`."""
    return doc_id.removesuffix(".pdf").rsplit("_", 1)[1]


def check_templates(split: VrduSplit) -> None:
    """On FARA's unseen-template files, no template in train is in valid or test.

    DeepForm publishes no template label, so its unseen-template claim rests on the
    benchmark's construction; docs/data.md says so.
    """
    if split.corpus != "fara" or split.level != "unseen":
        return
    train = {fara_template(d) for d in split.train}
    held_out = {fara_template(d) for d in (*split.valid, *split.test)}
    check_unseen_templates(train, held_out, corpus=f"fara ({split.file})")
    if split.template is not None and held_out != {split.template.replace("_", " ")}:
        raise SplitLeak(
            f"{split.file}: held-out documents are {sorted(held_out)}, not {split.template}"
        )
