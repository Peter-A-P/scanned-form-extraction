# Forms That Read Themselves

A vision-language model you own, fine-tuned to type your scanned forms in: a 2B and a 4B open
model trained here to read fields off the scan, measured against the frontier multimodal APIs
and the classic OCR pipelines on more than 9,000 public pages with known answers. Every field
right or wrong with its interval, cost per thousand pages, what breaks on a new form design or
a bad scan, and how many fields a person still checks at 99 percent.

Every organisation that still receives paper has a backlog of forms and someone typing them in.
This project puts vision-language models to work on that backlog: a frontier multimodal model
reading the scan, a 2B and a 4B open vision model fine-tuned to read it, and the classic OCR
pipelines beside them. Same pages, same fields, one grader. It reports every field read right or
wrong with confidence intervals, what each approach costs per thousand pages, how it holds up on
a form design it has never seen and on a bad scan, and the number a director wants: at 99
percent accuracy, how many fields still need a person.

## Result

<!-- results:start -->
Test sets, read once per arm, level 0 unless stated. Field accuracy is VRDU's own matchers, one grader for every arm; intervals are 95% bootstrap over documents. Frontier cost is the gateway ledger's at the 2026-10-16 price list, batch rate; OCR is costed at US$0.03 per vCPU-hour (RunPod, 2026-10-17). Written by `legible report`; do not edit.

**FARA registration forms, templates never seen in training (headline)**

| Arm | Fields correct (95% CI) | Every field right | Invented fields | Cost per 1,000 pages | Documents |
|---|---|---|---|---|---:|
| A, Claude Sonnet 5.5 on the image | 78.8% (77.5 to 80.0) | 31.4% (28.4 to 34.4) | 8.9% (8.1 to 9.7) | US$2.96 (2.95 to 2.97) | 900 |
| A, Claude Haiku 5.5 on the image | not yet measured |  |  |  | 0 |
| A, GPT-6.1 Sol on the image | not yet measured |  |  |  | 0 |
| A, Gemini 3.8 Flash on the image | not yet measured |  |  |  | 0 |
| D, Claude Sonnet 5.5 on the OCR text | 70.0% (68.3 to 71.8) | 22.3% (19.6 to 25.1) | 6.9% (6.2 to 7.7) | US$1.60 (1.58 to 1.62) | 900 |
| E, OCR plus rules | 14.2% (13.0 to 15.4) | 0.0% (0.0 to 0.0) | 0.2% (0.1 to 0.4) | US$0.02 (0.02 to 0.02) | 900 |
| B, Gemma 4 E2B fine-tuned on the image | 69.0% (67.2 to 70.7) | 29.6% (26.6 to 32.6) | 5.9% (5.2 to 6.6) | US$0.06 (0.06 to 0.06) | 900 |
| B, Gemma 4 E4B fine-tuned on the image | 66.8% (65.3 to 68.3) | 14.3% (12.1 to 16.6) | 13.2% (12.3 to 14.2) | US$0.07 (0.07 to 0.08) | 900 |
| C, Gemma 4 E2B untuned on the image | not yet measured |  |  |  | 0 |
| C, Gemma 4 E4B untuned on the image | not yet measured |  |  |  | 0 |

**DeepForm ad-buy forms, templates never seen in training (headline)**

