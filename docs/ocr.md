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

Preprocessing, per corpus, chosen on training pages (`PREPROCESS` in `legible/arms/ocr.py`):

| Corpus | What Tesseract is given | Why |
|---|---|---|
| FARA, DeepForm | The 300 dpi page as rendered, automatic page segmentation (`--psm 3`) | Scans at scan resolution; nothing to add |
| CORD | Scaled up twice, median filter 3, binarised against the mean of a 51-pixel window less 10, read as one block (`--psm 6`) | Phone photographs of dot-matrix print at about 100 dpi under uneven light. As published, Tesseract read **no words at all** from the first training receipt tried; the block mode keeps an item and its price on one line |

On the laptop, a VRDU page took 5 to 8 seconds and a CORD receipt about 6, single-threaded.

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
