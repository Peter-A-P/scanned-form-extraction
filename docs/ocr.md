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

A CORD receipt costs most because its preprocessing doubles the photograph, and some are
2304 by 4096 pixels as published. Seconds are wall time of a single-threaded Tesseract process
with all 16 vCPU busy, which is how a batch would be run.

Preprocessing, per corpus, chosen on training pages (`PREPROCESS` in `legible/arms/ocr.py`):

| Corpus | What Tesseract is given | Why |
|---|---|---|
| FARA, DeepForm | The 300 dpi page as rendered, automatic page segmentation (`--psm 3`) | Scans at scan resolution; nothing to add |
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

`legible ocr-text submit` and `legible ocr-text collect` (`legible/arms/text_run.py`). Arm D
reads the same stored OCR as arm E, laid out as positioned text (each line of the page one
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
