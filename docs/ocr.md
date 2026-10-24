# OCR and the rules arm

How arms D and E get their text, and how arm E's rules were written. Nothing here is a
result: the numbers below are from training pages, read on the laptop while the rules were
being written, and say only how far the rules got on the pages they were written from.

## Tesseract

Tesseract 5.4.0 (`legible/arms/ocr.py`), run as a subprocess with TSV output, one process per
page and one thread per process (`OMP_THREAD_LIMIT=1`), so the wall time of a page is the CPU
time OCR's cost is computed from. Each page's OCR is stored under the data root with the
sha256 of the image it read and the preprocessing used, and is reused only while both still
match (`legible/arms/ocr_run.py`). Measured runs are on the rented CPU machine.

## The measuring machine

A RunPod CPU pod, compute-optimised (`cpu3c`), 16 vCPU and 32 GB, Secure Cloud in EUR-IS-1, at
US$0.48 an hour (2026-10-17), Ubuntu 24.04 with its own Tesseract, **5.3.4**
(`tesseract-ocr` 5.3.4-1build5, English model as packaged). The rules were written against
Tesseract 5.4.0 output on the laptop; the measured numbers are 5.3.4's. `ops/cpu-pod.sh` sets
the machine up from nothing, fetches and verifies the corpora, renders them, and stops unless
every page is byte-identical to the committed manifests; then runs Tesseract, 16 pages at a
time, one thread each.

Level 0, 2026-10-17. A document in the dev part of one split file and the test part of
another is read once, so the test rows count only pages not already read for dev:

| Corpus | Part | Documents | Pages read | CPU seconds | Seconds a page |
|---|---|---:|---:|---:|---:|
| FARA | dev | 380 | 764 | 2,258 | 3.0 |
| FARA | test | 1,053 | 1,963 | 5,859 | 3.0 |
| DeepForm | dev | 100 | 245 | 1,104 | 4.5 |
| DeepForm | test | 300 | 774 | 4,183 | 5.4 |
| CORD | dev | 100 | 100 | 1,610 | 16.1 |
| CORD | test | 100 | 100 | 1,037 | 10.4 |
| NIST | train | 3,850 | 3,850 | 16,660 | 4.3 |
| NIST | dev | 561 | 561 | 2,713 | 4.8 |
| NIST | test (the 500 every arm reads) | 500 | 500 | 2,582 | 5.2 |
| NIST | curve, levels 1 to 4 | 300 | 1,200 | 5,138 | 4.3 |

NIST was read on a second pod of the same kind (EU-RO-1), 2026-10-17, the same Tesseract.

The VRDU curve subset (39 FARA and 30 DeepForm unseen-template test documents) was read at levels 2 and 4 on a third 16 vCPU CPU pod at the same rate (US-CA-2, AMD EPYC 7713,
2026-10-23), the same Tesseract 5.3.4, with the same pages: its degraded PNGs differ in bytes
from the laptop's (another zlib), and decode to the same pixels on the page compared.

| Corpus | Level | Documents | Pages read | CPU seconds | Seconds a page |
|---|---:|---:|---:|---:|---:|
| FARA | 2 | 39 | 75 | 298 | 4.0 |
| FARA | 4 | 39 | 75 | 252 | 3.4 |
| DeepForm | 2 | 30 | 75 | 605 | 8.1 |
| DeepForm | 4 | 30 | 75 | 1,768 | 23.6 |

A CORD receipt costs most because its preprocessing doubles the photograph, and some are
2304 by 4096 pixels as published. Seconds are wall time of a single-threaded Tesseract process
with all 16 vCPU busy, which is how a batch would be run.

Preprocessing, per corpus, chosen on training pages (`PREPROCESS` in `legible/arms/ocr.py`):

| Corpus | What Tesseract is given | Why |
|---|---|---|
| FARA, DeepForm | The 300 dpi page as rendered, automatic page segmentation (`--psm 3`) | Scans at scan resolution; nothing to add |
| NIST | The 300 ppi binary page as published, `--psm 3` | As for the VRDU scans |
| CORD | Scaled up twice, median filter 3, binarised against the mean of a 51-pixel window less 10, read as one block (`--psm 6`) | Phone photographs of dot-matrix print at about 100 dpi under uneven light. As published, Tesseract read **no words at all** from the first training receipt tried; the block mode keeps an item and its price on one line |

