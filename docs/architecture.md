# Architecture

The figures behind [PLAN.md](../PLAN.md), drawn before the first line of code so the design
cannot be shaped to fit the result. Four views: the system, one page through the five arms,
the fine-tuning and serving loop, and the evaluation design with the review rate. Nothing in
them is measured yet; the module names are the plan's.

## The system

![Public pages are fetched with their licences quoted, rendered, split and degraded to five levels; five arms read the same pages, the frontier and OCR-to-model arms through the gateway and the fine-tuned models served as gateway hosts; one grader scores every field, the review rate, the verifier, the cost per page and the release gate are computed from the outcomes, and the report writes the tables and the static site.](architecture/system.svg)

Three public corpora, never committed, come in: VRDU's registration and ad-buy forms as PDFs
with annotations, CORD's receipt photos, and NIST SD2's binary tax-form scans with field
files (`docs/data.md`). The fetch step keeps loaders, checksums and the licences quoted
(`legible.data`); pages are rendered at 300 dpi and split, the benchmarks' own splits where
they exist, NIST by simulated submission, with a dev carve-out and a leakage check; and the
degradation step produces levels 0 to 4 from a fixed seed, calibrated to Tesseract word
accuracy rather than to a filter's parameters (`legible.degrade`). Five arms read the same
pages: A, a frontier vision model; B, Gemma 4 E2B and E4B fine-tuned with QLoRA on page
images; C, the same bases untuned; D, Tesseract text to the same frontier model; E, Tesseract
with per-template rules. A and D call through project 04's gateway with image or text blocks at
the public data class, B and C are served on a rented GPU and registered as gateway hosts, so
every call is costed in one ledger. One grader (`legible.grade`) scores every field of every
arm with the schema's matchers and a miss taxonomy, bootstrapped over documents with paired
deltas on identical items. From the outcomes come the review rate at thresholds chosen on dev,
the verifier's arithmetic and format checks, the cost per page from the ledger and the release
gate's non-inferiority verdict per corpus, and the report writes the README tables, the
charts, the model cards and the static site at forms.peterparker.ca.

## One page through the five arms

![One page image at a degradation level, with its corpus schema, is read five ways: a frontier vision model through the gateway, the fine-tuned small vision model, the same model untuned, OCR text to the frontier model, and OCR with per-template rules; one grader scores every field of every arm the same way.](architecture/five-arms.svg)

One page image at a level from 0 to 4 and its corpus schema, one definition that the prompt,
the training targets and the grader all read, go to every arm. A sends an image block with the
instruction and the schema to a frontier model through the gateway, using structured output
where the vendor offers it, and returns JSON. B sends the image at 1120 or 560 visual tokens to
Gemma 4 E2B or E4B with its QLoRA adapter and returns JSON with a per-field confidence from the
logprobs. C sends the same input to the untuned instruction-tuned base, zero- or few-shot. D
runs Tesseract, renders the hOCR words as positioned text and sends it to the same frontier
model as A, text only. E runs Tesseract and applies per-template anchors and patterns built on
the training templates only, returning JSON or a blank. The grader scores every field as right,
wrong field, wrong value, blank filled, invented or malformed, and writes outcomes per document
with a document-level all-right flag.

## Fine-tuning and serving

![Training pages and their JSON targets are fed to QLoRA on a rented spot GPU with the vision encoder frozen and checkpoints in object storage; the ablations run over the token budget, data volume and seeds; the adapters are merged, published with their cards, served, registered with the gateway at a price per page, load-tested and priced into a break-even curve.](architecture/train-serve.svg)

Project 06's loop with a vision encoder. The training split's pages and their JSON targets
from the schema become the dataset (`train/dataset.py`); QLoRA trains rank-16 adapters on the
4-bit base with the vision encoder frozen and the projector and language layers trained
(`train/qlora.py`) on a rented spot GPU of the L4 or 4090 class, an A100 for E4B at 1120
tokens, chosen from the day-one price table and the provider rule in `docs/gpu-prices.md`.
Checkpoints go to object storage every N steps and a run resumes after a reclaim. The
ablations cover the token budget, 1120 against 560, the data volume at all, half and a
quarter, three seeds, and a multi-corpus run. The chosen recipe is merged to bf16, published to
Hugging Face with cards that state failure modes, and served with vLLM if Gemma 4's vision
path is supported and otherwise with batched Transformers (`legible.serve`). The endpoint is
registered with the gateway at a price of the GPU-hour rate over the measured pages per hour,
load-tested at concurrency 1, 8 and 32 for p50 and p99 (`bench/load.py`), and priced into a
break-even curve over utilisation by project 06's arithmetic (`bench/breakeven.py`).

## Evaluation design

![Dev carve-outs from VRDU and CORD are the only pages prompts and confidence thresholds may see; the unseen-template VRDU test carries the headline and the mixed-template test the gap; NIST is split by simulated submission with a leakage check and its 300 degraded pages carry the degradation curve; each test set is run once per arm, bootstrapped over documents, gated per corpus, and the review rate is read at 99 percent.](architecture/evaluation.svg)

Which pages carry which claim, and why each test set is touched once. VRDU's train templates
give a dev carve-out, an unseen-template test whose templates are disjoint from train, which
is the headline, and a mixed-template test reported as the gap between the two. CORD has 800
train, 100 dev and 100 test. NIST SD2 is split by simulated submission with a leakage check on
every build; its training split also yields the data-volume curve at all, half and a quarter,
and its test is 500 clean pages, 300 of them also at levels 1 to 4, which is the degradation
curve. Prompt iteration and the confidence thresholds, B's per-field logprob and the agreement
between A's and D's reads of the same page, are chosen on dev only and frozen. Each test set is
then run once per arm; outcomes are bootstrapped over documents with 95% intervals and paired
deltas on identical items; the release gate tests non-inferiority at a three-point delta per
corpus; the verifier's arithmetic and format checks report what they catch before review; and
the review rate on test is the share of fields routed to a person when the accepted fields
are held to 99 percent right (`legible.review`).
