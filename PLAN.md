# Plan: Forms That Read Themselves

**Written:** 2026-10-16. **Status (2026-10-28):** every arm measured on every test set, arm F
added 2026-10-24, every subset read, the README's tables filled by `legible report`,
forms.peterparker.ca live, the six non-FARA adapters public on Hugging Face, the three
ablations measured (ten of eleven runs read; 1,120 tokens, the whole training set and one model
per corpus stay the recipe). Still to do: `v0.1.0` and the repository public. The checklist is section 11.
**Build:** three weeks of evenings and weekends, starting when this plan is approved; the
weeks in section 6 are relative, not dated. **Package:** `legible`. **Repository:**
`scanned-form-extraction`.
**Fed by:** 04 (every model call, frontier and self-hosted, goes through the `boundary`
gateway with `data_class=public`, so cost per page has one ledger), 03 (the gate runs the
non-inferiority comparison between the fine-tuned model and the frontier arm, with intervals
from 02), 06 (the QLoRA recipe, the bases, the GPU price table and the break-even arithmetic),
07 (the OCR and page-rendering choices from its scanned track). **Feeds:** 07 (the scan
degradation pipeline and the per-level OCR quality measurement, for its scanned track), 04
(its first image-bearing ledger rows and per-image price entries).

This is the portfolio's first project on pixels rather than text: it reads scanned pages,
trains a model that looks at them, and publishes what each way of reading a form gets right, what it gets wrong, what it costs a
thousand pages, and how many fields a person still has to check.

---

## 1. What this produces

Every organisation that still receives paper has a backlog of forms, and someone typing them in.
This project measures the ways a machine can do the typing instead, on public forms with known
answers: a frontier vision model reading the scan, a small open model fine-tuned to read it, the
classic optical-character-recognition pipeline with rules, and OCR text handed to a language
model. Same pages, same fields, same grader. It reports accuracy per field with intervals, the
cost per thousand pages from one ledger, what happens when the form is a template the model has
never seen, what happens as the scan gets worse, and the number a director wants: at a target
accuracy, how many fields still go to a person.

The numbers a stranger can check:

