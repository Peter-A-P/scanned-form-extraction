# Working notes for Claude Code

This repository is Forms That Read Themselves, package `legible`: measuring
how well a frontier vision model, a fine-tuned small vision model, OCR with rules and OCR text
with a language model read scanned forms, on three public corpora with known answers, and what
each costs a thousand pages. The plan is in [PLAN.md](PLAN.md); the diagrams in
[docs/architecture.md](docs/architecture.md). Status: building since 2026-10-16; nothing measured yet.

## Read first

- [README.md](README.md): what this is and, once there are any, the result tables.
- [PLAN.md](PLAN.md): the design. Do not deviate from it silently; if something in it turns
  out wrong, change the plan in the same commit as the code and say why in the commit
  message.
- `docs/data.md`, `docs/models.md`, `docs/gpu-prices.md` and `docs/degradation.md` once they
  exist: the licences as quoted, the model identifiers with dates, the GPU decision, and what
  each degradation level means in OCR word accuracy.

## Engineering standard

- Python 3.13. Typed throughout; `mypy --strict` and `ruff` clean in CI.
- Tests that fail meaningfully: the grader against adversarial fixtures, the schema drift
  refusal, degradation determinism, the split leakage checks, the review-rate arithmetic.
- `pyproject.toml` with pinned major versions and a comment saying why for each pin.
- Docs ship in the same commit as the change. Every published adapter has a card with failure
  modes in the same commit as the upload.
- Never commit credentials, provider keys, Hugging Face tokens, or anything from `.env`.

## Rules specific to this repository

- **No model grades another model.** Truth is the corpus label; grading is programmatic.
- **Headline numbers for the VRDU corpora come from the unseen-template split.** The
  mixed-template number is reported beside it as the gap, never as the headline.
- **Test sets are touched once per arm.** Prompts and thresholds are tuned on dev.
- **Nothing raw is committed.** Loaders fetch and verify checksums; licences are quoted in
  `docs/data.md` before the first fetch.
- **Every page sent to a vendor is public**, declared `data_class=public` through the gateway,
  and that declaration must stay true. Registration forms are never shown as images on the
  demo.
- **Every model call goes through the gateway**, frontier and self-hosted alike, so cost per
  page has one source.
- **Nothing is measured on the laptop.** The 4 GB card runs tests and the site build. The one
  exception (PLAN.md, risks): frontier batches are submitted from it through the gateway, and
  nothing timed is taken from them.
- **Checkpoint from the first step.** Every training run resumes from object storage.
- **Every reported number carries a confidence interval**, and every price carries its date.
- **Plain punctuation** in everything written here: no em-dashes or other typographic dashes,
  straight quotes only.

## What goes in the README

The README opens with the one-liner, the results tables and the honest limitation, before any
installation instructions. The report command fills the tables; do not hand-edit them. Record
one approach that was tried and rejected, with the evidence, once the work has produced it.
