"""Arm B's training run: QLoRA on page images, resuming from object storage.

06's loop (smallprint/train/qlora.py at 3adf4fad) with the processor in place of the
tokenizer. What differs, and why:

- **The model is the image-text one** (`AutoModelForImageTextToText`, Gemma 4's conditional
  generation class), loaded in 4-bit NF4 with the vision and audio towers and the projector
  kept out of the quantisation, so the frozen encoder reads pages at full precision.
- **Examples are built here, not by TRL.** A collator renders each document as one user turn
  (its page images, then the corpus prompt every arm is sent) and one assistant turn (the
  schema's canonical JSON of the truth), runs the processor once, and masks every label up
  to the start of the answer, so the loss falls on the JSON alone. `loss_tokens` refuses a
  batch whose loss falls on everything or nothing, as 06's does.
- **The visual budget is a recipe field** (`visual_tokens`), set on the image processor
  before the first page, and recorded in the run.

The GPU stack is imported inside the functions that need it, so this module imports, and
its pure parts are tested, on a laptop without torch. Nothing trains on the laptop.
"""

from __future__ import annotations

import datetime as dt
import json
import platform
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from legible.train.checkpoint import CheckpointStore, step_of
from legible.train.dataset import TrainingHeader, TrainingRow
from legible.train.recipe import TARGET_MODULES, TrainConfig

INSTALL_HINT = (
    "training needs the GPU extra, which is not installed here: `uv sync --extra train` on "
    "the rented card. Nothing in this project trains on a laptop."
)
IGNORE = -100


class RunRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    run_id: str
    config: TrainConfig
    #: Every training set the run read: one, or NIST's twenty faces together.
    datasets: list[TrainingHeader]
    chat_template: str
    started_at: dt.datetime
    finished_at: dt.datetime | None = None
    resumed_from_step: int = 0
    steps: int = 0
    train_loss: float | None = None
    seconds_per_step: float | None = None
    max_tokens_seen: int = 0
    versions: dict[str, str] = {}

    def write(self, out_dir: Path) -> Path:
        path = out_dir / "run.json"
        path.write_text(self.model_dump_json(indent=2), encoding="utf-8", newline="\n")
        return path


def messages(instruction: str, n_images: int, target: str | None) -> list[dict[str, Any]]:
    """One document as a chat: its pages then the instruction; the answer when training."""
    user = [{"type": "image"} for _ in range(n_images)] + [{"type": "text", "text": instruction}]
    chat: list[dict[str, Any]] = [{"role": "user", "content": user}]
    if target is not None:
        chat.append({"role": "assistant", "content": [{"type": "text", "text": target}]})
    return chat


def mask_prompt(input_ids: Sequence[int], prompt_length: int, pad_id: int | None) -> list[int]:
    """Labels for one example: the answer's tokens, IGNORE for the prompt and padding."""
    labels = [IGNORE if i < prompt_length else t for i, t in enumerate(input_ids)]
    if pad_id is not None:
        labels = [IGNORE if t == pad_id else lab for t, lab in zip(input_ids, labels, strict=True)]
    return labels


def loss_tokens(labels: Sequence[int]) -> tuple[int, int]:
    """How many tokens carry the loss and how many there are; refuses all or none."""
    counted, total = sum(1 for t in labels if t != IGNORE), len(labels)
    if counted == 0 or counted == total:
        raise RuntimeError(f"the loss falls on {counted} of {total} tokens")
    return counted, total


#: One training document with the instruction its schema's prompt gives it.
Example = tuple[str, TrainingRow]


class Collator:
    """Turns training examples into a model batch, one document per example."""

    def __init__(
        self,
        processor: Any,
        load_page: Callable[[str], Any],
        max_seq_len: int,
    ) -> None:
        self.processor = processor
        self.load_page = load_page
        self.max_seq_len = max_seq_len
        self.longest = 0

    def example(self, example: Example) -> tuple[Any, list[int]]:
        """The processor's encoding of one document, batch of one, and its labels."""
        instruction, row = example
        images = [self.load_page(p) for p in row.pages]
        full = self.processor.apply_chat_template(
            messages(instruction, len(images), row.target), tokenize=False
        )
        prompt = self.processor.apply_chat_template(
            messages(instruction, len(images), None),
            tokenize=False,
            add_generation_prompt=True,
        )
        if not full.startswith(prompt):
            raise RuntimeError("the templated prompt is not a prefix of the templated example")
        enc = self.processor(text=[full], images=[images], return_tensors="pt")
        prompt_enc = self.processor(text=[prompt], images=[images], return_tensors="pt")
        ids = enc["input_ids"][0].tolist()
        if len(ids) > self.max_seq_len:
            raise ValueError(f"{row.doc_id} is {len(ids)} tokens, over max_seq_len")
        self.longest = max(self.longest, len(ids))
        labels = mask_prompt(ids, prompt_enc["input_ids"].shape[1], None)
        loss_tokens(labels)
        return enc, labels

    def __call__(self, rows: Sequence[Example]) -> dict[str, Any]:
        import torch

        if len(rows) != 1:
            raise ValueError("one document a step: pages differ in number and size")
        enc, labels = self.example(rows[0])
        batch = dict(enc)
        batch["labels"] = torch.tensor([labels])
        return batch


def _versions() -> dict[str, str]:
    found = {"python": platform.python_version()}
    for name in ("torch", "transformers", "peft", "bitsandbytes", "accelerate"):
        try:
            found[name] = str(__import__(name).__version__)
        except ImportError:
            continue
    return found


