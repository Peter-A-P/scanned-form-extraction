# Forms That Read Themselves

A vision-language model you own, fine-tuned to type your scanned forms in, measured against the
frontier multimodal APIs and the classic OCR pipelines on more than 9,000 public pages with known
answers. Every field right or wrong with its interval, cost per thousand pages, what breaks on a
new form design or a bad scan, and how many fields a person still checks at 99 percent.

Every organisation that still receives paper has a backlog of forms and someone typing them in.
This project puts vision-language models to work on that backlog: a frontier multimodal model
reading the scan, a 2B and a 4B open vision model fine-tuned to read it, and the classic OCR
pipelines beside them. Same pages, same fields, one grader. It reports every field read right or
wrong with confidence intervals, what each approach costs per thousand pages, how it holds up on
a form design it has never seen and on a bad scan, and the number a director wants: at 99
percent accuracy, how many fields still need a person.

## What it found

- **The frontier vision models read best, everywhere.** On form designs never seen in
  training, Gemini 3.8 Flash gets 80.6% of FARA's fields right and GPT-6.1 Sol 71.4% of
  DeepForm's; on receipts GPT-6.1 Sol gets 88.1%, and on the printed tax forms 94.9%.
- **The fine-tuned 2B and 4B cost a twenty-fifth to a fiftieth as much per page and read 10 to
  21 points worse than the best frontier model on each corpus.** On FARA's unseen templates
  the 2B gets 69.0% at US$0.06 a thousand pages, against Gemini's 80.6% at US$1.65 and Sonnet
  5.5's 78.8% at US$2.96. Project 03's gate blocks them on FARA and DeepForm,
  and cannot decide on CORD or NIST, where too few documents hold each field.
- **The fine-tunes are the ones a new form design hurts.** On FARA templates it saw in
  training the 2B gets 75.7%; on templates it did not, 69.0%. Sonnet 5.5 gets 74.2% and 78.8%:
  no worse on the unseen ones.
- **A bad scan barely moves a vision model and breaks the OCR pipelines.** On NIST's curve
  pages Sonnet 5.5 reads 87.9% at level 0 and 87.0% at level 3; Sonnet on the OCR text of the
  same pages falls from 37.4% to 4.5%, and OCR plus rules from 16.2% to 2.3%.
- **The cheapest frontier model is close on clean, printed forms.** Claude Haiku 5.5 reads
  84.5% of the tax forms' fields against Sonnet's 86.7%, at US$1.12 a thousand pages against
  US$16.38.
- **The fine-tunes beat the managed document service on two of the four form types and match
  it on the other two, at 47 to 509 times less a page.** Against Azure
  AI Document Intelligence the 4B gets 59.6% (53.7 to 65.3) of DeepForm's unseen-template fields
  to its 40.5% (37.0 to 44.3), and 77.6% (71.5 to 83.3) of CORD's receipt fields to its prebuilt
  receipt model's 66.6% (60.5 to 72.1), at US$0.19 and US$0.16 a thousand pages against US$30
  and US$10. On FARA's unseen templates (the 2B: 69.0%, Azure 68.9%) and the tax forms (the 4B:
  74.2%, Azure 72.5%) the two are level, Azure's custom neural models at US$30 a thousand pages
  ([docs/docintel.md](docs/docintel.md)). A bad scan costs Azure more than a vision model: 72.9%
  to 63.4% of the NIST curve's fields from level 0 to level 4.
- **The dearest model buys accuracy only on some forms.** Claude Opus 5.5, at about twice
  Sonnet's price, reads 93.5% of the ceiling subset's receipt fields against Sonnet's 83.8% and
  94.1% of its tax-form fields against 85.4%, and is no better on FARA or DeepForm. Sonnet
  reading the same pages twice changes 0.3% to 7.3% of its field outcomes, so a gap of a point
  or two between arms on one corpus is inside that noise.

## The honest limitation

