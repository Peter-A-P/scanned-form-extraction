"""Arms B and C served: a merged fine-tune or an untuned instruction model behind vLLM, read
through the gateway like every other arm.

06's serving shape (smallprint/serve/launch.py and train/merge.py at 3adf4fad), for page
images:

- **Merge.** The adapter is folded into the bf16 base at the revision it was trained on
  (`PeftModel.merge_and_unload`), and the merge is checked rather than assumed: over one
  training example's answer, the next-token predictions of the adapter on the base and of the
  merged weights must agree on at least 99% of positions. The processor files and the
  instruction model's chat template and stop tokens are written beside the weights, because
  vLLM will not serve a Gemma checkpoint without the processor configuration and a base names
  no end-of-turn token (06 found both on 2026-09-24).
- **Serve.** `vllm serve` with the run's visual budget (`max_soft_tokens`), as many images a
  prompt as the longest document has pages, and the merged checkpoint's generation config.
- **Read.** The gateway's self-hosted provider (`openai_compat`, `self_hosted: true`) points
  at the server, and `legible read` reads through it with the OpenAI content shape the
  server takes. Cost per page comes from the GPU's hourly rate over measured throughput
  (`legible.bench.cost`), not from a vendor price list.
"""

from __future__ import annotations

import json
import shutil
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from pydantic import BaseModel, ConfigDict

MIN_AGREEMENT: Final = 0.99
PROCESSOR_FILES: Final = ("processor_config.json",)
PROVIDER: Final = "selfhosted"


class MergeRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    run_id: str
    base: str
    revision: str
    agreement: float
    positions: int


def agreement(a: Sequence[int], b: Sequence[int]) -> float:
    """Share of positions where two next-token predictions agree."""
    if len(a) != len(b) or not a:
        raise ValueError("predictions of different lengths, or none")
    return sum(x == y for x, y in zip(a, b, strict=True)) / len(a)


def served_generation_config(
    instruct: Mapping[str, Any], base: Mapping[str, Any]
) -> dict[str, Any]:
    """Stop tokens from the instruction model, ids from the base, and no sampling fields."""
    eos = instruct.get("eos_token_id")
    ids = [eos] if isinstance(eos, int) else [int(t) for t in eos or []]
    if not ids:
        raise ValueError("the instruction model names no stop token")
    out: dict[str, Any] = {"eos_token_id": ids}
    for key in ("bos_token_id", "pad_token_id"):
        if base.get(key) is not None:
            out[key] = base[key]
    return out