On the laptop, while the rules were written, a VRDU page took 5 to 8 seconds and a CORD receipt about 6, single-threaded; those timings are not used.

## Page orientation

Fifteen DeepForm documents (32 pages) are portrait PDFs of landscape scans: the PDF says
portrait, VRDU's own OCR read them landscape, and VRDU's boxes are in that frame. The render
turns such a page 90 or 270 degrees, whichever puts more ink inside VRDU's token boxes
(`orient` in `legible/data/render.py`), and records the turn in the page manifest. Two of those
documents (five pages, both from the same 2012 political file, `...-72076-...`) are upside
down in VRDU's frame too: the boxes match the inverted page, so the page is kept as the
benchmark has it, and every arm reads it that way. Before the fix, two audit crops were blank,
which is how it was found.

## How arm E's rules were written

`legible/arms/rules.py` is the engine: find a printed label, take the value beside it or under
it in its column, keep it if it has the field's shape. `legible/arms/rule_sets.py` holds the
rules, written from training pages only:

- **FARA**, one rule set per template (Amendment, Short-Form, Dissemination Report),
  recognised from the form's title block. A split is given only the sets for the templates in
  its training part, so on an unseen-template split the held-out template's rules do not exist
  and its documents get no answer.
- **DeepForm**, one set: VRDU publishes no template label, and most training pages are
  WideOrbit invoices and orders. Line items are read from WideOrbit's row-and-date layout.
- **CORD**, one set of receipt keywords (SUBTOTAL, PB1, SVC, TOTAL, CASH, CHANGE and their
  Indonesian forms) and an item-line pattern.

Field accuracy on the training sample the rules were written from (75 FARA documents balanced
across templates, 60 DeepForm, 60 CORD; level 0; VRDU's own matchers):

| Corpus | Field accuracy on training pages |
|---|---|
| FARA, Amendment | 40% |
| FARA, Short-Form | 39% |
| FARA, Dissemination Report | 34% |
| DeepForm, header fields | 15 to 75% by field (contract number best, station address worst) |
| DeepForm, all fields with line items | 13% |
| CORD | 20% |

That is far below the plan's expectation of "the high nineties on templates it was written
for" (PLAN.md section 10, candidate 3), on the pages the rules were written from. Three reasons
are visible in the misses: FARA's three "templates" each span decades of form revisions
(typewritten 1970s reports beside 2010s PDFs) and many values are handwritten; VRDU's name
matcher is exact, so an OCR slip in one letter is a miss; and the receipts' OCR is poor even
after preprocessing. More rule-writing would raise these numbers, but each rule written is a
rule for one layout, which is the cost the comparison is about. The measured numbers, on dev
and then once on test, come from the CPU machine.

## Arm D: OCR text to the quality model

`legible read submit --arm d` and `legible read collect --arm d` (`legible/arms/read_run.py`,
which runs arm A the same way with the page images). Arm D reads the same stored OCR as arm E, laid out as positioned text (each line of the page one
line of text, each word at the column of its left edge, 160 columns across), one block per
page, followed by the corpus prompt built for OCR text (`legible/prompt.py`). The reader is
the `quality` route in `boundary.yaml`, Claude Sonnet 5.5, sent through the gateway in
batches with `data_class=public`, `purpose=arm-d`, and a run id naming the route, corpus,
part, level and prompt version.

- **One read per document** over the union of a part's split files: a zero-shot model does not
  depend on a split's training part, so each split file's number is cut from the one read
  when grading.
- **A run is resumed only as it was begun.** The run directory keeps the run's description
  and the exact prompt; a different model or a changed prompt is refused, not mixed in, and
  nothing already read or submitted is sent again.
- **Batches are cut by size** as well as count (`BATCH_BYTES`), so image batches stay inside
  each vendor's cap, and are built one batch at a time.
- **Dev before test, once.** A test run is refused until the same prompt has read every dev
  document at the same level, and a test run takes every test document or none (`--limit`
  is for dev).
- **Output budget** per corpus: 1,024 tokens for FARA, 8,192 for DeepForm, 2,048 for CORD. The
  longest training record as JSON is 479, 16,169 and 3,763 characters; an answer that runs
  out of budget is graded as malformed, as it is.

At the gateway's pessimistic pre-call estimate (a token for every 3.5 input characters,
the whole output budget spent, batch rate), the test sets come to about US$8.50 for FARA
(1,053 documents), US$13.70 for DeepForm (300) and US$1.30 for CORD (100), each inside the
US$25 per-run cap; at about 300 tokens out the expected cost is about US$7 for all three.