| Arm | Fields correct (95% CI) | Every field right | Invented fields | Cost per 1,000 pages | Documents |
|---|---|---|---|---|---:|
| A, Claude Sonnet 5.5 on the image | 69.8% (65.4 to 74.2) | 0.6% (0.0 to 1.9) | 10.0% (7.7 to 12.4) | US$5.19 (4.94 to 5.45) | 159 |
| A, Claude Haiku 5.5 on the image | not yet measured |  |  |  | 0 |
| A, GPT-6.1 Sol on the image | not yet measured |  |  |  | 0 |
| A, Gemini 3.8 Flash on the image | not yet measured |  |  |  | 0 |
| D, Claude Sonnet 5.5 on the OCR text | 69.8% (65.1 to 74.4) | 1.3% (0.0 to 3.1) | 9.3% (7.2 to 11.7) | US$4.68 (4.37 to 5.01) | 159 |
| E, OCR plus rules | 13.7% (9.9 to 18.3) | 1.3% (0.0 to 3.1) | 0.8% (0.6 to 1.0) | US$0.05 (0.04 to 0.05) | 159 |
| B, Gemma 4 E2B fine-tuned on the image | 55.3% (48.5 to 62.0) | 1.3% (0.0 to 3.1) | 8.0% (6.0 to 10.3) | US$0.19 (0.17 to 0.21) | 159 |
| B, Gemma 4 E4B fine-tuned on the image | 59.6% (53.7 to 65.3) | 3.1% (0.6 to 6.3) | 7.6% (5.4 to 10.3) | US$0.19 (0.17 to 0.20) | 159 |
| C, Gemma 4 E2B untuned on the image | not yet measured |  |  |  | 0 |
| C, Gemma 4 E4B untuned on the image | not yet measured |  |  |  | 0 |

**CORD receipts, test set**

| Arm | Fields correct (95% CI) | Every field right | Invented fields | Cost per 1,000 pages | Documents |
|---|---|---|---|---|---:|
| A, Claude Sonnet 5.5 on the image | 84.0% (77.8 to 89.2) | 47.0% (37.0 to 57.0) | 3.4% (2.3 to 4.6) | US$5.27 (5.06 to 5.50) | 100 |
| A, Claude Haiku 5.5 on the image | not yet measured |  |  |  | 0 |
| A, GPT-6.1 Sol on the image | not yet measured |  |  |  | 0 |
| A, Gemini 3.8 Flash on the image | not yet measured |  |  |  | 0 |
| D, Claude Sonnet 5.5 on the OCR text | 36.2% (29.8 to 42.7) | 1.0% (0.0 to 3.0) | 2.0% (1.2 to 3.0) | US$5.97 (5.03 to 7.14) | 100 |
| E, OCR plus rules | 15.8% (11.9 to 19.8) | 0.0% (0.0 to 0.0) | 0.8% (0.1 to 1.9) | US$0.09 (0.04 to 0.15) | 100 |
| B, Gemma 4 E2B fine-tuned on the image | 75.2% (67.9 to 82.0) | 38.0% (29.0 to 48.0) | 1.0% (0.4 to 1.8) | US$0.11 (0.11 to 0.11) | 100 |
| B, Gemma 4 E4B fine-tuned on the image | 77.6% (71.5 to 83.3) | 30.0% (21.0 to 39.0) | 0.9% (0.4 to 1.5) | US$0.16 (0.16 to 0.16) | 100 |
| C, Gemma 4 E2B untuned on the image | not yet measured |  |  |  | 0 |
| C, Gemma 4 E4B untuned on the image | not yet measured |  |  |  | 0 |

**NIST tax forms, 500 test faces**

| Arm | Fields correct (95% CI) | Every field right | Invented fields | Cost per 1,000 pages | Documents |
|---|---|---|---|---|---:|
| A, Claude Sonnet 5.5 on the image | not yet measured |  |  |  | 0 |
| A, Claude Haiku 5.5 on the image | not yet measured |  |  |  | 0 |
| A, GPT-6.1 Sol on the image | not yet measured |  |  |  | 0 |
| A, Gemini 3.8 Flash on the image | not yet measured |  |  |  | 0 |
| D, Claude Sonnet 5.5 on the OCR text | not yet measured |  |  |  | 0 |
| E, OCR plus rules | 16.0% (14.6 to 17.4) | 0.0% (0.0 to 0.0) | 15.2% (14.1 to 16.3) | US$0.04 (0.04 to 0.05) | 500 |
| B, Gemma 4 E2B fine-tuned on the image | not yet measured |  |  |  | 0 |
| B, Gemma 4 E4B fine-tuned on the image | not yet measured |  |  |  | 0 |
| C, Gemma 4 E2B untuned on the image | not yet measured |  |  |  | 0 |
| C, Gemma 4 E4B untuned on the image | not yet measured |  |  |  | 0 |