| Number | What it shows |
|---|---|
| Field-level accuracy per arm (frontier vision models, fine-tuned small vision models, their untuned bases, OCR plus rules, OCR text plus a language model) on identical held-out pages, per corpus, with 95% bootstrap intervals over documents and paired deltas between arms | The quality axis, on identical items, with no model grading another |
| Document-level "every field right" rate per arm | What a clerk experiences: a form that needs no correction |
| Accuracy on templates the model never saw against templates it trained on (VRDU's unseen-template split), per arm | Whether the result survives a new form design, which is where rules-based extraction dies |
| Accuracy against scan degradation level 0 to 4 (resolution, blur, skew, noise, compression), per arm, as a curve with intervals | Where each approach breaks, and which breaks first |
| Hallucination rate: fields filled when the truth is blank, and fields invented when the page does not carry them | The failure that matters most in a form a person trusts |
| Review rate at a target field accuracy (99 percent): the share of fields that must be routed to a person so the accepted fields hit the target, from each arm's confidence, thresholds chosen on dev and measured on test | The product number: of a thousand pages, how much human work is left |
| Cost per 1,000 pages: frontier from the gateway ledger, self-hosted from the GPU-hour price at measured throughput and stated utilisation, OCR from CPU time | The cost axis, in dollars, with the price list date |
| Non-inferiority of the best fine-tuned size against the best frontier arm, per corpus, through the 03 gate with a stated delta and the interval shown | Whether "a model you own reads it as well" is true, and for which corpus |
| Break-even monthly page volume as a function of utilisation, with the inputs published | The one number for the owner of the backlog, reusing 06's arithmetic |
| Latency per page, p50 and p99, per arm | Whether it keeps up with the counter or runs overnight |

## 2. Design decisions

### 2.1 Three corpora, one grader, truth known in advance

Three public corpora with field-level labels, chosen so the labels cost nothing and so that a
stranger can download the same pages:

- **VRDU Registration Forms**: 1,915 Foreign Agents Registration Act forms from the US
  Department of Justice, three templates, a handful of simple fields. The clean case.
- **VRDU Ad-buy Forms**: 641 political advertising order forms from FCC public files, dozens
  of templates, more than a dozen fields including nested and repeated line items. The hard
  case, and the one with the unseen-template split built in.
- **CORD receipts**: 1,000 photographed Indonesian receipts with 30 field classes including
  line items, subtotals and totals, CC BY 4.0. The receipts track Peter asked for, and the
  one with arithmetic the verifier can check.
- **NIST Special Database 2**: 5,590 binary scans of synthesised 1988 IRS 1040-package forms,
  12 form types, 900 simulated submissions, every field's answer in a text file. Free from
  NIST, and public domain: NIST confirmed on 2026-10-17 that SD2 is not subject to copyright
  protection, not the Standard Reference Data regime (`docs/data.md`).
  The volume track and the degradation track: labels known by construction, templates known,
  pages plentiful enough to train on and to degrade without touching the headline sets.

Grading is programmatic, field by field, with VRDU's own type-specific matchers (date,
numeric, price, string after normalisation) extended to CORD and NIST, and every miss
classified by name: wrong field, wrong value, blank filled, value invented, malformed. No
model grades another model, which is the 03 and 06 principle. Intervals are bootstrapped over
documents rather than fields, because a form's fields are not independent; paired deltas
refuse two runs that did not grade identical items (06's grader rule, carried over).

### 2.2 Five arms on the same pages

| Arm | What it is | Why it is here |
|---|---|---|
| A. Frontier vision | A page image and a schema in, JSON out, from one Anthropic, one OpenAI and one Google model through the 04 gateway, plus the cheapest Anthropic model as the cost anchor and the most expensive on a subset as the ceiling. Structured output where the vendor supports it | The bar, and the cost anchor the owner of a backlog would reach for first |
| B. Fine-tuned small vision | Gemma 4 E2B and E4B, QLoRA with images, trained per corpus on the training split, served on a rented GPU through the gateway | The deep-learning point and the ownership argument, 06's shape on pixels |
| C. Untuned small vision | The same bases zero-shot and few-shot | What the fine-tune is worth (section 10, candidate 2) |
| D. OCR text plus language model | Tesseract output with word positions rendered as positioned text, read by the same frontier model as arm A | Whether seeing the page beats reading its text (section 10, candidate 1); the pipeline most organisations already have |
| E. OCR plus rules | Tesseract plus per-template anchors and regular expressions, written for the templates in the training split | The free baseline, and the demonstration that it dies on a template it has not met (section 10, candidate 3) |
| F. Managed document AI (added 2026-10-24) | Azure AI Document Intelligence: the prebuilt receipt model on CORD; a custom neural model per training split on FARA and DeepForm (trained on the same training documents as arm B, read on the templates it never saw) and per NIST face. Through the gateway | The product a buyer is quoted first; whether a managed custom model beats a fine-tune you own, and at what price per page |

Arm A's exact model identifiers are chosen on day one from 04's current price file and recorded
in `docs/models.md` with the date, the 03 pattern. Images go to the vendors as content blocks
inside an ordinary `ChatRequest`; the gateway passes vendor-shaped blocks through untouched and
accepts non-text content under the `public` data class, so no change to 04 is needed. Every
page sent is a public record or a public dataset, and the declaration is true.

### 2.3 The fine-tune is 06's recipe with a vision encoder

Gemma 4 E2B and E4B are 06's small and middle bases, Apache 2.0, image input, with a visual
token budget the model card documents (70 to 1,120 tokens; the top of the range is what the
card recommends for OCR and document parsing). QLoRA on the 4-bit base with PEFT, rank 16,
vision encoder frozen, language layers and the projector trained; ablations on the visual token
budget (1,120 against 560, because it halves the cost per page if it holds), on data volume
(all training pages, half, a quarter), and three seeds on the final configuration so the
intervals include training variance. One fine-tune per corpus per size, plus one model trained
on all three corpora as an ablation. Checkpoints to object storage from the first step; spot
GPUs; the day-one GPU price table and provider rule from 06 (`docs/gpu-prices.md`, cloud spot if
within 20 percent of the marketplace, otherwise the marketplace, the README says which).

Changed 2026-10-26, before any ablation was trained: the ablations run on E2B at seed 0, each
against the seed-0 E2B already measured. The headline fine-tunes were trained and gated at
1,120 tokens before the 560 ablation ran, the reverse of the order section 9 planned, so if
560 holds it is reported as the cheaper recipe beside them rather than retrained into the
headline. The data-volume curve is all, half and a quarter of what each model trained on: for
NIST that is 800, 400 and 200 faces, since its full 3,850 ran at nineteen hours a run and was
cut to 800 (`docs/training.md`), and the curve is run on CORD too (800, 400, 200 receipts).
The multi-corpus model learns FARA and DeepForm from their mixed-template training sets, CORD
and NIST's 800 faces in one run; one model cannot hold out each FARA template the way the
unseen-template specialists do, so it is compared with the mixed-template specialists on the
mixed-template tables, and with the specialists on CORD and NIST.

Measured 2026-10-28 (the README's ablation tables, `docs/training.md`): 560 tokens did not
hold, 3.6 to 10.0 points down on FARA, DeepForm and CORD for a few cents a thousand pages
(`docs/rejected.md`), so 1,120 stays; accuracy falls at half and a quarter of the training set
on CORD and NIST; the multi-corpus model gains 6.9 points on FARA and loses on DeepForm and
NIST, so one model per corpus stays. NIST at 560 tokens was trained and not read.

Corrected 2026-10-16, once the split files were read: "one fine-tune per corpus per size" is
not enough for FARA. Its unseen-template level is three split files per seed, each holding out
a different template, and a model trained on one has seen the templates the others hold out.
So FARA's unseen numbers take three fine-tunes per size per seed, one per held-out template;
DeepForm's take one per seed; the mixed level one per corpus per seed. The FARA training sets
are 200 two-page forms, so each run is short; the GPU estimate in section 7 moves by a few
hours, not by a line. The gate decides on seed 0's files, with seeds 1 and 2 reported beside
it as training variance.

What is deliberately reused from 06 rather than rebuilt: the training loop's checkpointing, the
merge step, the serving launcher, the load client and the break-even arithmetic. `smallprint`
is public; where a module imports cleanly it is imported at a pinned tag, where it would drag
in the EDGAR stack it is copied with the commit recorded in the file's header.

### 2.4 Unseen templates are the headline, not the footnote

VRDU defines three task levels: single template, mixed templates, and unseen templates. The
headline numbers for the VRDU corpora are on the unseen-template split, because a form
extraction system that only works on the forms it was trained on is a rules engine with extra
steps, and because that is the split where arm E collapses and arm A does not, which is the
point of the comparison. The mixed-template number is reported beside it as the gap. NIST has
twelve fixed templates, so it carries no unseen-template claim; it carries the degradation
curve and the data-volume curve instead. CORD has no templates; its receipts vary freely.

### 2.5 Degradation is applied, measured and published

Every corpus is rasterised at 300 dpi to level 0. Levels 1 to 4 apply, cumulatively,
downsampling toward 100 dpi, Gaussian blur, skew of up to 3 degrees, salt-and-pepper noise
and JPEG recompression, with the parameters in `legible/degrade.py` and a fixed seed so the
degraded set is reproducible byte for byte. The levels are calibrated once, by Tesseract word
accuracy on the NIST clean pages, so that "level 3" means a stated OCR word error rate rather
than a parameter list. Each arm is measured on the same 300 NIST pages at every level, and on
a 150-page VRDU subset at levels 0, 2 and 4. The curve is the result 07's scanned track
inherits.

### 2.6 Confidence, review rate and the verifier

The fine-tuned arm emits a per-field confidence from its token log-probabilities. The frontier
arms are asked for none; their confidence is the agreement between the vision read and the OCR
text read of the same page (arms A and D), which costs nothing extra because both are run
anyway. For each arm the threshold is chosen on the dev split to hit 99 percent accuracy on the
accepted fields and the review rate is then measured on test, so the number is honest about
how many fields a person still checks. A verifier runs after extraction wherever the form
defines arithmetic or a format: receipt line items sum to the subtotal and subtotal plus tax to
the total, dates parse, registration numbers match their pattern, 1040 lines that the form
defines as sums are sums. The share of errors the verifier catches is reported; it is a cheap
layer and the number says how cheap.

Revised 2026-10-20: the fine-tuned arm's reads were taken without log-probabilities, so its
seed-0 headline models (both sizes; FARA's three held-out templates, DeepForm's unseen split,
CORD and NIST) read their level-0 dev and test documents a second time with them, at
temperature 0, into a run kept apart from the first (`legible/tokenconf.py`, `--logprobs`).
That is a second read of those test sets, decided by Peter on 2026-10-20 over dropping arm B's
review rate. It tunes nothing on test: the model and prompt are the ones already read, the
threshold is chosen on the second dev read, and the accuracy tables keep the first test read.
A field's confidence is the lowest probability among the tokens of its value.

### 2.7 Serving, cost and break-even through one ledger

The fine-tuned models are served with vLLM where its multimodal support covers Gemma 4 on the
day, otherwise with batched Transformers generation, on the same rented GPU class, registered
with the gateway as a host whose price entry is the GPU-hour rate divided by measured pages per
hour, so self-hosted cost per page comes out of the same ledger as the frontier cost. The
closed-loop load client from 06 runs at concurrency 1, 8 and 32 with real pages. Break-even is
published as a curve over utilisation with every input in a table, 06's arithmetic and 06's
staircase.

### 2.8 The demo shows results, and models nothing

forms.peterparker.ca is a static site on Azure Static Web Apps, the 01 and 08 pattern: a page
viewer that draws each arm's field reads on the page image, right in green and wrong in red with
the truth beside them; a degradation slider that steps the same page through levels 0 to 4 and
shows accuracy falling per arm; the cost and review-rate tables. Nothing is modelled in the
browser and nothing is uploaded. Page images shown are NIST (synthetic), CORD (CC BY 4.0) and
VRDU ad-buy forms (business documents from FCC public files); registration forms, which name
individuals, appear in the tables only.

### 2.9 Out of scope, on purpose

- Handwriting. NIST SD6 has 5,595 hand-printed pages with the same forms; it is the natural
  second corpus and it is deferred, because the machine-print result has to stand first.
- Long multi-page documents, table-of-contents navigation, cross-page reasoning. A form is a
  page or a few; 05 owns long documents.
- A layout-model arm (LayoutLM class). It needs OCR boxes as input and has been overtaken by
  vision-language models on exactly these benchmarks; it would be a dated point on the chart.
- A live upload demo. Costs money per visit, needs abuse limits, and a stranger's form is not
  public-class data, which 04 refuses for images. A different project.
- Training above E4B. The argument is that a small model you own suffices, as in 06.
- Document classification and routing. The form type is given; identifying it is a cheap
  classifier that would add nothing the extraction number does not already say.

## 3. Data

| Source | Size | What it gives | Access and terms |
|---|---|---|---|
| VRDU Registration Forms (Google Research, 2023) | 1,915 documents, PDFs, OCR output and annotations in `dataset.jsonl`, few-shot splits for three task levels | Three-template government forms with simple fields, human-annotated | Public records from justice.gov/nsd-fara; benchmark released by Google under CC BY 4.0, stated only by a hyperlink in Google's release post: the repository has no licence file (`docs/data.md`, read 2026-10-16) |
| VRDU Ad-buy Forms | 641 documents, same layout | Dozens of templates, nested and repeated fields, the unseen-template split | Public records from FCC public files; same licence note |
| CORD v2 (Clova AI) | 1,000 receipts: 800 train, 100 dev, 100 test, photographs with box-level annotation and 30 field classes | The receipts track; arithmetic for the verifier | CC BY 4.0, on Hugging Face |
| NIST Special Database 2 | 5,590 binary page images, 12 IRS form types from the 1988 1040 package, 900 simulated submissions, field answers as text files | Volume for training, labels by construction, the degradation and data-volume tracks | Free download from NIST with an MD5 list of the files inside the archive; the users' guide (February 2017) documents the field files. Public domain, confirmed by NIST on 2026-10-17: of the two regimes on NIST's licence page, the title 17 section 105 one, not Standard Reference Data |
| SROIE (ICDAR 2019) | 1,000 English receipts | Considered for the receipts track | Not used unless its terms are found and permit it: the competition pages state no licence. CORD carries the receipts track; SROIE is an optional second receipts set if its terms are confirmed on day one |

Dataset construction: every corpus is fetched by a loader that verifies a recorded checksum,
rasterised at 300 dpi, and stored under `data/pages/` with a manifest. Nothing raw is
committed; the manifest and checksums are. Splits: VRDU uses the benchmark's own split files
so the unseen-template claim means what the benchmark means (train size 200 at its three seeds,
decided 2026-10-16; each arm reads the union of the test sets once, `docs/data.md`); CORD uses its published split;
NIST is split by simulated submission so no submission's pages appear in both train and test,
with a leakage check that runs on every build. A dev split is carved from each training split
for threshold selection and prompt iteration, so the test sets are touched once per arm. A hand
audit of 200 labels across the corpora (VRDU and CORD are human-annotated; NIST's are by
construction) is done before the first frontier run and its disagreement rate is published.

Personal data: FARA registration forms name individuals and sometimes their addresses. They
are public records published by the Department of Justice for exactly that purpose, and the
benchmark has carried them since 2023. They are sent to vendors as `public` under 04's data
policy, which is true; they are not shown as images on the demo; and the repository does not
redistribute them, it fetches them from the benchmark's own source.

## 4. Methods and architecture

See `docs/architecture.md` for the diagrams. The package:

```
legible/
  data/        fetch.py (loaders with checksums for VRDU, CORD, NIST), render.py (PDF and TIFF to
               300 dpi pages), manifest.py, split.py (benchmark splits, NIST by submission, dev carve-out,
               leakage check), audit.py (the 200-label hand audit protocol and its report)
  schema/      one schema per corpus (pydantic): field names, types, matchers, nesting for line items;
               the prompt, the training target and the grader all read from it and refuse to load if
               they drift apart
  degrade.py   levels 0 to 4, fixed seed, parameters in one table
  calibrate.py measures Tesseract word accuracy per level on NIST from the stored OCR, and
               `legible calibrate` writes docs/degradation.md (moved out of degrade.py, which
               the OCR code imports, so the calibration can read stored OCR without a cycle)
  grade.py     field-level grader with type-specific matchers, miss taxonomy, document-level all-right,
               hallucination counts; bootstrap over documents; paired deltas that refuse mismatched items
  arms/        frontier.py (image block plus schema through the gateway, structured output where offered,
               batch submission where offered), ocr.py (Tesseract with hOCR, positioned-text rendering),
               rules.py (per-template anchors and patterns), ocrllm.py (positioned text to the same
               frontier model), small.py (untuned and fine-tuned Gemma 4 inference, logprob confidence)
  train/       dataset.py (page plus instruction to JSON target), qlora.py (PEFT, vision encoder frozen,
               checkpoint to object storage every N steps), ablate.py (token budget, data volume, seeds),
               merge.py
  serve/       vllm.py or hf.py launcher, gateway host registration, price entry from GPU rate and
               measured pages per hour
  review.py    confidence thresholds on dev, review rate at a target accuracy on test, agreement rule for
               the frontier arms
  verify.py    arithmetic and format checks per schema; share of errors caught
  bench/       load.py (closed-loop client, concurrency sweep, p50 and p99), cost.py (per 1,000 pages from
               the ledger and GPU rates), breakeven.py (06's utilisation curve, imported or vendored with
               the commit recorded)
  gate/        eval spec and outcome files for the 03 gate; the non-inferiority run per corpus
  report/      tables, the degradation chart, model cards, the site's JSON
  site/        the static viewer: page images, boxes, the slider, the tables; built by legible site
  cli.py       legible data fetch | build | degrade | run <arm> | train | serve | bench | review | gate | report | site
tests/         grader fixtures (nested line items, blank truth, invented values, date and price formats);
               schema round-trip and drift refusal; degradation determinism (same seed, same bytes);
               split leakage (no NIST submission across splits, VRDU templates disjoint on the unseen split);
               confidence threshold arithmetic; verifier rules against hand-built receipts; price entry
               reproduces cost per page from GPU rate and throughput
docs/          architecture.md, models.md (arm A identifiers and arm B bases with licences and dates),
               gpu-prices.md, degradation.md (the calibration), data.md (licences, counts, audit),
               rejected.md (the rejected approach), cards/ (one per published adapter)
```

### Tests that matter

The grader against adversarial fixtures: a nested line item in the wrong order, a blank truth
with a filled prediction, a price with a thousands separator, a date in three formats, a value
present on the page but outside the schema. The schema drift test: the prompt, the training
target and the grader built from one definition, and a load that fails if any of them names a
field the others do not. The degradation determinism test: level 3 of a page is byte-identical
across runs. The split tests: no NIST submission in two splits, and the unseen-template split's
train and test template sets disjoint. The review-rate arithmetic on a synthetic confidence
stream with a known answer. The gateway price entry for a served model reproduces cost per page
from GPU rate and measured throughput.

## 5. Interfaces with the rest of the portfolio

| Project | What crosses the line |
|---|---|
| 04 | Every call goes through `boundary` with `purpose` per arm, `run_id` per evaluation run and `data_class=public`; batch submission where the vendor offers it; the self-hosted models registered as hosts with a price entry. The ledger gains its first image-bearing rows and the first per-image price entries, which 04 records at its next price-file date |
| 03 | The gate's `outcomes_file` adapter: one spec per corpus and level (`gate-runs/specs/`), one suite per field and per line-item column, one outcome per document, a stated delta of 3 points, the ledger record written to this repository. A suite holds the documents where either side scored the field, so blank-for-both documents cannot pull the difference towards zero (`legible/gate.py`) |
| 06 | The bases, the QLoRA loop, checkpointing, merge, the serving launcher, the load client and the break-even arithmetic, imported at a pinned tag or vendored with the commit recorded |
| 07 | Hands over `legible.degrade` and `docs/degradation.md`: a reproducible way to make a scan worse by a stated amount and the OCR word accuracy at each level, which 07's scanned track reports its results against |

## 6. Week by week

Relative weeks of evenings and weekends, in order; the build starts when the plan is approved.

| Week | Built | Done when |
|---|---|---|
| 1 | Licences recorded in `docs/data.md`; loaders with checksums; rasterisation; schemas per corpus; grader with fixtures; splits and the leakage check; the 200-label audit; degradation pipeline and its Tesseract calibration; arm E rules for the training-split templates; arm D; arm A on every test set through the gateway (batch where offered), with repeats on 200 pages for the noise floor; cost per 1,000 pages for A, D and E | Every frontier and OCR number in section 1 filled with intervals; `docs/models.md` and `docs/degradation.md` written |
| 2 | GPU price table and provider decision; QLoRA on E2B and E4B per corpus, token-budget and data-volume ablations, the multi-corpus run, three seeds on the final configurations; arm C; evaluation on the unseen-template, degradation and receipts sets; serving, load test, self-hosted cost per 1,000 pages; the 03 gate run per corpus | The fine-tuned rows and the non-inferiority results filled; adapters published with cards |
| 3 | Confidence and review rate per arm; the verifier and its catch rate; break-even curve; the static site with the viewer and the slider; README tables from `legible report`; `docs/rejected.md`; `v0.1.0`; repository public; forms.peterparker.ca live; the status flip logged on peterparker.ca | Every number in section 1 in the README with its interval; the site live |
| slack | One week | |

First to drop if behind: the multi-corpus fine-tune, then the ceiling model on the subset, then
the third seed, then the VRDU degradation subset (NIST's curve stays). None is in the definition
of done. The five arms on the three corpora, the unseen-template numbers, the NIST degradation
curve, the review rate and the cost per 1,000 pages are not droppable.

## 7. Cost

Prices as of 2026-10-16. Anthropic list prices per million tokens: Haiku 5.5 at US$0.10 in and
US$0.50 out, Sonnet 5.5 at US$2 and US$10, Opus 5.5 at US$4 and US$20; message batches at
half. A page resized to 1,568 pixels on its long edge costs about 2,460 visual tokens on
Claude (28-pixel patches), plus about 400 tokens of instruction and schema and about 300
tokens of JSON out. Google lists Gemini 3 Flash at US$0.50 per million input tokens with an
image counted as 258 tokens. The OpenAI model's price is read from 04's price file on the day.
GPU rates as 06 recorded them: L4 or 4090 class about US$0.30 to 0.50 an hour, A100 40 GB about
US$0.90 to 1.30.

Pages per full arm: about 1,500 VRDU test pages across both corpora, 100 CORD test receipts,
500 NIST clean pages, 1,200 NIST degraded pages (300 at four levels), 450 VRDU degraded pages,
plus 400 repeat pages for the noise floor: about 4,100 page calls.

Measured 2026-10-16, once the corpora were built (`manifests/*-splits.json`): the VRDU documents
are multi-page, and the union of the headline test sets is 2,128 FARA pages and 774 DeepForm
pages, about 2,900 rather than 1,500. With the rest unchanged a full arm is about 5,500 pages,
some 35 percent over the table below: the Anthropic quality model's line is nearer US$24 than
US$18. The total stays inside the US$90 monthly cap set in 04 that day, and each corpus is its
own run, so no run comes near the US$25 per-run cap.

Revised 2026-10-16 with the models chosen that day (`docs/models.md`) and the measured page
count, about 5,500 pages a full arm, at the batch rate and the same tokens per page:

| Item | Model | US$ |
|---|---|---:|
| Arm A, quality | Claude Sonnet 5.5 | 24 |
| Arm A, cost anchor | Claude Haiku 5.5 | 1 |
| Arm A, ceiling on 600 pages | Claude Fable 5.1 (the most expensive model; the plan had Opus-class); Claude Opus 5.5 from 2026-10-22, about US$10 | 13 |
| Arm A, Google | Gemini 3.8 Flash, before its 2027-01-01 price rise | 6 |
| Arm A, OpenAI | GPT-6.1 Sol | 24 |
| Arm D, OCR text to the quality model | Claude Sonnet 5.5 | 17 |
| **API total** | | **85** (CA$115) |

That is inside the US$90 monthly cap, with little room: the NIST pages (about 1,700 of the
5,500) are not yet fetched. The order of what drops if the API runs over is unchanged: the
OpenAI arm first, then the ceiling subset.

Revised 2026-10-17, once NIST was fetched and every vision model had a dev pass: the dev runs
came to about US$12 billed (arm D US$3.07, Sonnet US$4.07, Haiku US$0.26, Gemini US$2.29 after
a rerun, GPT-6.1 Sol still open), and the remaining test and NIST runs to about US$90, so the
build's API spend is about US$105, CA$140, over the estimate. Peter raised legible's monthly
cap to US$110 that day, in 04 and here. The table further down is the plan as first written.

Revised 2026-10-20, with every VRDU and CORD test read collected: October's ledger stood at
US$82.55 billed. NIST's frontier reads (the 500 test faces for the four vision models and the
OCR-text arm, and the 300 curve pages at levels 1 to 4) need answers of up to 8,192 tokens,
since 3,072 truncated them on dev, and come to about US$95 more, so the build's API spend is
about US$180, CA$240, well past the estimate. Peter chose to keep the plan whole over dropping
arms or waiting for November, and raised legible's monthly cap to US$190, in 04 and here. The
overrun is recorded, not hidden.

Revised 2026-10-22: the NIST test came to about US$42 for the five frontier arms and the curve
at about 2.4 times that, so the estimate above was about US$20 short. With the ceiling moved
to Opus 5.5 (about US$10 rather than Fable's US$25), finishing in October takes about US$210.
Peter raised legible's cap to US$215, in 04 and here.

Revised 2026-10-24: arm F added at Peter's request (section 2.2). Azure's retail prices API
(read 2026-10-24, East US, S0): custom extraction US$30 a 1,000 pages, prebuilt US$10, layout
US$10, neural training free for 10 hours a month then US$3 an hour. The scope is the headline
dev and test sets (FARA's three unseen-template splits, DeepForm's unseen split, CORD, NIST's
twenty faces) and the NIST curve, about 5,200 pages, plus layout on the training documents the
labels are placed with: about US$140 (CA$190). Not in scope: the mixed-template gap, the VRDU
curve and the subsets. Peter raised legible's monthly cap to US$365 and its daily cap to US$80
in 04 and here; the per-run cap stays at US$25.

Actual, 2026-10-25: arm F came to US$133.22 in the ledger (reads US$118.93, layout readings of
the training documents US$14.29) and US$26.16 of training past the ten free hours (18.72 hours
over 24 builds; DeepForm and most NIST faces trained for close to the one-hour ceiling, where the
estimate assumed the half-hour minimum), about US$159 (CA$215) against the US$140 estimate.
The training is billed by Azure outside the gateway, so it is not under legible's cap. The
Azure resource and its training storage were deleted on 2026-10-26, every read being stored.

Revised 2026-10-26: the three ablations (section 2.3), eleven E2B fine-tunes, from the
measured training records (the E2B took 227 minutes on NIST's 800 faces and 57 on CORD) and
the arm B reads: about 13 GPU hours of training and 12 of reading on the 24 GB class at
US$0.27 to 0.50 an hour, about US$12 to 15 (CA$16 to 20). No API spend: the fine-tunes are read
through the gateway on the rented card.

Actual, 2026-10-28: about US$30 (CA$41) of RunPod time, twice the estimate, and about US$15 of
it pods left running idle. A training pod's crash went unnoticed for fourteen hours because the
monitoring script's process check matched its own command, and two finished pods ran five hours
because the script exited, on finding no RTX 3090 free, before deleting them. NIST's runs also
needed the 48 GB A6000 (US$0.59 an hour), not the 24 GB class. The balance ran out with one
read left, NIST at 560 tokens; its adapter is on the volume.

The plan as first written:

| Item | Basis | US$ | CA$ |
|---|---|---:|---:|
| Arm A, Anthropic quality model | 4,100 pages at about 2,900 tokens in and 300 out, batch rate | 18 | 24 |
| Arm A, Anthropic cost anchor | The same pages on the cheapest model | 2 | 3 |
| Arm A, ceiling model on a 600-page subset | Opus-class, batch rate | 6 | 8 |
| Arm A, Google model | 4,100 pages, image at 258 tokens | 5 | 7 |
| Arm A, OpenAI model | 4,100 pages, estimated at a mid-tier price; checked on the day | 15 | 20 |
| Arm D, OCR text to the quality model | 4,100 pages at about 1,500 tokens in and 300 out, batch rate | 12 | 16 |
| Fine-tuning | About 30 GPU hours on the L4 or 4090 class (two sizes, three corpora, ablations, seeds); about 8 hours on the A100 class for E4B at the 1,120-token budget | 22 | 30 |
| Evaluation of arms B and C, serving and load tests | About 12 GPU hours | 6 | 8 |
| Object storage for checkpoints, one month | | 3 | 4 |
| Development runs | Through the gateway's development cache; re-runs cost nothing | 0 | 0 |
| Demo site | Azure Static Web Apps free tier | 0 | 0 |
| **Total** | | **89** | **120** |

With a reserve for a second pass on the prompts and one wasted GPU run, the plan budgeted
**CA$100 to 175**. If the API spend ran over, the OpenAI arm was to be dropped first, then the
ceiling subset; neither was, and the overruns are recorded above.

## 8. Handover and reuse

`legible` v0.1.0 at the end of week 3. 07 imports `legible.degrade` and reads
`docs/degradation.md`. 04 gains per-image price entries and the first image rows in its
ledger. 03 gains a third real use of its adapter. The published adapters on Hugging Face carry
cards with failure modes, the training page counts and the licence of every corpus they were
trained on. The schemas, grader and degradation pipeline are corpus-agnostic: a fourth corpus is
a schema file and a loader.

## 9. Risks

| Risk | Handling |
|---|---|
| A corpus licence turns out narrower than recorded | Licences are read and quoted in `docs/data.md` on day one before any fetch; SROIE is already out unless its terms are found; VRDU's variant (CC BY 4.0) is quoted from Google's release post, since the repository has none; NIST SD2 waits on NIST's answer; a corpus whose terms forbid redistribution of derived models drops its adapter from publication and keeps its numbers |
| Public records with personal names sent to vendors | True `public` declaration under 04's policy; nothing redistributed; no registration page images on the demo; the plan says so above the fold in the README's "What this does not do" |
| VRDU annotations are human and imperfect | The 200-label audit before the first run; disagreement rate published; a label the audit overturns is corrected in a recorded patch file, never silently |
| The fine-tune does not reach the frontier on the unseen-template split | Published either way, through the gate with its interval; the review-rate number still says what a person has left to do for each arm |
| vLLM lacks Gemma 4 vision support on the day | Batched Transformers generation on the same GPU; throughput reported for whichever served, and the README says which |
| Spot interruptions | Checkpoint every N steps to object storage from the first run, resumable training, the cost of interruptions measured and reported, as in 06 |
| Visual token budget inflates GPU time | The 560-token ablation is run first on E2B; if it holds within the interval, it becomes the default for the rest. As built, the 1,120-token runs fitted the GPU time, so the headline was trained first and the ablation follows it (section 2.3, 2026-10-26). It did not hold: 1,120 stays (2026-10-28) |
| The laptop tempts a shortcut | Nothing is measured on it; the 4 GB card runs tests and the site build. One exception, decided 2026-10-17: the frontier batches (arms A and D) are submitted and collected from the laptop through the gateway, because a batch's answers, tokens and cost come from the vendor whichever machine sends it, and the VPS planned for them could not be reached. Nothing timed comes from the laptop: OCR seconds are the CPU machine's, and no latency from a batch is reported. Arm F (2026-10-24) is sent the same way, for the same reason: the service's answers and pages billed are the vendor's whichever machine asks |
| Vendor terms on training from outputs | Not relevant: no distillation; labels come from the corpora |
| Employer boundary | Public data only, nothing shared in either direction, no internal design reproduced |

## 10. Candidates for the rejected approach

1. **OCR text plus the same frontier model matches the vision read.** Arm D against arm A,
   same model, same pages, paired. Expected: level on clean single-template pages, and a gap
   of several points on nested line items and on degraded scans, because the positioned text
   loses the table structure and the OCR errors compound. If instead D matches A everywhere,
   that is the cheaper pipeline and the README says so.
2. **Prompting the untuned small base to reach the fine-tune.** Zero-shot and few-shot on
   E2B and E4B, same items. Expected: a gap of tens of points that no prompt closes.
3. **Rules survive a new template.** Arm E on the unseen-template split. Expected: from the
   high nineties on templates it was written for to near zero on templates it was not, at a
   cost of nothing per page. The honest statement of what rules buy and when they stop.
4. **A higher visual token budget always helps.** 1,120 against 560 on every corpus and
   level. Expected: a difference only on dense ad-buy pages and at degradation level 3 and
   above, at twice the cost per page everywhere.

Whichever produces the clearest evidence becomes `docs/rejected.md`.

## 11. Definition of done

- [x] Three corpora fetched by loaders with checksums, licences quoted in `docs/data.md`, splits with leakage checks, the 200-label audit published
- [x] Degradation levels 0 to 4 reproducible byte for byte and calibrated to OCR word accuracy in `docs/degradation.md`
- [x] Five arms measured on identical held-out pages per corpus, intervals over documents, paired deltas, miss taxonomy and hallucination rates (six, with arm F)
- [x] Unseen-template against mixed-template accuracy per arm on both VRDU corpora
- [x] Degradation curve per arm on NIST, and on the VRDU subset
- [x] Two fine-tuned sizes per corpus, three seeds on the final configuration, token-budget and data-volume ablations; adapters published with cards including failure modes (ablations measured 2026-10-28, ten of eleven read, NIST at 560 tokens trained and not read; FARA's adapters private, since its forms name individuals)
- [x] Non-inferiority of the best fine-tune against the best frontier arm per corpus through the 03 gate, delta stated, interval shown
- [x] Review rate at 99 percent accepted-field accuracy per arm, thresholds from dev, measured on test
- [x] Verifier catch rate per corpus
- [x] Cost per 1,000 pages per arm from the gateway ledger and GPU rates, prices dated; latency p50 and p99
- [x] Break-even curve over utilisation with the inputs table
- [x] forms.peterparker.ca live with the viewer, the slider and the tables
- [x] One rejected approach documented with evidence (`docs/rejected.md`)
- [ ] Repository public, `v0.1.0` tagged, the status flip logged on peterparker.ca

## 12. Deferred

| Deferred | Kept so the door stays open |
|---|---|
| Handwriting: NIST SD6, 5,595 hand-printed pages of the same twelve forms | Same loader shape, same schemas; one corpus entry and a fetch |
| A dedicated 1B document model (PaddleOCR-VL class) as a sixth arm | `arms/small.py` takes any Transformers vision model with a generate method |
| SROIE as a second receipts set | Loader stub kept; enabled when its terms are confirmed |
| Live upload demo through 04 with a spend cap | The site's viewer already renders a result JSON; a live result is the same JSON |
| Multi-page documents and cross-page fields | The page manifest carries document and page ids; the schema can take a document scope |
| A layout-model arm for the historical comparison | The OCR boxes arm D produces are the input such a model needs |
| A write-up | The degradation chart is ready to be a figure in one |

## 13. Name

**Chosen 2026-10-16: Forms That Read Themselves.** The working title stayed; the magnitude
(more than 9,000 pages, a 2B and a 4B model, 99 percent, cost per thousand pages) and the
selling point (vision-language models, multimodal fine-tuning) live in the README's opening
paragraph and the technical line, which is where the naming rules put them. The candidates as
weighed:

1. **Thousands of Forms, Read Overnight, Checked by Morning**: the backlog, the speed and the
   review rate, in the shape of 07's name.
2. **Every Field on the Form, and What It Costs to Read**: the outcome and the cost axis.
3. **The Backlog of Paper, Read by Machine**: shortest; the felt cost is the backlog.
4. **Forms That Read Themselves**: keep the working title and let the one-liner carry the
   magnitude. Chosen.

Repository, package and slug stay as they are whichever is chosen, as 07's did.
