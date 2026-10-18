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
| A, Claude Sonnet 5.5 on the image | not yet measured |  |  |  | 0 |
| A, Claude Haiku 5.5 on the image | not yet measured |  |  |  | 0 |
| A, GPT-6.1 Sol on the image | not yet measured |  |  |  | 0 |
| A, Gemini 3.8 Flash on the image | not yet measured |  |  |  | 0 |
| D, Claude Sonnet 5.5 on the OCR text | not yet measured |  |  |  | 0 |
| E, OCR plus rules | 14.2% (13.0 to 15.4) | 0.0% (0.0 to 0.0) | 0.2% (0.1 to 0.4) | US$0.02 (0.02 to 0.02) | 900 |

**DeepForm ad-buy forms, templates never seen in training (headline)**

| Arm | Fields correct (95% CI) | Every field right | Invented fields | Cost per 1,000 pages | Documents |
|---|---|---|---|---|---:|
| A, Claude Sonnet 5.5 on the image | not yet measured |  |  |  | 0 |
| A, Claude Haiku 5.5 on the image | not yet measured |  |  |  | 0 |
| A, GPT-6.1 Sol on the image | not yet measured |  |  |  | 0 |
| A, Gemini 3.8 Flash on the image | not yet measured |  |  |  | 0 |
| D, Claude Sonnet 5.5 on the OCR text | not yet measured |  |  |  | 0 |
| E, OCR plus rules | 13.7% (9.9 to 18.3) | 1.3% (0.0 to 3.1) | 0.8% (0.6 to 1.0) | US$0.05 (0.04 to 0.05) | 159 |

**CORD receipts, test set**

| Arm | Fields correct (95% CI) | Every field right | Invented fields | Cost per 1,000 pages | Documents |
|---|---|---|---|---|---:|
| A, Claude Sonnet 5.5 on the image | not yet measured |  |  |  | 0 |
| A, Claude Haiku 5.5 on the image | not yet measured |  |  |  | 0 |
| A, GPT-6.1 Sol on the image | not yet measured |  |  |  | 0 |
| A, Gemini 3.8 Flash on the image | not yet measured |  |  |  | 0 |
| D, Claude Sonnet 5.5 on the OCR text | not yet measured |  |  |  | 0 |
| E, OCR plus rules | 15.8% (11.9 to 19.8) | 0.0% (0.0 to 0.0) | 0.8% (0.1 to 1.9) | US$0.09 (0.04 to 0.15) | 100 |

**NIST tax forms, 500 test faces**

| Arm | Fields correct (95% CI) | Every field right | Invented fields | Cost per 1,000 pages | Documents |
|---|---|---|---|---|---:|
| A, Claude Sonnet 5.5 on the image | not yet measured |  |  |  | 0 |
| A, Claude Haiku 5.5 on the image | not yet measured |  |  |  | 0 |
| A, GPT-6.1 Sol on the image | not yet measured |  |  |  | 0 |
| A, Gemini 3.8 Flash on the image | not yet measured |  |  |  | 0 |
| D, Claude Sonnet 5.5 on the OCR text | not yet measured |  |  |  | 0 |
| E, OCR plus rules | 16.0% (14.6 to 17.4) | 0.0% (0.0 to 0.0) | 15.2% (14.1 to 16.3) | US$0.04 (0.04 to 0.05) | 500 |

**FARA, templates seen in training (the gap beside the headline)**

| Arm | Fields correct (95% CI) | Every field right | Invented fields | Cost per 1,000 pages | Documents |
|---|---|---|---|---|---:|
| A, Claude Sonnet 5.5 on the image | not yet measured |  |  |  | 0 |
| A, Claude Haiku 5.5 on the image | not yet measured |  |  |  | 0 |
| A, GPT-6.1 Sol on the image | not yet measured |  |  |  | 0 |
| A, Gemini 3.8 Flash on the image | not yet measured |  |  |  | 0 |
| D, Claude Sonnet 5.5 on the OCR text | not yet measured |  |  |  | 0 |
| E, OCR plus rules | 36.2% (33.6 to 38.9) | 1.0% (0.0 to 2.3) | 3.5% (2.6 to 4.4) | US$0.03 (0.02 to 0.03) | 300 |

**DeepForm, templates seen in training (the gap beside the headline)**

| Arm | Fields correct (95% CI) | Every field right | Invented fields | Cost per 1,000 pages | Documents |
|---|---|---|---|---|---:|
| A, Claude Sonnet 5.5 on the image | not yet measured |  |  |  | 0 |
| A, Claude Haiku 5.5 on the image | not yet measured |  |  |  | 0 |
| A, GPT-6.1 Sol on the image | not yet measured |  |  |  | 0 |
| A, Gemini 3.8 Flash on the image | not yet measured |  |  |  | 0 |
| D, Claude Sonnet 5.5 on the OCR text | not yet measured |  |  |  | 0 |
| E, OCR plus rules | 11.5% (8.9 to 14.4) | 0.7% (0.0 to 1.7) | 0.9% (0.7 to 1.1) | US$0.05 (0.04 to 0.05) | 300 |

**NIST, the 300 curve pages at each degradation level** (fields correct; what each level does to OCR is in [docs/degradation.md](docs/degradation.md))

| Arm | Level 0 | Level 1 | Level 2 | Level 3 | Level 4 |
|---|---|---|---|---|---|
| A, Claude Sonnet 5.5 on the image |  |  |  |  |  |
| A, Claude Haiku 5.5 on the image |  |  |  |  |  |
| A, GPT-6.1 Sol on the image |  |  |  |  |  |
| A, Gemini 3.8 Flash on the image |  |  |  |  |  |
| D, Claude Sonnet 5.5 on the OCR text |  |  |  |  |  |
| E, OCR plus rules | 16.2% (14.4 to 18.1) | 4.9% (4.2 to 5.7) | 4.5% (3.8 to 5.3) | 2.3% (1.9 to 2.8) | 0.5% (0.3 to 0.7) |

Not yet measured: the fine-tuned and untuned small models (arms B and C), the review rate at 99%, and latency, which batch reads do not give.
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