**FARA, templates seen in training (the gap beside the headline)**

| Arm | Fields correct (95% CI) | Every field right | Invented fields | Cost per 1,000 pages | Documents |
|---|---|---|---|---|---:|
| A, Claude Sonnet 5.5 on the image | 74.2% (71.9 to 76.4) | 24.3% (19.7 to 29.0) | 12.6% (11.2 to 14.1) | US$2.97 (2.96 to 2.99) | 300 |
| A, Claude Haiku 5.5 on the image | not yet measured |  |  |  | 0 |
| A, GPT-6.1 Sol on the image | not yet measured |  |  |  | 0 |
| A, Gemini 3.8 Flash on the image | not yet measured |  |  |  | 0 |
| D, Claude Sonnet 5.5 on the OCR text | 64.8% (61.7 to 67.8) | 16.7% (12.7 to 21.0) | 8.5% (7.2 to 9.8) | US$1.64 (1.61 to 1.68) | 300 |
| E, OCR plus rules | 36.2% (33.6 to 38.9) | 1.0% (0.0 to 2.3) | 3.5% (2.6 to 4.4) | US$0.03 (0.02 to 0.03) | 300 |
| B, Gemma 4 E2B fine-tuned on the image | 75.7% (73.0 to 78.3) | 35.3% (30.0 to 40.7) | 7.8% (6.5 to 9.1) | US$0.06 (0.06 to 0.06) | 300 |
| B, Gemma 4 E4B fine-tuned on the image | 72.2% (69.7 to 74.7) | 22.7% (18.0 to 27.3) | 11.4% (10.0 to 12.9) | US$0.07 (0.07 to 0.08) | 300 |
| C, Gemma 4 E2B untuned on the image | not yet measured |  |  |  | 0 |
| C, Gemma 4 E4B untuned on the image | not yet measured |  |  |  | 0 |

**DeepForm, templates seen in training (the gap beside the headline)**

| Arm | Fields correct (95% CI) | Every field right | Invented fields | Cost per 1,000 pages | Documents |
|---|---|---|---|---|---:|
| A, Claude Sonnet 5.5 on the image | 71.8% (68.5 to 75.1) | 0.7% (0.0 to 1.7) | 8.4% (6.9 to 10.0) | US$5.14 (4.94 to 5.35) | 300 |
| A, Claude Haiku 5.5 on the image | not yet measured |  |  |  | 0 |
| A, GPT-6.1 Sol on the image | not yet measured |  |  |  | 0 |
| A, Gemini 3.8 Flash on the image | not yet measured |  |  |  | 0 |
| D, Claude Sonnet 5.5 on the OCR text | 71.6% (68.1 to 75.0) | 0.7% (0.0 to 1.7) | 8.2% (6.7 to 9.9) | US$4.63 (4.40 to 4.87) | 300 |
| E, OCR plus rules | 11.5% (8.9 to 14.4) | 0.7% (0.0 to 1.7) | 0.9% (0.7 to 1.1) | US$0.05 (0.04 to 0.05) | 300 |
| B, Gemma 4 E2B fine-tuned on the image | 60.2% (55.5 to 64.7) | 4.0% (2.0 to 6.3) | 7.2% (5.6 to 9.0) | US$0.17 (0.16 to 0.19) | 300 |
| B, Gemma 4 E4B fine-tuned on the image | 58.2% (53.0 to 63.2) | 6.3% (3.7 to 9.3) | 3.9% (2.7 to 5.3) | US$0.20 (0.18 to 0.21) | 300 |
| C, Gemma 4 E2B untuned on the image | not yet measured |  |  |  | 0 |
| C, Gemma 4 E4B untuned on the image | not yet measured |  |  |  | 0 |

**NIST, the 300 curve pages at each degradation level** (fields correct; what each level does to OCR is in [docs/degradation.md](docs/degradation.md))