def load_processor(config: TrainConfig) -> Any:
    """The base's processor with the instruction model's chat template and the run's
    visual budget."""
    from transformers import AutoProcessor

    base = config.base
    processor = AutoProcessor.from_pretrained(base.repo, revision=base.revision)
    if getattr(processor, "chat_template", None) is None:
        instruct = AutoProcessor.from_pretrained(
            base.instruct_repo, revision=base.instruct_revision
        )
        processor.chat_template = instruct.chat_template
    processor.image_processor.max_soft_tokens = config.visual_tokens
    return processor


def train(
    config: TrainConfig,
    headers: list[TrainingHeader],
    examples: list[Example],
    pages_dir: Path,
    *,
    out_dir: Path,
    store: CheckpointStore | None = None,
) -> RunRecord:
    """Fine-tune one base on one training set, resuming from the newest checkpoint."""
    try:
        import torch
        from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
        from PIL import Image
        from transformers import (
            AutoModelForImageTextToText,
            BitsAndBytesConfig,
            Trainer,
            TrainingArguments,
        )
    except ImportError as missing:
        raise RuntimeError(f"{INSTALL_HINT} ({missing.name} is missing)") from missing

    out_dir.mkdir(parents=True, exist_ok=True)
    checkpoints = store if store is not None else CheckpointStore(out_dir)
    resume_from = checkpoints.latest()
    processor = load_processor(config)
    record = RunRecord(
        run_id=config.run_id,
        config=config,
        datasets=headers,
        chat_template=f"{config.base.instruct_repo}@{config.base.instruct_revision}",
        started_at=dt.datetime.now(dt.UTC),
        resumed_from_step=(step_of(resume_from) or 0) if resume_from else 0,
        versions=_versions(),
    )
    record.write(out_dir)

    model = AutoModelForImageTextToText.from_pretrained(
        config.base.repo,
        revision=config.base.revision,
        quantization_config=BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_use_double_quant=True,
            bnb_4bit_compute_dtype=torch.bfloat16,
            llm_int8_skip_modules=["vision_tower", "audio_tower", "embed_vision", "embed_audio"],
        ),
        dtype=torch.bfloat16,
        device_map="auto",
    )
    model = prepare_model_for_kbit_training(model, use_gradient_checkpointing=True)
    model = get_peft_model(
        model,
        LoraConfig(
            r=config.rank,
            lora_alpha=config.alpha,
            lora_dropout=config.dropout,
            target_modules=TARGET_MODULES,
            bias="none",
            task_type="CAUSAL_LM",
        ),
    )
    adapted = [n for n, _ in model.named_parameters() if ".lora_A." in n]
    if any("vision_tower" in n or "audio_tower" in n for n in adapted):
        raise RuntimeError("adapters landed on the vision or audio tower")
    if not any("embed_vision" in n for n in adapted):
        raise RuntimeError("no adapter on the vision projector")
    print(f"LoRA on {len(adapted)} layers", flush=True)

    def load_page(rel: str) -> Any:
        with Image.open(pages_dir / rel) as img:
            return img.convert("RGB")

    chosen = examples if config.volume is None else examples[: config.volume]
    collator = Collator(processor, load_page, config.max_seq_len)
    collator.example(chosen[0])  # the loss mask and the length, checked before a step is paid

    arguments = TrainingArguments(
        output_dir=str(out_dir),
        num_train_epochs=config.epochs,
        per_device_train_batch_size=config.batch_size,
        gradient_accumulation_steps=config.grad_accum,
        learning_rate=config.learning_rate,
        warmup_steps=config.warmup_ratio,
        lr_scheduler_type="cosine",
        bf16=True,
        gradient_checkpointing=True,
        logging_steps=5,
        save_steps=config.save_steps,
        save_strategy="steps",
        save_total_limit=2,
        seed=config.seed,
        data_seed=config.seed,
        report_to=[],
        remove_unused_columns=False,
        dataloader_num_workers=2,
    )

    class Rows:
        """The training rows as a map-style dataset the Trainer indexes."""

        def __len__(self) -> int:
            return len(chosen)

        def __getitem__(self, i: int) -> Example:
            return chosen[i]

    trainer = Trainer(model=model, args=arguments, train_dataset=Rows(), data_collator=collator)
    from legible.train.callbacks import SaveToStore, StepTimer

    trainer.add_callback(SaveToStore(checkpoints, out_dir))
    timer = StepTimer()
    trainer.add_callback(timer)
    result = trainer.train(resume_from_checkpoint=str(resume_from) if resume_from else None)
    model.save_pretrained(str(out_dir / "adapter"))
    processor.save_pretrained(str(out_dir / "adapter"))
    finished = record.model_copy(
        update={
            "finished_at": dt.datetime.now(dt.UTC),
            "steps": int(result.global_step),
            "train_loss": float(result.training_loss),
            "seconds_per_step": timer.seconds_per_step,
            "max_tokens_seen": collator.longest,
        }
    )
    finished.write(out_dir)
    from legible.train.checkpoint import CommandSyncer

    if isinstance(checkpoints.syncer, CommandSyncer):
        # Beside the checkpoints, under a name the resume logic does not read as one.
        checkpoints.syncer.push(out_dir / "adapter", "adapter")
    return finished


def read_record(out_dir: Path) -> RunRecord:
    return RunRecord.model_validate_json((out_dir / "run.json").read_text(encoding="utf-8"))


def describe(record: RunRecord) -> str:
    return json.dumps(
        {"run": record.run_id, "steps": record.steps, "train_loss": record.train_loss}, indent=2
    )
