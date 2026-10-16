# Forms That Read Themselves

Vision-language models on the backlog of paper forms, measured on more than 9,000 public pages
with known answers: a frontier multimodal model, a 2B and a 4B open vision model fine-tuned on
page images, and the classic OCR pipelines. Every field right or wrong with its interval, the
cost per thousand pages, what breaks on an unseen form design or a bad scan, and how many fields
a person still checks at 99 percent accuracy.

Every organisation that still receives paper has a backlog of forms and someone typing them in.
This project puts vision-language models to work on that backlog: a frontier multimodal model
reading the scan, a 2B and a 4B open vision model fine-tuned to read it, and the classic OCR
pipelines beside them. Same pages, same fields, one grader. It reports every field read right or
wrong with confidence intervals, what each approach costs per thousand pages, how it holds up on
a form design it has never seen and on a bad scan, and the number a director wants: at 99
percent accuracy, how many fields still need a person.

## Result

Plan only. Nothing has been measured yet. The columns the benchmark will fill:

| Arm | Corpus | Fields correct (95% CI) | Every field right | Unseen templates | At degradation level 3 | Hallucinated fields | Review rate at 99% | Cost per 1,000 pages | p99 per page |
|---|---|---|---|---|---|---|---|---|---|
| | | | | | | | | | |

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