### Arm D on dev

Submitted from the laptop (PLAN.md, risks), 2026-10-17; Claude Sonnet 5.5 at the batch rate
(two CORD receipts were a synchronous smoke test at the full rate); level 0; prompt version 1;
VRDU's matchers; 95% bootstrap intervals over documents. Cost is the gateway ledger's, at the
2026-10-16 price list. The validation part is the same in every seed of a split.

| Split | Documents | Field accuracy | Invented | Cost, US$ |
|---|---:|---|---|---:|
| FARA, mixed templates | 100 | 69.4% (64.0 to 74.5) | 6.4% (4.5 to 8.3) | 0.32 |
| FARA, Amendment held out | 100 | 63.6% (59.2 to 67.8) | 12.7% (10.7 to 14.7) | 0.29 |
| FARA, Dissemination Report held out | 100 | 83.6% (79.8 to 87.0) | 1.2% (0.3 to 2.0) | 0.29 |
| FARA, Short-Form held out | 100 | 61.9% (56.8 to 66.8) | 7.2% (5.1 to 9.3) | 0.37 |
| DeepForm, either split | 100 | 74.8% (69.6 to 79.6) | 5.6% (3.8 to 7.7) | 1.17 |
| CORD | 100 | 34.9% (28.0 to 42.3) | 3.6% (1.0 to 7.2) | 0.70 |

All 580 dev documents cost US$3.07. One DeepForm reply ran out of its 8,192-token budget and
is graded unparsed: document 417792, one of the two upside-down scans (Page orientation,
above), whose OCR is noise. On CORD 601 of 840 misses are fields left empty; the receipts'
OCR is the weakest of the three, and arm A on the same receipts will say how much of that is
the OCR and how much the model.

## Arm E on dev

Level 0, Tesseract 5.3.4 on the measuring machine, 2026-10-17, VRDU's matchers, 95% bootstrap
intervals over documents. VRDU's validation part is the same 100 documents in all three seeds
of a split, so each row stands for three files. Dev, not test: the test run is once, after
this.

| Split | Documents | Recognised by a rule set | Field accuracy | Invented |
|---|---:|---:|---|---:|
| FARA, mixed templates | 100 | 95 | 37.1% (32.6 to 41.5) | 3.4% |
| FARA, Amendment held out | 100 | 60 | 21.7% (17.4 to 26.0) | 1.2% |
| FARA, Dissemination Report held out | 100 | 77 | 20.3% (17.5 to 23.1) | 0.2% |
| FARA, Short-Form held out | 100 | 0 | 0.0% | 0.0% |
| DeepForm, either split | 100 | 100 | 10.4% (6.5 to 15.5) | 0.9% |
| CORD | 100 | 100 | 16.6% (13.1 to 20.4) | 0.5% |

On a held-out FARA template the documents a rule set still "recognises" are claimed by
another template's rules, whose title pattern also appears on the held-out form; their
fields are read with the wrong layout, which is what an unseen template does to rules.

## Arm E on test

Run once, 2026-10-17, with the rules frozen as they were when written (`legible/arms/rule_sets.py`
at 1de5f5b; not changed after the dev run). The rules read the OCR stored from the measuring
machine; applying them is arithmetic on stored words, so it ran on the laptop and nothing in
it is timed. Level 0, VRDU's matchers, 95% bootstrap intervals over documents. A document no
rule set recognised is graded as answering nothing (every field missing, not malformed;
`answer` in `legible/arms/rules_run.py`), which leaves field accuracy as it is.

