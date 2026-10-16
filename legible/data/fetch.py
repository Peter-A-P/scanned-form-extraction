"""Fetching corpus files and verifying them against checksums recorded in the repository.

Each corpus has a file of checksums under legible/data/checksums/, read from its source on
the date that file records and committed, so that what a stranger downloads is provably what
these numbers were measured on. A download that does not match is deleted and refused; a
file already on disk is verified before it is trusted, every time.

VRDU publishes no checksums, so its file is the repository's git tree at a pinned commit:
each blob's SHA-1 over git's `blob <size>\\0` header and the content. CORD's is the Hugging Face
LFS sha256 at a pinned commit. Files are hashed as they stream, because CORD's shards are
half a gigabyte each.
"""

from __future__ import annotations

import hashlib
import http.client
import json
import time
import urllib.request
from collections.abc import Iterable
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import BinaryIO, Literal

Algorithm = Literal["git-blob", "sha256"]
Corpus = Literal["vrdu", "cord"]
USER_AGENT = "legible/0 (+https://github.com/Peter-A-P/scanned-form-extraction)"
_CHUNK = 1 << 20
ATTEMPTS = 4


class ChecksumMismatch(Exception):
    """A file's bytes are not the bytes the recorded checksum names."""


@dataclass(frozen=True, slots=True)
class Pinned:
    """One file of a corpus as recorded: where it lives, its size and its checksum."""

    path: str
    size: int
    digest: str


@dataclass(frozen=True, slots=True)
class Checksums:
    source: str
    commit: str
    algorithm: Algorithm
    files: dict[str, Pinned]

    def get(self, path: str) -> Pinned:
        try:
            return self.files[path]
        except KeyError:
            raise KeyError(f"{path} is not in the recorded checksums for {self.source}") from None


def load_checksums(corpus: Corpus) -> Checksums:
    text = resources.files("legible.data.checksums").joinpath(f"{corpus}.json").read_text("utf-8")
    raw = json.loads(text)
    algorithm: Algorithm = "git-blob" if corpus == "vrdu" else "sha256"
    files = {p: Pinned(path=p, size=int(v[0]), digest=str(v[1])) for p, v in raw["files"].items()}
    return Checksums(source=raw["source"], commit=raw["commit"], algorithm=algorithm, files=files)


def _hasher(algorithm: Algorithm, size: int) -> hashlib._Hash:
    if algorithm == "git-blob":
        h = hashlib.sha1(usedforsecurity=False)
        h.update(b"blob %d\x00" % size)
        return h
    return hashlib.sha256()


def digest(data: bytes, algorithm: Algorithm) -> str:
    h = _hasher(algorithm, len(data))
    h.update(data)
    return h.hexdigest()


def _check(pinned: Pinned, algorithm: Algorithm, size: int, got: str) -> None:
    if size != pinned.size:
        raise ChecksumMismatch(f"{pinned.path}: {size:,} bytes, recorded {pinned.size:,}")
    if got != pinned.digest:
        raise ChecksumMismatch(f"{pinned.path}: {algorithm} {got}, recorded {pinned.digest}")


def _copy_hashing(
    chunks: Iterable[bytes], out: BinaryIO | None, pinned: Pinned, algorithm: Algorithm
) -> None:
    h = _hasher(algorithm, pinned.size)
    size = 0
    for chunk in chunks:
        h.update(chunk)
        size += len(chunk)
        if out is not None:
            out.write(chunk)
    _check(pinned, algorithm, size, h.hexdigest())


def _read_chunks(stream: BinaryIO) -> Iterable[bytes]:
    while chunk := stream.read(_CHUNK):
        yield chunk


def verify_file(path: Path, pinned: Pinned, algorithm: Algorithm) -> None:
    """Raise ChecksumMismatch unless the file on disk is the recorded file."""
    with path.open("rb") as f:
        _copy_hashing(_read_chunks(f), None, pinned, algorithm)


def fetch(url: str, pinned: Pinned, algorithm: Algorithm, dest: Path) -> Path:
    """The verified file at `dest`, downloading it if it is absent or does not verify."""
    if dest.exists():
        try:
            verify_file(dest, pinned, algorithm)
            return dest
        except ChecksumMismatch:
            dest.unlink()
    dest.parent.mkdir(parents=True, exist_ok=True)
    partial = dest.with_name(dest.name + ".partial")
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    # A dropped connection partway through a half-gigabyte shard is common enough to retry;
    # a checksum mismatch is not, and is raised at once.
    for attempt in range(1, ATTEMPTS + 1):
        try:
            with (
                urllib.request.urlopen(request, timeout=300) as response,
                partial.open("wb") as out,
            ):
                _copy_hashing(_read_chunks(response), out, pinned, algorithm)
            break
        except (OSError, http.client.HTTPException):
            partial.unlink(missing_ok=True)
            if attempt == ATTEMPTS:
                raise
            time.sleep(2**attempt)
        except BaseException:
            partial.unlink(missing_ok=True)
            raise
    partial.replace(dest)
    return dest