def merge(adapter_dir: Path, out_dir: Path, check: Any) -> MergeRecord:
    """Merge a run's adapter into its bf16 base and check it on one example.

    `check` is the (encoding, labels) of one training example, from the training
    collator, so the check is on the format the model was trained on."""
    import torch
    from huggingface_hub import hf_hub_download
    from peft import PeftModel
    from transformers import AutoModelForImageTextToText

    from legible.train.vision import IGNORE, read_record

    record = read_record(adapter_dir.parent)
    base = record.config.base
    model = AutoModelForImageTextToText.from_pretrained(
        base.repo, revision=base.revision, dtype=torch.bfloat16, device_map="cuda"
    )
    tuned = PeftModel.from_pretrained(model, str(adapter_dir))
    enc, labels = check
    enc = {k: v.to("cuda") if hasattr(v, "to") else v for k, v in enc.items()}
    answer = [i for i, t in enumerate(labels) if t != IGNORE]
    # Logits over the answer's positions only: over a 262k-token vocabulary, a DeepForm
    # example's full logits did not fit beside the 4B on a 24 GB card (2026-10-18).
    keep = len(labels) - answer[0] + 1
    with torch.no_grad():
        before = tuned(**enc, logits_to_keep=keep).logits[0].argmax(-1).tolist()
        merged = tuned.merge_and_unload()
        after = merged(**enc, logits_to_keep=keep).logits[0].argmax(-1).tolist()
    # Index j of the kept logits is position len(labels) - keep + j, which predicts the next.
    positions = [i - 1 - (len(labels) - keep) for i in answer]
    share = agreement([before[i] for i in positions], [after[i] for i in positions])
    if share < MIN_AGREEMENT:
        raise RuntimeError(f"the merge agrees with the adapter on {share:.3f} of the answer")
    out_dir.mkdir(parents=True, exist_ok=True)
    merged.save_pretrained(str(out_dir), safe_serialization=True)
    # The processor and chat template the run saved beside its adapter: Gemma 4's base
    # repository ships no preprocessor_config.json at its pinned revision (the first merge,
    # 2026-10-18, stopped on the 404), and vLLM will not serve the model without one.
    for f in adapter_dir.iterdir():
        if (
            f.is_file()
            and not f.name.startswith("adapter_")
            and f.name not in {"run.json", "README.md"}
        ):
            shutil.copy(f, out_dir / f.name)
    for name in PROCESSOR_FILES:
        if not (out_dir / name).exists():
            raise FileNotFoundError(f"{name} is neither saved with the adapter nor in the base")
    instruct = json.loads(
        Path(
            hf_hub_download(
                base.instruct_repo, "generation_config.json", revision=base.instruct_revision
            )
        ).read_text()
    )
    base_gen = json.loads((out_dir / "config.json").read_text())
    (out_dir / "generation_config.json").write_text(
        json.dumps(
            served_generation_config(instruct, base_gen.get("text_config", base_gen)), indent=1
        )
    )
    out = MergeRecord(
        run_id=record.run_id,
        base=base.repo,
        revision=base.revision,
        agreement=share,
        positions=len(positions),
    )
    (out_dir / "merge.json").write_text(out.model_dump_json(indent=1))
    return out


def vllm_argv(
    model: str,
    served_name: str,
    *,
    visual_tokens: int,
    max_images: int,
    port: int = 8000,
    revision: str | None = None,
) -> list[str]:
    """`vllm serve` for one model with the run's visual budget; a Hub model (arm C's
    instruction models) at its pinned revision."""
    return [
        "vllm",
        "serve",
        model,
        *(["--revision", revision] if revision else []),
        "--served-model-name",
        served_name,
        "--port",
        str(port),
        "--max-model-len",
        # An eleven-page ad buy at 1,120 visual tokens a page and its 8,192-token answer.
        "32768",
        "--gpu-memory-utilization",
        "0.90",
        "--dtype",
        "bfloat16",
        "--generation-config",
        "auto",
        "--limit-mm-per-prompt",
        json.dumps({"image": max_images}),
        "--mm-processor-kwargs",
        json.dumps({"max_soft_tokens": visual_tokens}),
        # The schema's JSON with no whitespace between tokens. With the grammar's optional
        # whitespace allowed, the fine-tuned 2B on DeepForm wrote its first line items and
        # then spaces and newlines to the 8,192-token limit on 150 of 159 test documents
        # (2026-10-18).
        "--structured-outputs-config",
        json.dumps({"backend": "xgrammar", "disable_any_whitespace": True}),
    ]


def gateway_config(
    base_config: Mapping[str, Any], served_name: str, port: int = 8000
) -> dict[str, Any]:
    """boundary.yaml with the self-hosted server as a provider and a route of its own name."""
    config: dict[str, Any] = json.loads(json.dumps(base_config))
    config["providers"][PROVIDER] = {
        "kind": "openai_compat",
        "base_url": f"http://127.0.0.1:{port}/v1",
        "self_hosted": True,
    }
    config["routes"][served_name] = {"provider": PROVIDER, "model": served_name}
    # One attempt: a self-hosted server that fails is a finding, and a retry would hide it
    # in the latency (06's served configuration does the same).
    config.setdefault("retry", {})["max_attempts"] = 1
    # A DeepForm answer runs to 8,192 tokens, minutes on a busy server; the default 120-second
    # read timeout cut the first one off and stopped the pass (2026-10-18).
    config.setdefault("defaults", {}).setdefault("timeouts", {})["read_s"] = 900.0
    return config
