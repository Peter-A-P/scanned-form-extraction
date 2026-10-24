"""Uploading an adapter and its card to the Hugging Face Hub.

Every published adapter has a card with failure modes in the same commit as the upload
(CLAUDE.md), so `publish` refuses an adapter whose card is missing, whose card names another
run, or whose card says it is not for upload, and sends the adapter's files and the card as
the repository's README in one Hub commit. Repositories are created private unless asked
otherwise: making an adapter public is a decision, not a default.

The token is read from `HF_TOKEN` and never printed. `huggingface_hub` is imported only by
the real uploader, so the checks here are tested on a laptop without it; it comes with the
train extra (transformers depends on it), which is installed where the adapters are, on the
rented card's volume.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from legible.cards import read_front_matter

TOKEN_VARIABLE = "HF_TOKEN"


class PublishRefused(Exception):
    """An upload that would break the rules is not started."""


class Uploader(Protocol):
    """The two Hub calls an upload makes."""

    def create_repo(self, repo_id: str, *, private: bool) -> str:
        """Create the repository if it is not there; return its full id."""
        ...

    def commit(self, repo_id: str, files: Sequence[tuple[str, Path]], message: str) -> str:
        """Add (path in repo, local file) pairs in one commit; return the commit's URL."""
        ...


@dataclass(frozen=True)
class Upload:
    repo_id: str
    private: bool
    files: tuple[str, ...]
    card_sha256: str
    commit_url: str


def adapter_files(adapter: Path) -> list[tuple[str, Path]]:
    """Every file under the adapter directory, by its path in the repository. A README the
    directory carries is dropped: the card is the README."""
    out = []
    for p in sorted(adapter.rglob("*")):
        rel = p.relative_to(adapter).as_posix()
        if p.is_file() and rel != "README.md":
            out.append((rel, p))
    return out


def check(adapter: Path, card: Path) -> str:
    """The run id the adapter and its card agree on, or a refusal saying why not."""
    if not card.is_file():
        raise PublishRefused(
            f"no card at {card}: every published adapter has its card in the same commit "
            "(`legible cards` writes it)"
        )
    meta = read_front_matter(card.read_text(encoding="utf-8"))
    run_id = meta.get("legible_run_id")
    if not run_id:
        raise PublishRefused(f"{card} names no run (`legible_run_id`)")
    if meta.get("legible_publishable") is not True:
        raise PublishRefused(f"{card} marks {run_id} as not for upload")
    if not (adapter / "adapter_config.json").is_file():
        raise PublishRefused(f"{adapter} has no adapter_config.json: not a PEFT adapter")
    record = adapter / "run.json"
    if not record.is_file():
        raise PublishRefused(f"{adapter} has no run.json, so nothing ties it to its card")
    trained = json.loads(record.read_text(encoding="utf-8")).get("run_id")
    if trained != run_id:
        raise PublishRefused(f"the adapter is run {trained} and the card is for {run_id}")
    peft = json.loads((adapter / "adapter_config.json").read_text(encoding="utf-8"))
    base = peft.get("base_model_name_or_path")
    if base and base != meta.get("base_model"):
        raise PublishRefused(
            f"the adapter's base is {base} and the card's {meta.get('base_model')}"
        )
    return str(run_id)


def publish(
    adapter: Path,
    card: Path,
    repo_id: str,
    uploader: Uploader,
    *,
    private: bool = True,
) -> Upload:
    """Check, then create the repository and commit the adapter with its card as README."""
    run_id = check(adapter, card)
    files = [*adapter_files(adapter), ("README.md", card)]
    card_sha = hashlib.sha256(card.read_bytes()).hexdigest()
    full_id = uploader.create_repo(repo_id, private=private)
    url = uploader.commit(
        full_id, files, f"Adapter {run_id} with its card (sha256 {card_sha[:12]})"
    )
    return Upload(
        repo_id=full_id,
        private=private,
        files=tuple(p for p, _ in files),
        card_sha256=card_sha,
        commit_url=url,
    )


class HubUploader:
    """The real uploader: huggingface_hub with the token from HF_TOKEN."""

    def __init__(self, token: str | None = None) -> None:
        token = token if token is not None else os.environ.get(TOKEN_VARIABLE)
        if not token:
            raise PublishRefused(f"{TOKEN_VARIABLE} is not set; nothing was uploaded")
        try:
            from huggingface_hub import HfApi
        except ImportError as missing:
            raise PublishRefused(
                "huggingface_hub is not installed here; it comes with the train extra "
                "(`uv sync --extra train`), where the adapters are"
            ) from missing
        self._api = HfApi(token=token)

    def create_repo(self, repo_id: str, *, private: bool) -> str:
        url = self._api.create_repo(repo_id, repo_type="model", private=private, exist_ok=True)
        # A repository that already existed keeps its visibility; refuse rather than upload
        # into a public one when private was asked for.
        found = bool(self._api.model_info(url.repo_id).private)
        if found != private:
            raise PublishRefused(
                f"{url.repo_id} exists and is {'private' if found else 'public'}; asked for "
                f"{'private' if private else 'public'}, so nothing was uploaded"
            )
        return str(url.repo_id)

    def commit(self, repo_id: str, files: Sequence[tuple[str, Path]], message: str) -> str:
        from huggingface_hub import CommitOperationAdd

        info = self._api.create_commit(
            repo_id=repo_id,
            repo_type="model",
            operations=[
                CommitOperationAdd(path_in_repo=rel, path_or_fileobj=str(p)) for rel, p in files
            ],
            commit_message=message,
        )
        return str(info.commit_url)