VRDU's FARA test part is the same 300 documents in all three seeds of a split, so a FARA row
stands for three files; DeepForm's unseen-template test parts differ by seed.

| Split | Documents | Recognised | Field accuracy | Invented | Every field right |
|---|---:|---:|---|---|---:|
| FARA, mixed templates | 300 | 284 | 36.2% (33.6 to 38.9) | 3.5% (2.6 to 4.4) | 1.0% |
| FARA, Amendment held out | 300 | 187 | 22.4% (19.9 to 24.9) | 0.5% (0.1 to 1.0) | 0.0% |
| FARA, Dissemination Report held out | 300 | 216 | 19.3% (17.6 to 20.9) | 0.2% (0.0 to 0.5) | 0.0% |
| FARA, Short-Form held out | 300 | 1 | 0.1% (0.0 to 0.2) | 0.0% | 0.0% |
| DeepForm, mixed templates | 300 | 300 | 11.5% (9.0 to 14.4) | 0.9% (0.7 to 1.1) | 0.7% |
| DeepForm, unseen templates, seed 0 | 159 | 159 | 13.7% (9.8 to 18.3) | 0.8% (0.6 to 1.0) | 1.3% |
| DeepForm, unseen templates, seed 1 | 157 | 157 | 12.6% (9.1 to 17.0) | 0.8% (0.6 to 1.0) | 1.3% |
| DeepForm, unseen templates, seed 2 | 153 | 153 | 13.1% (9.3 to 17.6) | 0.8% (0.6 to 1.1) | 1.3% |
| CORD | 100 | 100 | 15.8% (11.9 to 19.8) | 0.8% (0.1 to 1.9) | 0.0% |

Most misses are fields left empty: the rules answer only where a label and a value of the
right shape were found, so arm E invents little and reads little. DeepForm's unseen-template
number is no worse than its mixed one because its one rule set was never written per
template. The README's tables will carry these through the report command, beside the other
arms on the same documents.

## Arm E on NIST: zonal OCR

SD2's twenty faces never change layout, so arm E there is the classic fixed-form pipeline:
zones, not label anchors (`legible/arms/zonal.py`). The face, each field's zone and the page
registration are learned from the 3,850 training pages' OCR and answer files by `legible rules
learn-nist`, and committed as `legible/arms/nist_zones.json`; nothing is learned from dev or
test. The design was tuned on dev only.

On dev, level 0, 2026-10-17: every one of the 561 faces is identified correctly, and **16.3% of
fields (15.0 to 17.8) are read right**, with 14.5% of scored fields invented (a zone that read
the form's own print or a neighbour's value). That is far below what a template pipeline is
supposed to reach, and the ceiling is Tesseract's, not the zones': of the 11,791 filled fields on
the dev faces, only **56% appear anywhere in Tesseract's output as the value's own words on one
line**. SD2 prints machine type into boxes whose lines touch the characters, and Tesseract
merges adjacent columns ("9784\Parent"), drops a character ("Sierr") or reads a box line as one
("[broker"). Of the values Tesseract did read whole, 81% fall inside their learned zone; the
rest sit a row away, because the synthesis jitters each value by about a row's height.

What was tried on dev, in order, each one kept only if it helped:

| Change | Field accuracy |
|---|---:|
| Zones from the 5th to 95th percentile of every sample | 0.6% |
| A sample only where the value is found once on the page; outliers dropped; the form's own print left out of a read | 12.9% |
| Registration of each page by its anchors (a shift) | 17.1% |
| A scale and a shift on each axis; low-confidence words dropped; a word given to one zone only | 15.9 to 17.5% |
| Keeping printed words longer than two characters (so "and" in a joint name survives) | 14.4%, reverted |

## Calibration

`docs/degradation.md`, written by `legible calibrate` from the NIST curve pages' OCR at every
level.