The number a director wants is the one this cannot give yet: **at 99% accuracy, every field
still goes to a person**, for every arm on every corpus. Neither confidence tried separates
right fields from wrong ones well enough. The frontier arm's, whether its image read and its
OCR-text read agree, is right less than 99% of the time even where they agree; the fine-tune's
own token probability is confidently wrong ([docs/rejected.md](docs/rejected.md)). So the
tables say how much typing each pipeline saves a checker, not how much of the checking it
replaces. Beside that: the corpora are public and old (FARA registrations from the 1960s on,
NIST's synthesised 1988 tax forms); CORD's 100 receipts and NIST's 500 pages spread over twenty
form faces are too few for the gate to decide field by field at three points; and the review
rate's fine-tuned rows come from a second read of the test sets, with log-probabilities,
decided after the first (PLAN.md 2.6).

## Result

<!-- results:start -->
Test sets, read once per arm, level 0 unless stated. Field accuracy is VRDU's own matchers, one grader for every arm; intervals are 95% bootstrap over documents. Frontier cost is the gateway ledger's at the 2026-10-16 price list, batch rate; OCR is costed at US$0.03 per vCPU-hour (RunPod, 2026-10-17). Written by `legible report`; do not edit.

**FARA registration forms, templates never seen in training (headline)**

| Arm | Fields correct (95% CI) | Every field right | Invented fields | Cost per 1,000 pages | Documents |
|---|---|---|---|---|---:|
| A, Claude Sonnet 5.5 on the image | 78.8% (77.5 to 80.0) | 31.4% (28.4 to 34.4) | 8.9% (8.1 to 9.7) | US$2.96 (2.95 to 2.97) | 900 |
| A, Claude Haiku 5.5 on the image | 75.4% (73.9 to 76.8) | 27.8% (24.9 to 30.7) | 11.0% (10.1 to 11.8) | US$0.18 (0.17 to 0.18) | 900 |
| A, GPT-6.1 Sol on the image | 71.8% (70.3 to 73.2) | 21.6% (18.9 to 24.3) | 12.7% (11.9 to 13.6) | US$2.78 (2.76 to 2.79) | 900 |
| A, Gemini 3.8 Flash on the image | 80.6% (79.4 to 81.9) | 38.4% (35.3 to 41.7) | 8.5% (7.7 to 9.2) | US$1.65 (1.57 to 1.73) | 900 |
| D, Claude Sonnet 5.5 on the OCR text | 70.0% (68.3 to 71.8) | 22.3% (19.6 to 25.1) | 6.9% (6.2 to 7.7) | US$1.60 (1.58 to 1.62) | 900 |
| E, OCR plus rules | 14.2% (13.0 to 15.4) | 0.0% (0.0 to 0.0) | 0.2% (0.1 to 0.4) | US$0.02 (0.02 to 0.02) | 900 |
| B, Gemma 4 E2B fine-tuned on the image | 69.0% (67.2 to 70.7) | 29.6% (26.6 to 32.6) | 5.9% (5.2 to 6.6) | US$0.06 (0.06 to 0.06) | 900 |
| B, Gemma 4 E4B fine-tuned on the image | 66.8% (65.3 to 68.3) | 14.3% (12.1 to 16.6) | 13.2% (12.3 to 14.2) | US$0.07 (0.07 to 0.08) | 900 |
| C, Gemma 4 E2B untuned on the image | 62.2% (60.7 to 63.7) | 10.7% (8.7 to 12.8) | 8.4% (7.6 to 9.3) | US$0.06 (0.06 to 0.06) | 900 |
| C, Gemma 4 E4B untuned on the image | 70.8% (69.1 to 72.4) | 27.4% (24.6 to 30.3) | 9.3% (8.4 to 10.2) | US$0.09 (0.09 to 0.09) | 900 |
| F, Azure Document Intelligence | 68.9% (67.5 to 70.4) | 20.8% (18.1 to 23.4) | 3.1% (2.6 to 3.6) | US$30.00 (30.00 to 30.00) | 900 |

**DeepForm ad-buy forms, templates never seen in training (headline)**

| Arm | Fields correct (95% CI) | Every field right | Invented fields | Cost per 1,000 pages | Documents |
|---|---|---|---|---|---:|
| A, Claude Sonnet 5.5 on the image | 69.8% (65.4 to 74.2) | 0.6% (0.0 to 1.9) | 10.0% (7.7 to 12.4) | US$5.19 (4.94 to 5.45) | 159 |
| A, Claude Haiku 5.5 on the image | 66.4% (61.5 to 71.0) | 1.3% (0.0 to 3.1) | 11.1% (8.7 to 13.8) | US$0.35 (0.33 to 0.37) | 159 |
| A, GPT-6.1 Sol on the image | 71.4% (66.7 to 76.0) | 2.5% (0.6 to 5.0) | 8.6% (6.5 to 10.9) | US$4.53 (4.32 to 4.75) | 159 |
| A, Gemini 3.8 Flash on the image | 70.0% (64.4 to 75.1) | 2.5% (0.6 to 5.0) | 7.0% (5.3 to 9.0) | US$2.73 (2.39 to 3.14) | 159 |
| D, Claude Sonnet 5.5 on the OCR text | 69.8% (65.1 to 74.4) | 1.3% (0.0 to 3.1) | 9.3% (7.2 to 11.7) | US$4.68 (4.37 to 5.01) | 159 |
| E, OCR plus rules | 13.7% (9.9 to 18.3) | 1.3% (0.0 to 3.1) | 0.8% (0.6 to 1.0) | US$0.05 (0.04 to 0.05) | 159 |
| B, Gemma 4 E2B fine-tuned on the image | 55.3% (48.5 to 62.0) | 1.3% (0.0 to 3.1) | 8.0% (6.0 to 10.3) | US$0.19 (0.17 to 0.21) | 159 |
| B, Gemma 4 E4B fine-tuned on the image | 59.6% (53.7 to 65.3) | 3.1% (0.6 to 6.3) | 7.6% (5.4 to 10.3) | US$0.19 (0.17 to 0.20) | 159 |
| C, Gemma 4 E2B untuned on the image | 20.4% (17.1 to 23.9) | 0.0% (0.0 to 0.0) | 8.2% (5.8 to 11.0) | US$0.13 (0.12 to 0.14) | 159 |
| C, Gemma 4 E4B untuned on the image | 47.2% (42.6 to 51.9) | 0.0% (0.0 to 0.0) | 13.5% (10.4 to 16.9) | US$0.22 (0.20 to 0.24) | 159 |
| F, Azure Document Intelligence | 40.5% (37.0 to 44.3) | 0.6% (0.0 to 1.9) | 3.1% (2.1 to 4.2) | US$30.00 (30.00 to 30.00) | 159 |

**CORD receipts, test set**

| Arm | Fields correct (95% CI) | Every field right | Invented fields | Cost per 1,000 pages | Documents |
|---|---|---|---|---|---:|
| A, Claude Sonnet 5.5 on the image | 84.0% (77.8 to 89.2) | 47.0% (37.0 to 57.0) | 3.4% (2.3 to 4.6) | US$5.27 (5.06 to 5.50) | 100 |
| A, Claude Haiku 5.5 on the image | 76.7% (70.1 to 82.6) | 28.0% (19.0 to 37.0) | 5.2% (4.0 to 6.6) | US$0.38 (0.36 to 0.40) | 100 |
| A, GPT-6.1 Sol on the image | 88.1% (84.2 to 91.6) | 51.0% (41.0 to 61.0) | 3.4% (2.4 to 4.6) | US$4.59 (4.35 to 4.85) | 100 |
| A, Gemini 3.8 Flash on the image | 86.1% (79.7 to 91.6) | 57.0% (47.0 to 66.0) | 1.2% (0.6 to 2.0) | US$4.42 (3.77 to 5.12) | 100 |
| D, Claude Sonnet 5.5 on the OCR text | 36.2% (29.8 to 42.7) | 1.0% (0.0 to 3.0) | 2.0% (1.2 to 3.0) | US$5.97 (5.03 to 7.14) | 100 |
| E, OCR plus rules | 15.8% (11.9 to 19.8) | 0.0% (0.0 to 0.0) | 0.8% (0.1 to 1.9) | US$0.09 (0.04 to 0.15) | 100 |
| B, Gemma 4 E2B fine-tuned on the image | 75.2% (67.9 to 82.0) | 38.0% (29.0 to 48.0) | 1.0% (0.4 to 1.8) | US$0.11 (0.11 to 0.11) | 100 |
| B, Gemma 4 E4B fine-tuned on the image | 77.6% (71.5 to 83.3) | 30.0% (21.0 to 39.0) | 0.9% (0.4 to 1.5) | US$0.16 (0.16 to 0.16) | 100 |
| C, Gemma 4 E2B untuned on the image | 40.7% (36.8 to 44.6) | 0.0% (0.0 to 0.0) | 9.8% (8.1 to 11.6) | US$0.14 (0.14 to 0.14) | 100 |
| C, Gemma 4 E4B untuned on the image | 60.0% (54.6 to 65.2) | 3.0% (0.0 to 7.0) | 9.9% (8.3 to 11.8) | US$0.19 (0.19 to 0.19) | 100 |
| F, Azure Document Intelligence | 66.6% (60.5 to 72.1) | 2.0% (0.0 to 5.0) | 0.4% (0.1 to 0.7) | US$10.00 (10.00 to 10.00) | 100 |

**NIST tax forms, 500 test faces**

| Arm | Fields correct (95% CI) | Every field right | Invented fields | Cost per 1,000 pages | Documents |
|---|---|---|---|---|---:|
| A, Claude Sonnet 5.5 on the image | 86.7% (84.8 to 88.4) | 46.2% (42.0 to 50.4) | 0.7% (0.6 to 1.0) | US$16.38 (15.63 to 17.19) | 500 |
| A, Claude Haiku 5.5 on the image | 84.5% (82.3 to 86.4) | 36.8% (32.6 to 41.0) | 0.5% (0.3 to 0.7) | US$1.12 (1.08 to 1.17) | 500 |
| A, GPT-6.1 Sol on the image | 94.9% (94.0 to 95.6) | 50.2% (45.8 to 54.6) | 0.4% (0.3 to 0.5) | US$15.33 (14.69 to 16.00) | 500 |
| A, Gemini 3.8 Flash on the image | 80.1% (76.2 to 83.7) | 46.2% (41.8 to 50.6) | 0.6% (0.4 to 0.8) | US$12.48 (11.85 to 13.16) | 500 |
| D, Claude Sonnet 5.5 on the OCR text | 38.7% (36.2 to 41.1) | 1.2% (0.4 to 2.2) | 2.3% (1.9 to 2.7) | US$16.02 (15.26 to 16.82) | 500 |
| E, OCR plus rules | 16.0% (14.6 to 17.4) | 0.0% (0.0 to 0.0) | 15.2% (14.1 to 16.3) | US$0.04 (0.04 to 0.05) | 500 |
| B, Gemma 4 E2B fine-tuned on the image | 73.6% (70.4 to 76.7) | 27.6% (23.8 to 31.6) | 1.4% (1.0 to 1.8) | US$0.40 (0.38 to 0.42) | 500 |
| B, Gemma 4 E4B fine-tuned on the image | 74.2% (70.9 to 77.2) | 24.8% (21.0 to 28.6) | 3.3% (2.7 to 4.0) | US$0.64 (0.60 to 0.67) | 500 |
| C, Gemma 4 E2B untuned on the image | 15.0% (13.7 to 16.4) | 0.0% (0.0 to 0.0) | 27.9% (25.3 to 30.4) | US$0.41 (0.39 to 0.43) | 500 |
| C, Gemma 4 E4B untuned on the image | 16.0% (14.5 to 17.7) | 0.0% (0.0 to 0.0) | 27.3% (24.7 to 30.0) | US$0.69 (0.65 to 0.73) | 500 |
| F, Azure Document Intelligence | 72.5% (70.5 to 74.4) | 6.8% (4.6 to 9.0) | 0.6% (0.4 to 0.8) | US$30.00 (30.00 to 30.00) | 500 |

**FARA, templates seen in training (the gap beside the headline)**

| Arm | Fields correct (95% CI) | Every field right | Invented fields | Cost per 1,000 pages | Documents |
|---|---|---|---|---|---:|
| A, Claude Sonnet 5.5 on the image | 74.2% (71.9 to 76.4) | 24.3% (19.7 to 29.0) | 12.6% (11.2 to 14.1) | US$2.97 (2.96 to 2.99) | 300 |
| A, Claude Haiku 5.5 on the image | 70.1% (67.6 to 72.4) | 19.0% (14.7 to 23.7) | 14.4% (13.0 to 15.9) | US$0.18 (0.18 to 0.19) | 300 |
| A, GPT-6.1 Sol on the image | 65.8% (63.3 to 68.2) | 13.7% (10.0 to 17.7) | 16.6% (15.2 to 18.0) | US$2.83 (2.81 to 2.86) | 300 |
| A, Gemini 3.8 Flash on the image | 76.2% (74.0 to 78.4) | 27.3% (22.3 to 32.3) | 11.0% (9.6 to 12.4) | US$1.76 (1.61 to 1.92) | 300 |
| D, Claude Sonnet 5.5 on the OCR text | 64.8% (61.7 to 67.8) | 16.7% (12.7 to 21.0) | 8.5% (7.2 to 9.8) | US$1.64 (1.61 to 1.68) | 300 |
| E, OCR plus rules | 36.2% (33.6 to 38.9) | 1.0% (0.0 to 2.3) | 3.5% (2.6 to 4.4) | US$0.03 (0.02 to 0.03) | 300 |
| B, Gemma 4 E2B fine-tuned on the image | 75.7% (73.0 to 78.3) | 35.3% (30.0 to 40.7) | 7.8% (6.5 to 9.1) | US$0.06 (0.06 to 0.06) | 300 |
| B, Gemma 4 E4B fine-tuned on the image | 72.2% (69.7 to 74.7) | 22.7% (18.0 to 27.3) | 11.4% (10.0 to 12.9) | US$0.07 (0.07 to 0.08) | 300 |
| C, Gemma 4 E2B untuned on the image | 56.2% (53.8 to 58.7) | 5.0% (2.7 to 7.7) | 10.6% (9.1 to 12.1) | US$0.06 (0.06 to 0.06) | 300 |
| C, Gemma 4 E4B untuned on the image | 63.7% (60.9 to 66.6) | 17.3% (13.3 to 21.7) | 12.8% (11.2 to 14.3) | US$0.09 (0.09 to 0.09) | 300 |

**DeepForm, templates seen in training (the gap beside the headline)**

| Arm | Fields correct (95% CI) | Every field right | Invented fields | Cost per 1,000 pages | Documents |
|---|---|---|---|---|---:|
| A, Claude Sonnet 5.5 on the image | 71.8% (68.5 to 75.1) | 0.7% (0.0 to 1.7) | 8.4% (6.9 to 10.0) | US$5.14 (4.94 to 5.35) | 300 |
| A, Claude Haiku 5.5 on the image | 67.4% (63.5 to 71.2) | 1.0% (0.0 to 2.3) | 9.7% (8.1 to 11.5) | US$0.35 (0.33 to 0.36) | 300 |
| A, GPT-6.1 Sol on the image | 72.3% (68.5 to 75.9) | 1.3% (0.3 to 2.7) | 7.4% (6.0 to 8.9) | US$4.49 (4.27 to 4.69) | 300 |
| A, Gemini 3.8 Flash on the image | 71.7% (67.5 to 75.6) | 1.7% (0.3 to 3.3) | 6.0% (4.9 to 7.3) | US$2.55 (2.30 to 2.81) | 300 |
| D, Claude Sonnet 5.5 on the OCR text | 71.6% (68.1 to 75.0) | 0.7% (0.0 to 1.7) | 8.2% (6.7 to 9.9) | US$4.63 (4.40 to 4.87) | 300 |
| E, OCR plus rules | 11.5% (8.9 to 14.4) | 0.7% (0.0 to 1.7) | 0.9% (0.7 to 1.1) | US$0.05 (0.04 to 0.05) | 300 |
| B, Gemma 4 E2B fine-tuned on the image | 60.2% (55.5 to 64.7) | 4.0% (2.0 to 6.3) | 7.2% (5.6 to 9.0) | US$0.17 (0.16 to 0.19) | 300 |
| B, Gemma 4 E4B fine-tuned on the image | 58.2% (53.0 to 63.2) | 6.3% (3.7 to 9.3) | 3.9% (2.7 to 5.3) | US$0.20 (0.18 to 0.21) | 300 |
| C, Gemma 4 E2B untuned on the image | 19.2% (16.8 to 21.9) | 0.0% (0.0 to 0.0) | 8.4% (6.6 to 10.4) | US$0.13 (0.12 to 0.14) | 300 |
| C, Gemma 4 E4B untuned on the image | 47.3% (43.9 to 50.9) | 0.0% (0.0 to 0.0) | 12.1% (10.0 to 14.4) | US$0.22 (0.21 to 0.24) | 300 |

**NIST, the 300 curve pages at each degradation level** (fields correct; what each level does to OCR is in [docs/degradation.md](docs/degradation.md))

| Arm | Level 0 | Level 1 | Level 2 | Level 3 | Level 4 |
|---|---|---|---|---|---|
| A, Claude Sonnet 5.5 on the image | 87.9% (85.8 to 89.9) | 86.9% (84.8 to 88.9) | 86.5% (84.1 to 88.8) | 87.0% (84.9 to 89.0) | 85.7% (83.5 to 87.8) |
| A, Claude Haiku 5.5 on the image | 86.4% (84.3 to 88.2) | 85.8% (83.7 to 87.7) | 84.7% (82.4 to 86.9) | 84.5% (82.1 to 86.7) | 82.9% (80.4 to 85.2) |
| A, GPT-6.1 Sol on the image | 94.9% (93.8 to 95.8) | 95.1% (93.7 to 96.2) | 94.8% (93.5 to 95.8) | 94.8% (93.6 to 95.7) | 91.8% (90.4 to 93.0) |
| A, Gemini 3.8 Flash on the image | 79.4% (74.4 to 84.0) | 76.8% (71.5 to 82.0) | 80.9% (76.0 to 85.6) | 77.2% (71.8 to 82.2) | 76.2% (71.1 to 81.1) |
| D, Claude Sonnet 5.5 on the OCR text | 37.4% (34.5 to 40.5) | 10.4% (8.9 to 11.9) | 8.3% (7.0 to 9.7) | 4.5% (3.7 to 5.4) | 1.0% (0.7 to 1.4) |
| E, OCR plus rules | 16.2% (14.4 to 18.1) | 4.9% (4.2 to 5.7) | 4.5% (3.8 to 5.3) | 2.3% (1.9 to 2.8) | 0.5% (0.3 to 0.7) |
| B, Gemma 4 E2B fine-tuned on the image | 74.9% (71.3 to 78.3) | 75.4% (72.0 to 78.8) | 73.9% (69.9 to 77.8) | 72.1% (68.4 to 75.6) | 68.7% (64.9 to 72.4) |
| B, Gemma 4 E4B fine-tuned on the image | 74.9% (70.9 to 78.6) | 75.6% (72.1 to 78.8) | 77.5% (74.5 to 80.3) | 75.1% (71.5 to 78.5) | 72.6% (69.4 to 75.7) |
| C, Gemma 4 E2B untuned on the image | 14.5% (12.9 to 16.2) | 13.3% (11.8 to 14.8) | 13.4% (12.0 to 15.0) | 13.6% (12.2 to 15.1) | 12.3% (11.0 to 13.7) |
| C, Gemma 4 E4B untuned on the image | 16.0% (14.0 to 18.0) | 16.2% (14.2 to 18.4) | 16.8% (14.6 to 19.0) | 15.9% (13.8 to 18.1) | 14.4% (12.4 to 16.4) |
| F, Azure Document Intelligence | 72.9% (70.4 to 75.3) | 72.0% (69.5 to 74.4) | 71.0% (68.5 to 73.3) | 69.5% (67.0 to 71.9) | 63.4% (60.7 to 66.0) |

**FARA, the 39 unseen-template test documents of the VRDU curve subset at levels 0, 2 and 4** (fields correct; real scans beside the NIST curve)

| Arm | Level 0 | Level 2 | Level 4 |
|---|---|---|---|
| A, Claude Sonnet 5.5 on the image | 72.9% (65.5 to 79.8) | 70.1% (61.8 to 78.0) | 71.4% (63.5 to 79.1) |
| A, Claude Haiku 5.5 on the image | 68.6% (60.5 to 76.4) | 69.3% (61.7 to 76.6) | 68.1% (59.8 to 75.9) |
| A, GPT-6.1 Sol on the image | 65.7% (56.9 to 74.2) | 66.8% (58.5 to 75.0) | 65.2% (56.6 to 73.6) |
| A, Gemini 3.8 Flash on the image | 72.9% (65.5 to 80.0) | 73.1% (65.6 to 80.1) | 69.8% (61.5 to 77.6) |
| D, Claude Sonnet 5.5 on the OCR text | 62.6% (52.6 to 72.0) | 62.3% (53.4 to 70.9) | 27.5% (19.2 to 36.0) |
| E, OCR plus rules | 10.3% (5.2 to 16.0) |  |  |
| B, Gemma 4 E2B fine-tuned on the image | 61.7% (52.8 to 70.3) | 60.2% (51.8 to 68.4) | 56.9% (47.9 to 65.7) |
| B, Gemma 4 E4B fine-tuned on the image | 56.5% (48.5 to 64.9) | 57.5% (49.6 to 65.4) | 57.0% (49.8 to 64.8) |
| C, Gemma 4 E2B untuned on the image | 53.0% (45.9 to 60.1) | 55.1% (47.8 to 62.2) | 55.9% (48.6 to 63.0) |
| C, Gemma 4 E4B untuned on the image | 61.1% (52.6 to 69.6) | 62.0% (53.3 to 70.6) | 63.9% (55.1 to 72.7) |

**DeepForm, the 30 unseen-template test documents of the VRDU curve subset at levels 0, 2 and 4** (fields correct; real scans beside the NIST curve)

| Arm | Level 0 | Level 2 | Level 4 |
|---|---|---|---|
| A, Claude Sonnet 5.5 on the image | 78.2% (68.4 to 85.2) | 77.0% (68.0 to 83.9) | 74.6% (65.5 to 82.5) |
| A, Claude Haiku 5.5 on the image | 69.6% (56.9 to 80.2) | 70.0% (59.2 to 79.1) | 68.5% (56.6 to 78.8) |
| A, GPT-6.1 Sol on the image | 80.6% (71.6 to 87.2) | 79.7% (70.7 to 86.3) | 78.0% (69.8 to 84.9) |
| A, Gemini 3.8 Flash on the image | 62.5% (41.5 to 81.6) | 81.5% (73.8 to 87.1) | 78.9% (69.4 to 85.7) |
| D, Claude Sonnet 5.5 on the OCR text | 78.8% (69.9 to 85.4) | 72.9% (61.1 to 81.3) | 18.8% (4.1 to 36.3) |
| E, OCR plus rules | 13.8% (6.6 to 25.1) |  |  |
| B, Gemma 4 E2B fine-tuned on the image | 66.4% (52.2 to 77.7) | 61.3% (46.5 to 73.4) | 57.1% (43.1 to 69.1) |
| B, Gemma 4 E4B fine-tuned on the image | 67.7% (53.3 to 79.1) | 64.0% (49.2 to 75.5) | 63.0% (47.8 to 75.6) |
| C, Gemma 4 E2B untuned on the image | 19.0% (11.1 to 28.6) | 24.7% (16.8 to 33.4) | 27.0% (19.5 to 35.2) |
| C, Gemma 4 E4B untuned on the image | 52.8% (44.1 to 61.6) | 49.5% (40.6 to 59.1) | 51.8% (44.0 to 59.0) |

**The verifier on test: the share of wrong fields its rules flag, over every field and over the fields a rule reads, and the share of right fields flagged** (legible/verify_rules.py; each rule kept only where the training truth obeys it on 99% of documents, docs/verify-rules.md). FARA has one rule, a registration number's digits; NIST the 1988 forms' sums. No rule held for DeepForm's dates or CORD's arithmetic, so neither has a verifier.

| Arm | FARA, unseen templates | NIST |
|---|---|---|
| A, Claude Sonnet 5.5 on the image | 0.0% (0.0 to 0.0); where a rule looks 0.0% (0.0 to 0.0); false alarms 0.4% (0.2 to 0.6) | 1.9% (0.6 to 3.4); where a rule looks 12.2% (3.9 to 24.3); false alarms 0.3% (0.0 to 0.6) |
| A, Claude Haiku 5.5 on the image | 0.3% (0.0 to 0.6); where a rule looks 11.1% (0.0 to 25.0); false alarms 0.4% (0.2 to 0.6) | 5.4% (2.6 to 8.6); where a rule looks 64.4% (41.5 to 83.5); false alarms 4.9% (3.5 to 6.4) |
| A, GPT-6.1 Sol on the image | 0.1% (0.0 to 0.2); where a rule looks 6.2% (0.0 to 21.1); false alarms 0.4% (0.2 to 0.7) | 3.2% (1.6 to 5.1); where a rule looks 27.0% (12.4 to 57.7); false alarms 5.6% (4.1 to 7.1) |
| A, Gemini 3.8 Flash on the image | 0.0% (0.0 to 0.0); where a rule looks 0.0% (0.0 to 0.0); false alarms 0.4% (0.2 to 0.6) | 0.0% (0.0 to 0.0); where a rule looks 0.0% (0.0 to 0.0); false alarms 0.6% (0.2 to 1.0) |
| D, Claude Sonnet 5.5 on the OCR text | 0.9% (0.5 to 1.5); where a rule looks 10.3% (5.4 to 15.9); false alarms 0.4% (0.2 to 0.7) | 9.6% (8.1 to 11.3); where a rule looks 58.3% (52.3 to 64.5); false alarms 10.0% (8.0 to 12.1) |
| E, OCR plus rules | 0.0% (0.0 to 0.0); where a rule looks 0.0% (0.0 to 0.0); false alarms 0.0% (0.0 to 0.0) | 8.6% (7.4 to 9.8); where a rule looks 47.6% (43.7 to 51.7); false alarms 10.9% (8.5 to 13.6) |
| B, Gemma 4 E2B fine-tuned on the image | 0.5% (0.1 to 0.9); where a rule looks 21.2% (7.7 to 35.7); false alarms 0.2% (0.1 to 0.4) | 3.6% (2.3 to 5.2); where a rule looks 62.6% (47.4 to 77.1); false alarms 2.0% (1.3 to 2.8) |
| B, Gemma 4 E4B fine-tuned on the image | 0.3% (0.1 to 0.6); where a rule looks 13.9% (3.2 to 26.3); false alarms 0.5% (0.3 to 0.8) | 1.5% (0.8 to 2.2); where a rule looks 21.7% (12.8 to 33.8); false alarms 1.2% (0.6 to 1.8) |
| C, Gemma 4 E2B untuned on the image | 0.2% (0.1 to 0.4); where a rule looks 16.0% (3.6 to 32.0); false alarms 0.5% (0.3 to 0.8) | 15.1% (12.9 to 17.4); where a rule looks 70.1% (64.8 to 74.8); false alarms 8.3% (6.2 to 10.6) |
| C, Gemma 4 E4B untuned on the image | 0.4% (0.1 to 0.8); where a rule looks 23.1% (7.7 to 40.9); false alarms 0.4% (0.2 to 0.6) | 13.2% (11.0 to 15.5); where a rule looks 63.4% (57.7 to 68.6); false alarms 6.2% (4.4 to 8.1) |
| F, Azure Document Intelligence | 0.5% (0.1 to 0.9); where a rule looks 41.2% (16.7 to 66.7); false alarms 0.7% (0.4 to 1.0) | 10.1% (7.9 to 12.4); where a rule looks 52.1% (44.5 to 59.1); false alarms 4.6% (3.7 to 5.5) |

**Non-inferiority through the 03 gate** (docs/gate.md): the fine-tune with the better dev accuracy against the frontier vision model with the best, and against the cost anchor, one suite per field, one outcome per document, a 3-point margin, Holm's adjustment across the decided fields. A field the test set holds too few documents of to resolve 3 points is under-powered and not decided.

| Corpus | Candidate | Against | Verdict | Fields: pass, block, under-powered | Worst blocking fields (difference, 95% CI) |
|---|---|---|---|---|---|
| FARA, unseen templates | B, Gemma 4 E2B fine-tuned on the image | A, Gemini 3.8 Flash on the image | **block** | 0, 6, 0 | `registrant_name` -26.9% (-30.0 to -23.8); `foreign_principle_name` -16.4% (-21.2 to -11.5) |
| FARA, unseen templates | B, Gemma 4 E2B fine-tuned on the image | A, Claude Haiku 5.5 on the image | **block** | 2, 4, 0 | `registrant_name` -16.6% (-19.5 to -13.9); `signer_name` -13.5% (-16.1 to -10.9) |
| FARA, mixed templates | B, Gemma 4 E2B fine-tuned on the image | A, Gemini 3.8 Flash on the image | **block** | 1, 4, 1 | `registrant_name` -8.0% (-11.4 to -5.0); `registration_num` -3.0% (-5.0 to -0.7) |
| FARA, mixed templates | B, Gemma 4 E2B fine-tuned on the image | A, Claude Haiku 5.5 on the image | **block** | 4, 1, 1 | `signer_name` +1.7% (-3.4 to +7.2) |
| DeepForm, unseen templates | B, Gemma 4 E4B fine-tuned on the image | A, GPT-6.1 Sol on the image | **block** | 0, 10, 4 | `line_item-channel` -32.2% (-41.8 to -22.6); `line_item-sub_amount` -25.0% (-33.6 to -16.4) |
| DeepForm, unseen templates | B, Gemma 4 E4B fine-tuned on the image | A, Claude Haiku 5.5 on the image | **block** | 0, 9, 5 | `line_item-channel` -29.6% (-38.8 to -19.7); `contract_num` -23.3% (-30.2 to -15.7) |
| DeepForm, mixed templates | B, Gemma 4 E4B fine-tuned on the image | A, GPT-6.1 Sol on the image | **block** | 1, 13, 0 | `line_item-channel` -32.8% (-39.6 to -26.1); `contract_num` -27.9% (-33.8 to -22.1) |
| DeepForm, mixed templates | B, Gemma 4 E4B fine-tuned on the image | A, Claude Haiku 5.5 on the image | **block** | 1, 13, 0 | `line_item-channel` -30.5% (-37.3 to -23.7); `contract_num` -27.1% (-33.1 to -21.4) |
| CORD | B, Gemma 4 E4B fine-tuned on the image | A, Gemini 3.8 Flash on the image | no decision: every field under-powered at 3 points | 0, 0, 30 | none |
| CORD | B, Gemma 4 E4B fine-tuned on the image | A, Claude Haiku 5.5 on the image | no decision: every field under-powered at 3 points | 0, 0, 30 | none |
| NIST | B, Gemma 4 E4B fine-tuned on the image | A, GPT-6.1 Sol on the image | no decision: every field under-powered at 3 points | 0, 0, 1113 | none |
| NIST | B, Gemma 4 E4B fine-tuned on the image | A, Claude Haiku 5.5 on the image | no decision: every field under-powered at 3 points | 0, 0, 1113 | none |

**Review at 99%: Sonnet 5.5 on the image, each field checked against Sonnet 5.5 on the OCR text.** A field is accepted when the two reads agree; the threshold is chosen on dev and applied once to test (legible/review.py, legible/agreement.py).

| Corpus | Fields sent to a person (95% CI) | Accuracy of the fields accepted | Reached 99% on dev |
|---|---|---|---|
| FARA, unseen templates | 100.0% (100.0 to 100.0) | none accepted | no: fields the two reads agree on are right less than 99% of the time on dev, so every field goes to a person |
| DeepForm, unseen templates | 100.0% (100.0 to 100.0) | none accepted | no: fields the two reads agree on are right less than 99% of the time on dev, so every field goes to a person |
| CORD | 100.0% (100.0 to 100.0) | none accepted | no: fields the two reads agree on are right less than 99% of the time on dev, so every field goes to a person |
| NIST | 100.0% (100.0 to 100.0) | none accepted | no: fields the two reads agree on are right less than 99% of the time on dev, so every field goes to a person |

**Review at 99%: Gemma 4 E2B fine-tuned (seed 0), each field's confidence the lowest probability among the tokens of its value.** Read a second time with log-probabilities for this table (PLAN.md 2.6); the threshold is chosen on that dev read and applied once to its test read (legible/tokenconf.py).

| Corpus | Fields sent to a person (95% CI) | Accuracy of the fields accepted | Reached 99% on dev |
|---|---|---|---|
| FARA, unseen templates | 100.0% (100.0 to 100.0) | none accepted | no: at no token probability are the fields above it right 99% of the time on dev, so every field goes to a person |
| DeepForm, unseen templates | 100.0% (100.0 to 100.0) | none accepted on test | yes, 100.0% on dev |
| CORD | 100.0% (100.0 to 100.0) | none accepted | no: at no token probability are the fields above it right 99% of the time on dev, so every field goes to a person |
| NIST | 100.0% (100.0 to 100.0) | none accepted | no: at no token probability are the fields above it right 99% of the time on dev, so every field goes to a person |

**Review at 99%: Gemma 4 E4B fine-tuned (seed 0), each field's confidence the lowest probability among the tokens of its value.** Read a second time with log-probabilities for this table (PLAN.md 2.6); the threshold is chosen on that dev read and applied once to its test read (legible/tokenconf.py).

| Corpus | Fields sent to a person (95% CI) | Accuracy of the fields accepted | Reached 99% on dev |
|---|---|---|---|
| FARA, unseen templates | 100.0% (100.0 to 100.0) | none accepted | no: at no token probability are the fields above it right 99% of the time on dev, so every field goes to a person |
| DeepForm, unseen templates | 99.8% (99.5 to 99.9) | 82.8% (50.0 to 100.0) | yes, 100.0% on dev |
| CORD | 100.0% (100.0 to 100.0) | none accepted | no: at no token probability are the fields above it right 99% of the time on dev, so every field goes to a person |
| NIST | 100.0% (100.0 to 100.0) | none accepted | no: at no token probability are the fields above it right 99% of the time on dev, so every field goes to a person |

**The ceiling: Claude Opus 5.5, the dearest Anthropic model, on a subset of the headline test documents, beside Sonnet 5.5's reads of the same documents** (legible/data/subsets.py; batch rate; fields correct with 95% CI over documents).

| Corpus | Documents | Opus 5.5 | Sonnet 5.5 | Opus cost per 1,000 pages | Sonnet cost |
|---|---:|---|---|---|---|
| FARA | 101 | 79.9% (75.9 to 83.7) | 81.8% (78.2 to 85.2) | US$6.35 (6.22 to 6.49) | US$2.97 (2.94 to 3.00) |
| DeepForm | 60 | 65.9% (58.4 to 73.3) | 67.1% (59.8 to 74.3) | US$10.60 (9.91 to 11.35) | US$5.07 (4.76 to 5.39) |
| CORD | 50 | 93.5% (90.2 to 96.4) | 83.8% (74.6 to 91.3) | US$11.32 (10.54 to 12.16) | US$5.43 (5.12 to 5.78) |
| NIST | 200 | 94.1% (92.1 to 95.8) | 85.4% (82.3 to 88.3) | US$35.49 (33.02 to 38.10) | US$16.36 (15.22 to 17.58) |

**The noise floor: Sonnet 5.5 reading the repeat subset a second time**, the same request at the vendor's default sampling, days after the first. A difference between two arms smaller than the share of fields one arm changes on itself is not a difference.

| Corpus | Documents | First read | Second read | Fields whose outcome changed |
|---|---:|---|---|---|
| FARA | 35 | 80.1% (74.6 to 85.3) | 79.6% (74.2 to 84.7) | 0.6% (0.0 to 1.7) |
| DeepForm | 18 | 66.7% (54.6 to 78.2) | 66.9% (54.8 to 78.3) | 0.3% (0.0 to 1.0) |
| CORD | 30 | 91.4% (87.4 to 94.9) | 90.0% (85.6 to 93.8) | 3.0% (0.6 to 6.2) |
| NIST | 50 | 83.7% (76.4 to 89.8) | 88.6% (84.4 to 92.5) | 7.3% (2.4 to 14.5) |

**The ablations** (legible/train/ablate.py, PLAN.md 2.3): each change to the recipe trained on E2B at seed 0 and read like the headline models, against the seed-0 E2B it changes; the difference is paired over the documents both read, in points of fields correct, with its 95% interval.

*Visual tokens: E2B at 560 a page against the headline's 1,120*

| Set | Documents | E2B, 1,120 visual tokens | E2B, 560 visual tokens | Difference | Cost per 1,000 pages, 1,120 visual tokens | Cost per 1,000 pages, 560 visual tokens |
|---|---:|---|---|---|---|---|
| FARA, unseen templates | 900 | 69.0% (67.2 to 70.7) | 65.4% (63.8 to 66.9) | -3.6 (-4.9 to -2.3) | US$0.06 (0.06 to 0.06) | US$0.03 (0.03 to 0.03) |
| DeepForm, unseen templates | 159 | 55.3% (48.5 to 62.0) | 45.3% (39.3 to 51.5) | -10.0 (-17.0 to -3.2) | US$0.19 (0.17 to 0.21) | US$0.18 (0.16 to 0.20) |
| CORD | 100 | 75.2% (67.9 to 82.0) | 70.8% (65.0 to 76.5) | -4.4 (-8.2 to -0.5) | US$0.11 (0.11 to 0.11) | US$0.08 (0.08 to 0.08) |
| NIST | 500 | 73.6% (70.4 to 76.7) | not yet measured |  | US$0.40 (0.38 to 0.42) |  |
| NIST curve, level 2 | 300 | 73.9% (69.9 to 77.8) | not yet measured |  | US$0.42 (0.39 to 0.45) |  |
| NIST curve, level 3 | 300 | 72.1% (68.4 to 75.6) | not yet measured |  | US$0.42 (0.39 to 0.45) |  |
| NIST curve, level 4 | 300 | 68.7% (64.9 to 72.4) | not yet measured |  | US$0.42 (0.39 to 0.45) |  |
| FARA, VRDU curve subset, level 4 | 39 | 56.9% (47.9 to 65.7) | 54.5% (46.4 to 62.8) | -2.4 (-7.9 to +2.9) | US$0.07 (0.06 to 0.07) | US$0.04 (0.04 to 0.05) |
| DeepForm, VRDU curve subset, level 4 | 30 | 57.1% (43.1 to 69.1) | 46.4% (29.2 to 64.6) | -10.7 (-27.2 to +1.9) | US$0.32 (0.25 to 0.41) | US$0.22 (0.17 to 0.28) |

*Data volume: E2B on half and a quarter of the training documents*

| Set | Documents | E2B, 800 documents | E2B, 400 documents | Difference | E2B, 200 documents | Difference |
|---|---:|---|---|---|---|---|
| CORD | 100 | 75.2% (67.9 to 82.0) | 63.5% (57.7 to 69.4) | -11.7 (-15.8 to -7.9) | 57.5% (52.5 to 62.5) | -17.7 (-22.6 to -12.3) |
| NIST | 500 | 73.6% (70.4 to 76.7) | 63.1% (59.7 to 66.4) | -10.6 (-13.1 to -8.2) | 36.7% (34.4 to 39.1) | -37.0 (-39.9 to -34.0) |

*One model for every corpus against one per corpus, E2B*

| Set | Documents | E2B, one model per corpus | E2B, one model for every corpus | Difference |
|---|---:|---|---|---|
| FARA, mixed templates | 300 | 75.7% (73.0 to 78.3) | 82.5% (80.0 to 85.0) | +6.9 (+5.0 to +8.8) |
| DeepForm, mixed templates | 300 | 60.2% (55.5 to 64.7) | 55.1% (50.0 to 60.0) | -5.1 (-9.0 to -1.5) |
| CORD | 100 | 75.2% (67.9 to 82.0) | 74.7% (68.3 to 80.8) | -0.5 (-3.8 to +2.4) |
| NIST | 500 | 73.6% (70.4 to 76.7) | 65.8% (62.8 to 68.7) | -7.8 (-9.9 to -5.8) |

**Latency and throughput of the fine-tunes**, one served at a time on one RTX 3090 (US$0.50 an hour, RunPod Secure Cloud, 2026-10-23), read through the gateway by 06's closed-loop client on the model's own test documents at level 0, the accuracy runs' requests cycled in order (docs/serving.md). A read is one document, every page of it; latency is per read, intervals are 95% bootstrap over reads, and the first 30 seconds of each level are discarded. The throughput interval resamples reads with the window fixed, as 06's does, so it has no width where every read is one page and none failed.

| Fine-tune | In flight | Reads (errors) | Pages a read | Read p50 (95% CI) | Read p99 | First token p50 | Pages a second | Cost per 1,000 pages, GPU kept busy |
|---|---:|---:|---:|---|---|---|---|---|
| E2B, FARA (amendment template) | 1 | 111 (0) | 2.0 | 1.5 s (1.5 to 1.6) | 2.7 s (2.2 to 9.0) | 1.0 s (1.0 to 1.0) | 1.17 (1.10 to 1.23) | US$0.12 |
| E2B, FARA (amendment template) | 8 | 358 (0) | 2.0 | 1.8 s (1.7 to 2.5) | 12.1 s (10.7 to 12.8) | 1.1 s (1.0 to 1.6) | 4.15 (4.06 to 4.24) | US$0.03 |
| E2B, FARA (amendment template) | 32 | 748 (0) | 2.0 | 7.7 s (7.6 to 7.9) | 14.6 s (14.2 to 14.9) | 7.2 s (7.0 to 7.3) | 7.86 (7.74 to 7.99) | US$0.02 |
| E4B, FARA (amendment template) | 1 | 90 (0) | 1.9 | 2.2 s (2.1 to 2.2) | 16.1 s (3.0 to 16.1) | 1.2 s (1.2 to 1.2) | 0.78 (0.72 to 0.83) | US$0.18 |
| E4B, FARA (amendment template) | 8 | 166 (0) | 2.0 | 8.3 s (8.0 to 8.4) | 15.8 s (12.0 to 95.8) | 2.7 s (2.3 to 2.8) | 1.86 (1.80 to 1.93) | US$0.07 |
| E4B, FARA (amendment template) | 32 | 288 (0) | 2.0 | 30.1 s (29.9 to 30.4) | 62.8 s (47.9 to 260.4) | 8.8 s (7.9 to 9.5) | 2.08 (2.03 to 2.13) | US$0.07 |
| E2B, DeepForm | 1 | 98 (0) | 2.7 | 8.9 s (7.3 to 11.8) | 91.9 s (72.9 to 91.9) | 1.5 s (1.1 to 1.6) | 0.14 (0.13 to 0.16) | US$0.97 |
| E2B, DeepForm | 8 | 79 (0) | 2.7 | 9.7 s (7.8 to 12.3) | 87.3 s (86.0 to 87.3) | 0.1 s (0.1 to 0.2) | 0.82 (0.71 to 0.92) | US$0.17 |
| E2B, DeepForm | 32 | 239 (0) | 2.6 | 19.2 s (17.5 to 22.5) | 164.8 s (120.4 to 172.1) | 5.0 s (4.0 to 6.0) | 1.79 (1.66 to 1.93) | US$0.08 |
| E4B, DeepForm | 1 | 97 (0) | 2.7 | 13.0 s (10.4 to 16.9) | 130.5 s (128.5 to 130.5) | 1.7 s (1.3 to 1.9) | 0.13 (0.12 to 0.15) | US$1.06 |
| E4B, DeepForm | 8 | 87 (0) | 2.7 | 18.6 s (15.3 to 21.9) | 208.4 s (78.4 to 208.4) | 1.6 s (1.4 to 1.6) | 0.54 (0.48 to 0.61) | US$0.26 |
| E4B, DeepForm | 32 | 288 (0) | 2.6 | 40.6 s (34.8 to 45.6) | 358.7 s (244.1 to 475.3) | 2.8 s (2.4 to 3.2) | 1.05 (0.98 to 1.12) | US$0.13 |
| E2B, CORD | 1 | 86 (0) | 1.0 | 2.3 s (2.2 to 2.4) | 16.4 s (5.5 to 16.4) | 0.6 s (0.6 to 0.6) | 0.35 (0.35 to 0.35) | US$0.39 |
| E2B, CORD | 8 | 536 (0) | 1.0 | 2.2 s (2.2 to 2.2) | 16.5 s (6.6 to 18.8) | 0.1 s (0.1 to 0.1) | 2.76 (2.76 to 2.76) | US$0.05 |
| E2B, CORD | 32 | 1623 (0) | 1.0 | 2.9 s (2.8 to 2.9) | 8.9 s (8.7 to 24.3) | 0.1 s (0.1 to 0.1) | 8.54 (8.54 to 8.54) | US$0.02 |
| E4B, CORD | 1 | 92 (0) | 1.0 | 4.0 s (3.9 to 4.2) | 10.4 s (9.4 to 10.4) | 0.7 s (0.7 to 0.7) | 0.22 (0.22 to 0.22) | US$0.63 |
| E4B, CORD | 8 | 157 (0) | 1.0 | 7.8 s (7.3 to 8.2) | 22.5 s (20.5 to 64.6) | 0.8 s (0.7 to 1.0) | 0.83 (0.83 to 0.83) | US$0.17 |
| E4B, CORD | 32 | 277 (0) | 1.0 | 20.9 s (20.1 to 21.6) | 61.1 s (54.2 to 64.3) | 1.3 s (1.2 to 1.3) | 1.25 (1.25 to 1.25) | US$0.11 |
| E2B, NIST | 1 | 97 (0) | 1.0 | 13.3 s (13.2 to 13.3) | 13.7 s (13.6 to 13.7) | 1.4 s (1.4 to 1.4) | 0.08 (0.08 to 0.08) | US$1.70 |
| E2B, NIST | 8 | 101 (0) | 1.0 | 14.8 s (14.7 to 14.9) | 20.1 s (19.0 to 20.1) | 0.1 s (0.1 to 0.1) | 0.54 (0.54 to 0.54) | US$0.26 |
| E2B, NIST | 32 | 256 (0) | 1.0 | 35.3 s (34.0 to 37.0) | 92.7 s (85.3 to 115.4) | 1.7 s (1.5 to 1.8) | 0.76 (0.76 to 0.76) | US$0.18 |
| E4B, NIST | 1 | 98 (0) | 1.0 | 23.8 s (23.6 to 23.9) | 25.5 s (24.7 to 25.5) | 2.0 s (2.0 to 2.0) | 0.05 (0.05 to 0.05) | US$3.04 |
| E4B, NIST | 8 | 92 (0) | 1.0 | 39.4 s (38.5 to 39.6) | 46.3 s (44.1 to 46.3) | 2.0 s (1.9 to 2.0) | 0.22 (0.22 to 0.22) | US$0.64 |
| E4B, NIST | 32 | 288 (0) | 1.0 | 69.8 s (64.9 to 74.7) | 207.8 s (192.0 to 236.5) | 8.0 s (6.2 to 11.1) | 0.37 (0.37 to 0.37) | US$0.37 |

**Break-even, FARA: pages a month at which renting the card for the E2B, FARA (amendment template) fine-tune costs no more than paying each frontier model, or Azure Document Intelligence, by the page**, over the share of the month the card is kept busy (10% to 90%). 06's arithmetic (legible/bench/breakeven.py): whole cards rented all month, each frontier model at its headline test cost from the ledger. Below the utilisation given it never breaks even; above it the volume holds while one card carries it. It says nothing about accuracy, which the tables above do.

The fine-tune at its best measured throughput, 7.86 (7.74 to 7.99) pages a second at 32 in flight on one RTX 3090 at US$0.50 an hour (RunPod Secure Cloud, 2026-10-23): US$0.18 per 1,000 pages at 10% utilisation, US$0.02 at 90%. No fixed cost; 730.5 hours a month.

| Paid by the page | Its cost per 1,000 pages | Breaks even from utilisation | Pages a month there (cards) | Pages a month at 90% (cards) |
|---|---:|---:|---:|---:|
| Claude Sonnet 5.5 | US$2.96 | 10% | 123,226 (1) | 123,226 (1) |
| Claude Haiku 5.5 | US$0.18 | 20% | 2.1 million (1) | 2.1 million (1) |
| GPT-6.1 Sol | US$2.78 | 10% | 131,514 (1) | 131,514 (1) |
| Gemini 3.8 Flash | US$1.65 | 10% | 221,213 (1) | 221,213 (1) |
| Azure Document Intelligence | US$30.00 | 10% | 12,175 (1) | 12,175 (1) |

**Break-even, DeepForm: pages a month at which renting the card for the E4B, DeepForm fine-tune costs no more than paying each frontier model, or Azure Document Intelligence, by the page**, over the share of the month the card is kept busy (10% to 90%). 06's arithmetic (legible/bench/breakeven.py): whole cards rented all month, each frontier model at its headline test cost from the ledger. Below the utilisation given it never breaks even; above it the volume holds while one card carries it. It says nothing about accuracy, which the tables above do.

The fine-tune at its best measured throughput, 1.05 (0.98 to 1.12) pages a second at 32 in flight on one RTX 3090 at US$0.50 an hour (RunPod Secure Cloud, 2026-10-23): US$1.32 per 1,000 pages at 10% utilisation, US$0.15 at 90%. No fixed cost; 730.5 hours a month.

| Paid by the page | Its cost per 1,000 pages | Breaks even from utilisation | Pages a month there (cards) | Pages a month at 90% (cards) |
|---|---:|---:|---:|---:|
| Claude Sonnet 5.5 | US$5.19 | 10% | 70,432 (1) | 70,432 (1) |
| Claude Haiku 5.5 | US$0.35 | 40% | 1.0 million (1) | 1.0 million (1) |
| GPT-6.1 Sol | US$4.53 | 10% | 80,576 (1) | 80,576 (1) |
| Gemini 3.8 Flash | US$2.73 | 10% | 133,787 (1) | 133,787 (1) |
| Azure Document Intelligence | US$30.00 | 10% | 12,175 (1) | 12,175 (1) |

**Break-even, CORD: pages a month at which renting the card for the E4B, CORD fine-tune costs no more than paying each frontier model, or Azure Document Intelligence, by the page**, over the share of the month the card is kept busy (10% to 90%). 06's arithmetic (legible/bench/breakeven.py): whole cards rented all month, each frontier model at its headline test cost from the ledger. Below the utilisation given it never breaks even; above it the volume holds while one card carries it. It says nothing about accuracy, which the tables above do.

The fine-tune at its best measured throughput, 1.25 (1.25 to 1.25) pages a second at 32 in flight on one RTX 3090 at US$0.50 an hour (RunPod Secure Cloud, 2026-10-23): US$1.11 per 1,000 pages at 10% utilisation, US$0.12 at 90%. No fixed cost; 730.5 hours a month.

| Paid by the page | Its cost per 1,000 pages | Breaks even from utilisation | Pages a month there (cards) | Pages a month at 90% (cards) |
|---|---:|---:|---:|---:|
| Claude Sonnet 5.5 | US$5.27 | 10% | 69,340 (1) | 69,340 (1) |
| Claude Haiku 5.5 | US$0.38 | 30% | 951,474 (1) | 951,474 (1) |
| GPT-6.1 Sol | US$4.59 | 10% | 79,577 (1) | 79,577 (1) |
| Gemini 3.8 Flash | US$4.42 | 10% | 82,565 (1) | 82,565 (1) |
| Azure Document Intelligence | US$10.00 | 10% | 36,525 (1) | 36,525 (1) |

**Break-even, NIST: pages a month at which renting the card for the E4B, NIST fine-tune costs no more than paying each frontier model, or Azure Document Intelligence, by the page**, over the share of the month the card is kept busy (10% to 90%). 06's arithmetic (legible/bench/breakeven.py): whole cards rented all month, each frontier model at its headline test cost from the ledger. Below the utilisation given it never breaks even; above it the volume holds while one card carries it. It says nothing about accuracy, which the tables above do.

The fine-tune at its best measured throughput, 0.37 (0.37 to 0.37) pages a second at 32 in flight on one RTX 3090 at US$0.50 an hour (RunPod Secure Cloud, 2026-10-23): US$3.73 per 1,000 pages at 10% utilisation, US$0.41 at 90%. No fixed cost; 730.5 hours a month.

| Paid by the page | Its cost per 1,000 pages | Breaks even from utilisation | Pages a month there (cards) | Pages a month at 90% (cards) |
|---|---:|---:|---:|---:|
| Claude Sonnet 5.5 | US$16.38 | 10% | 22,298 (1) | 22,298 (1) |
| Claude Haiku 5.5 | US$1.12 | 40% | 325,098 (1) | 325,098 (1) |
| GPT-6.1 Sol | US$15.33 | 10% | 23,828 (1) | 23,828 (1) |
| Gemini 3.8 Flash | US$12.48 | 10% | 29,259 (1) | 29,259 (1) |
| Azure Document Intelligence | US$30.00 | 10% | 12,175 (1) | 12,175 (1) |

Arms B and C read through vLLM on an RTX 3090 at temperature 0, unconstrained (held to the schema's grammar, the fine-tunes left their trained format: docs/training.md), and are costed at the GPU's US$0.50 an hour on RunPod (2026-10-18) over the measured wall time of each read pass. B's row is seed 0, the model trained for that table's split; seeds 1 and 2 are the training variance. Latency is the fine-tunes' alone: the frontier models were read in batches, whose only latency is the batch's (docs/serving.md). Arm F is costed per page at Azure's prices read 2026-10-24, through the gateway; its 24 custom models took 18.72 training hours, US$26.16 past the ten free a month at US$3 an hour, which, like arm B's training, is not in the cost per page (docs/docintel.md).
<!-- results:end -->

## Tried and rejected

Three approaches were measured and dropped: the fine-tune's own token probability as the
signal for what a person must check, holding the fine-tunes to the schema's grammar, and
halving the visual tokens a page, which saved a few cents a thousand pages and cost 3.6 to
10.0 points of fields right. The evidence is in [docs/rejected.md](docs/rejected.md).

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
the diagrams are in [docs/architecture.md](docs/architecture.md). The demo site, each arm's
reads drawn on the pages at each scan quality beside these tables, is built by `legible site`
([docs/site.md](docs/site.md)).

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
