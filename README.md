# Forms That Read Themselves

Every organisation that still receives paper has a backlog of forms and someone typing them in.
This project measures, on thousands of public forms with known answers, the ways a machine can
do the typing instead: a frontier vision model reading the scan, a small open model fine-tuned
to read it, the classic OCR pipeline with rules, and OCR text handed to a language model. Same
pages, same fields, same grader. It reports what each gets right, what it costs a thousand
pages, what happens when the form is one the model has never seen or the scan is bad, and how
many fields a person still has to check.

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