| Arm | Level 0 | Level 1 | Level 2 | Level 3 | Level 4 |
|---|---|---|---|---|---|
| A, Claude Sonnet 5.5 on the image |  |  |  |  |  |
| A, Claude Haiku 5.5 on the image |  |  |  |  |  |
| A, GPT-6.1 Sol on the image |  |  |  |  |  |
| A, Gemini 3.8 Flash on the image |  |  |  |  |  |
| D, Claude Sonnet 5.5 on the OCR text |  |  |  |  |  |
| E, OCR plus rules | 16.2% (14.4 to 18.1) | 4.9% (4.2 to 5.7) | 4.5% (3.8 to 5.3) | 2.3% (1.9 to 2.8) | 0.5% (0.3 to 0.7) |
| B, Gemma 4 E2B fine-tuned on the image |  |  |  |  |  |
| B, Gemma 4 E4B fine-tuned on the image |  |  |  |  |  |
| C, Gemma 4 E2B untuned on the image |  |  |  |  |  |
| C, Gemma 4 E4B untuned on the image |  |  |  |  |  |

**Review at 99%: Sonnet 5.5 on the image, each field checked against Sonnet 5.5 on the OCR text.** A field is accepted when the two reads agree; the threshold is chosen on dev and applied once to test (legible/review.py, legible/agreement.py).

| Corpus | Fields sent to a person (95% CI) | Accuracy of the fields accepted | Reached 99% on dev |
|---|---|---|---|
| FARA, unseen templates | 100.0% (100.0 to 100.0) | nan% (nan to nan) | no: every field reviewed |
| DeepForm, unseen templates | 100.0% (100.0 to 100.0) | nan% (nan to nan) | no: every field reviewed |
| CORD | 100.0% (100.0 to 100.0) | nan% (nan to nan) | no: every field reviewed |
| NIST | not yet measured | | |

Arms B and C read through vLLM on an RTX 3090, held to the schema's JSON, and are costed at the GPU's US$0.50 an hour over the measured wall time of each read pass. B's row is seed 0, the model trained for that table's split; seeds 1 and 2 are the training variance. Not yet measured: latency, which batch reads do not give.
<!-- results:end -->

## What this does not do

It does not read handwriting, long multi-page documents or forms whose type is unknown. It
sends public records and public datasets to model vendors and nothing else; the registration
forms it reads name individuals, so they appear here as numbers and never as images. It does not
take uploads. Nothing is modelled in the browser.

## How it works

Three public corpora (US Department of Justice registration forms and FCC advertising order
forms from Google's VRDU benchmark, CORD receipts, and NIST's synthesised tax forms) are
rasterised, split so that held-out templates stay held out, and degraded in five reproducible
steps. Five arms read the same pages and one programmatic grader scores every field, with
intervals over documents and paired deltas between arms. The fine-tuned arm is Gemma 4 E2B and
E4B with QLoRA on the page images; every model call, frontier and self-hosted, goes through the
portfolio's gateway so cost per page has one ledger; the release gate from project 03 decides
non-inferiority. The design, the data terms and the week-by-week order are in [PLAN.md](PLAN.md);
the diagrams are in [docs/architecture.md](docs/architecture.md).

## Part of a portfolio

One of sixteen projects on [peterparker.ca](https://peterparker.ca), each of which ends in a
measured result a stranger can reproduce from its repository with one command. This one reuses
the gateway from [Inside the Boundary, On the Record](https://github.com/Peter-A-P/compliant-ai-gateway),
the release gate from [AI Release Gate](https://github.com/Peter-A-P/ai-release-gate) and the
fine-tuning recipe from [Frontier Quality at a Fraction of the Bill](https://github.com/Peter-A-P/fraction-of-the-bill).

## How this was built

The design, the methodology and the judgement calls are Peter Parker's. AI coding assistants
were used for implementation. Every number in this repository is reproducible with one command,
and the plan was written before the first line of code so that the result could not be shaped
to fit.
