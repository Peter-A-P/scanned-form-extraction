"""NIST Special Database 2: fetched, verified, read and split.

One archive, `sd02.zip`, pinned by its sha256, and NIST's own MD5 list of the 11,200 files
inside it, pinned by its sha256 (`legible/data/checksums/nist.json`). Every member is checked
against the MD5 list as it is read, so nothing is extracted to disk that has not been verified,
and nothing is read from an archive that does not match the one recorded.

A document is one form face: `r0200_03` is the fourth face of simulated submission 200. Its
truth is the answer file (`.fmt`): the face id on the first line, then one field id and value a
line. A value the form wraps onto a second line continues on a line that starts with a tab;
it is joined back on with nothing between, because the wrap falls mid-word. Check marks and
signatures (`_ICON_`) are not text and are left out with their fields (legible/schema). The
pages are 300 ppi binary PNG as published and are kept byte for byte, like CORD's.

The split is by submission, so no submission's faces are in two parts.
"""

from __future__ import annotations

import hashlib
import io
import zipfile
from collections.abc import Iterator, Mapping
from pathlib import Path

from PIL import Image
from pydantic import BaseModel, ConfigDict

from legible.data.fetch import ChecksumMismatch, Pinned, fetch
from legible.data.render import PageEntry
from legible.data.split import Split, carve_dev, split_by_group
from legible.schema import Record
from legible.schema.corpora import SCHEMAS, nist_name

BASE = "https://s3.amazonaws.com/nist-srd/SD2"
#: Parts of the split, as fractions of the 900 submissions: test first, then dev carved from
#: what is left, the rest train (PLAN.md section 3).
TEST, DEV = 0.2, 0.1
SALT = "legible-nist-sd2"


def _pinned() -> tuple[Pinned, Pinned]:
    import json
    from importlib import resources

    raw = json.loads(
        resources.files("legible.data.checksums").joinpath("nist.json").read_text("utf-8")
    )
    files = {p: Pinned(path=p, size=int(v[0]), digest=str(v[1])) for p, v in raw["files"].items()}
    return files["sd02.zip"], files["sd02_md5.lst"]


class NistDoc(BaseModel):
    model_config = ConfigDict(frozen=True)

    doc_id: str
    submission: str
    face: str
    truth: Record

    @property
    def corpus(self) -> str:
        """The schema key: each face is its own form."""
        return f"nist_{self.face.lower()}"


def fetch_sd2(raw_dir: Path) -> tuple[Path, dict[str, str]]:
    """The verified archive and NIST's MD5 for each file inside it."""
    archive, md5_list = _pinned()
    lst = fetch(f"{BASE}/{md5_list.path}", md5_list, "sha256", raw_dir / md5_list.path)
    zip_path = fetch(f"{BASE}/{archive.path}", archive, "sha256", raw_dir / archive.path)
    md5s: dict[str, str] = {}
    for line in lst.read_text(encoding="ascii").splitlines():
        digest, _, name = line.strip().partition(" ")
        if name:
            md5s[name.strip()] = digest
    return zip_path, md5s


def _member(zf: zipfile.ZipFile, name: str, md5s: Mapping[str, str]) -> bytes:
    data = zf.read(name)
    expected = md5s.get(name)
    if expected is None:
        raise ChecksumMismatch(f"{name} is not in NIST's MD5 list")
    got = hashlib.md5(data, usedforsecurity=False).hexdigest()
    if got != expected:
        raise ChecksumMismatch(f"{name}: md5 {got}, NIST lists {expected}")
    return data


def parse_fmt(text: str) -> tuple[str, dict[str, str]]:
    """(face id, field id to value) from an answer file. Empty values are kept as empty."""
    lines = text.splitlines()
    face = lines[0].strip()
    values: dict[str, str] = {}
    last: str | None = None
    for line in lines[1:]:
        if line.startswith("\t"):
            if last is None:
                raise ValueError(f"{face}: a continuation line before any field")
            values[last] += line[1:]
            continue
        if not line.strip():
            continue
        field_id, _, value = line.partition(" ")
        values[field_id.strip()] = value
        last = field_id.strip()
    return face, values


def truth_of(face: str, values: Mapping[str, str]) -> Record:
    """The record the schema scores: every text field of the face, None where it is empty."""
    schema = SCHEMAS[f"nist_{face.lower()}"]
    by_name = {nist_name(k): v for k, v in values.items()}
    record: Record = {}
    for f in schema.scalars:
        v = by_name.get(f.name, "")
        record[f.name] = v.strip() or None
    return record


def read_sd2(
    zip_path: Path, md5s: Mapping[str, str], pages_dir: Path | None
) -> Iterator[tuple[NistDoc, PageEntry | None]]:
    """Every face in the archive, each member verified; with `pages_dir`, its page written."""
    with zipfile.ZipFile(zip_path) as zf:
        names = sorted(n for n in zf.namelist() if n.endswith(".fmt"))
        for fmt in names:
            stem = fmt[: -len(".fmt")]
            doc_id = stem.rsplit("/", 1)[1]
            face, values = parse_fmt(_member(zf, fmt, md5s).decode("ascii"))
            doc = NistDoc(
                doc_id=doc_id,
                submission=doc_id.split("_")[0],
                face=face,
                truth=truth_of(face, values),
            )
            entry = None
            if pages_dir is not None:
                data = _member(zf, stem + ".png", md5s)
                rel = f"nist/{doc_id}/p00.png"
                dest = pages_dir / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(data)
                with Image.open(io.BytesIO(data)) as img:
                    width, height = img.size
                entry = PageEntry(
                    corpus="nist",
                    doc_id=doc_id,
                    page=0,
                    path=rel,
                    width=width,
                    height=height,
                    sha256=hashlib.sha256(data).hexdigest(),
                )
            yield doc, entry


def submission_of(doc_id: str) -> str:
    return doc_id.split("_")[0]


def split(doc_ids: list[str]) -> dict[str, Split]:
    """Train, dev and test by submission: test drawn first, dev carved from what is left."""
    first = split_by_group(doc_ids, submission_of, test=TEST, dev=0.0, salt=SALT)
    return carve_dev(first, submission_of, fraction=DEV / (1 - TEST), salt=SALT)


#: Pages each arm reads from NIST's test part, and the subset read at every degradation level
#: (PLAN.md section 2.5 and section 7): drawn in a fixed hash order, so the subset is the
#: first 300 of the 500.
ARM_TEST, CURVE = 500, 300


def _order(doc_id: str) -> str:
    return hashlib.sha256(f"{SALT}/sample/{doc_id}".encode()).hexdigest()


def arm_sample(test_ids: list[str]) -> list[str]:
    """The test pages every arm reads, in the order the curve's subset is taken from."""
    if len(test_ids) < ARM_TEST:
        raise ValueError(f"the test part has {len(test_ids)} pages, fewer than {ARM_TEST}")
    return sorted(test_ids, key=_order)[:ARM_TEST]


class NistSplitRow(BaseModel):
    model_config = ConfigDict(frozen=True)

    face: str
    part: Split
    #: Among the 500 test pages every arm reads.
    arm_test: bool = False
    #: Among the 300 read at every degradation level.
    curve: bool = False


def split_rows(docs: list[NistDoc]) -> dict[str, NistSplitRow]:
    parts = split([d.doc_id for d in docs])
    sample = arm_sample(sorted(d for d, p in parts.items() if p == "test"))
    curve = set(sample[:CURVE])
    chosen = set(sample)
    return {
        d.doc_id: NistSplitRow(
            face=d.face, part=parts[d.doc_id], arm_test=d.doc_id in chosen, curve=d.doc_id in curve
        )
        for d in sorted(docs, key=lambda d: d.doc_id)
    }


def write_splits(path: Path, rows: Mapping[str, NistSplitRow]) -> None:
    import json

    # One document a line, so a diff of the file reads as the documents that moved.
    lines = [
        json.dumps(d) + ":" + json.dumps(r.model_dump(exclude_defaults=True), separators=(",", ":"))
        for d, r in rows.items()
    ]
    head = '{"source":"legible.data.nist.split_rows","docs":{\n'
    path.write_text(head + ",\n".join(lines) + "\n}}\n", encoding="utf-8", newline="\n")


def read_splits(path: Path) -> dict[str, NistSplitRow]:
    import json

    raw = json.loads(path.read_text(encoding="utf-8"))
    return {d: NistSplitRow.model_validate(r) for d, r in raw["docs"].items()}


def check_split(rows: Mapping[str, NistSplitRow]) -> None:
    """No submission in two parts; the samples drawn from test only, the curve inside them."""
    from legible.data.split import SplitLeak

    parts: dict[str, set[str]] = {}
    for d, r in rows.items():
        parts.setdefault(submission_of(d), set()).add(r.part)
        if r.arm_test and r.part != "test":
            raise SplitLeak(f"{d} is in the arms' test sample but in {r.part}")
        if r.curve and not r.arm_test:
            raise SplitLeak(f"{d} is on the curve but not in the arms' test sample")
    straddling = sorted(s for s, p in parts.items() if len(p) > 1)
    if straddling:
        raise SplitLeak(f"submissions in two parts: {straddling[:5]}")
