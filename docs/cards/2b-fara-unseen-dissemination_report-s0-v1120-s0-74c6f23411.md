---
base_model: google/gemma-4-E2B
base_model_revision: d29ff6b45f081a49ee2733a859c9c9c2d95d1a6f
library_name: peft
pipeline_tag: image-text-to-text
license: apache-2.0
language:
- en
tags:
- document-understanding
- form-extraction
- vision-language-model
- qlora
- lora
- gemma4
- legible
- fara
legible_run_id: 2b-fara-unseen-dissemination_report-s0-v1120-s0-74c6f23411
legible_publishable: true
# VRDU Registration Forms (FARA) is not on the Hugging Face Hub; its source is under Training data.
---

# Gemma 4 E2B fine-tuned to read FARA registration forms, Dissemination Report template held out

A QLoRA adapter on `google/gemma-4-E2B` that reads the page images of one document and writes its fields as JSON. Trained and measured in Forms That Read Themselves (package `legible`), which compares frontier vision models, fine-tuned small vision models and OCR pipelines on scanned forms with known answers. Run `2b-fara-unseen-dissemination_report-s0-v1120-s0-74c6f23411`. This card is written by `legible cards` from the run's records and graded reads; no number in it is typed by hand.

## What it reads and what it writes

Input: the document's pages as images, in page order, then the instruction every reader in the project is sent (`legible.prompt`, version 1), which describes each field and gives the JSON Schema. The adapter was trained on that instruction and nothing else.

One JSON object a document, every value a string or null, in the compact form it was trained on (`{"advertiser":null}`, no spaces). A US Department of Justice Foreign Agents Registration Act filing: a registration statement amendment, a short-form registration or a dissemination report.

| Field | Kind | What it is |
|---|---|---|
| `file_date` | date | The date the form was filed or signed. |
| `foreign_principle_name` | name | The name of the foreign principal the registrant acts for. |
| `registrant_name` | name | The name of the registrant. |
| `registration_num` | code | The registrant's FARA registration number. |
| `signer_name` | name | The name of the person who signed the form. |
| `signer_title` | string | The signer's title or position. |

## How it was trained

Project 06's QLoRA recipe with a vision encoder (`legible/train/vision.py`): one user turn of page images then the instruction, one assistant turn of the truth's JSON, the loss on the answer's tokens only. Every training document is from the split's train part; a held-out document refuses the set (`legible/train/dataset.py`).

| Setting | Value |
|---|---|
| Base | `google/gemma-4-E2B` at revision `d29ff6b45f081a49ee2733a859c9c9c2d95d1a6f` |
| Chat template | `google/gemma-4-E2B-it` at revision `3e22461f65e89153144f8adb70e3b8c2cc9845a7` |
| Quantisation | NF4 4-bit with double quantisation, bf16 compute; the vision and audio towers, the vision projector and the output layer kept at full precision |
| LoRA | rank 64, alpha 128, dropout 0.05, on the language model's attention and MLP projections and the vision projector, never the towers |
| Optimisation | learning rate 0.0001, cosine schedule, warmup 0.03, 1 epoch, 1 document a step, 8 steps accumulated |
| Visual tokens a page | 1,120 |
| Sequence limit | 12,288 tokens |
| Seed | 0 |
| Training set | `fara-unseen-dissemination_report-s0` (200 documents) |
| Training documents and pages | 200 documents, 417 pages |
| Optimiser steps | 25, from 200 documents at 8 a step |
| Loss and timing | in `run.json`, the training record uploaded with the adapter; it was not on the machine that wrote this card |
| Templates trained on | Amendment 103, Short-Form 97 |

## Training data and its licences

**VRDU Registration Forms (FARA)**, https://github.com/google-research-datasets/vrdu (registration-form). Terms: CC BY 4.0 for the benchmark's annotations; the pages are US public records, Foreign Agents Registration Act filings published by the Department of Justice.

> "We are excited to announce the public release of the VRDU dataset and evaluation code under a Creative Commons license."

Quoted from Google's release post, "Advances in document understanding" (2023-08-09), https://research.google/blog/advances-in-document-understanding/, where "Creative Commons license" links to https://creativecommons.org/licenses/by/4.0/. That hyperlink is the only statement of the variant; the repository has no licence file (read 2026-10-16). Attribution: Google Research's VRDU benchmark (Wang et al., "VRDU: A Benchmark for Visually-rich Document Understanding", KDD 2023), annotations used under CC BY 4.0.

The adapter is released under apache-2.0, the base model's licence. Publication: VRDU's annotations are CC BY 4.0 and the pages are public records the Department of Justice publishes for inspection; neither forbids a derived model. The forms name individuals, and an adapter trained on them can write a name it saw in training: it is uploaded private, and making it public is a decision recorded in docs/models.md, not a default.

## Results

On the 300 test documents of VRDU's split file `FARA-lv3-unk_Dissemination_Report-train_200-test_300-valid_100-SD_0`, templates never seen in training, read once, level 0, temperature 0, unconstrained. Field accuracy is VRDU's matchers, one grader for every reader; intervals are 95% bootstrap over documents. The adapter is costed at an RTX 3090 at US$0.50 an hour on RunPod (2026-10-18) over the measured wall time of its read; the frontier models at the gateway ledger's cost at the 2026-10-16 price list, batch rate.

| Reader | Fields correct (95% CI) | Every field right | Invented fields | Answers that did not parse | Cost per 1,000 pages | Documents |
|---|---|---|---|---|---|---:|
| B, Gemma 4 E2B fine-tuned (this adapter) | 84.4% (82.1 to 86.6) | 52.3% (46.7 to 58.0) | 0.8% (0.3 to 1.3) | 0.3% (0.0 to 1.0) | US$0.06 (0.06 to 0.06) | 300 |
| C, Gemma 4 E2B untuned on the image | 78.2% (76.1 to 80.3) | 28.3% (23.3 to 33.7) | 1.1% (0.6 to 1.6) | 0.0% (0.0 to 0.0) | US$0.06 (0.06 to 0.07) | 300 |
| A, Claude Sonnet 5.5 on the image | 90.2% (88.8 to 91.6) | 54.7% (49.0 to 60.3) | 1.4% (0.8 to 2.0) | 0.0% (0.0 to 0.0) | US$3.03 (3.01 to 3.05) | 300 |
| A, Claude Haiku 5.5 on the image | 91.0% (89.5 to 92.4) | 59.0% (53.3 to 64.7) | 0.9% (0.5 to 1.4) | 0.0% (0.0 to 0.0) | US$0.15 (0.15 to 0.16) | 300 |
| A, GPT-6.1 Sol on the image | 89.4% (88.0 to 90.8) | 50.0% (44.3 to 55.7) | 1.6% (1.0 to 2.2) | 0.0% (0.0 to 0.0) | US$2.68 (2.66 to 2.70) | 300 |
| A, Gemini 3.8 Flash on the image | 92.9% (91.5 to 94.2) | 68.7% (63.3 to 73.7) | 1.5% (0.9 to 2.1) | 0.0% (0.0 to 0.0) | US$1.30 (1.17 to 1.43) | 300 |

The best frontier model on these documents is Gemini 3.8 Flash, at 92.9% (91.5 to 94.2) of fields for US$1.30 (1.17 to 1.43) a thousand pages. This adapter's field accuracy differs from it by -8.5 points, at US$0.06 (0.06 to 0.06) a thousand pages, about 1/22 of the cost. Against its untuned base it reads +6.2 points.

In the README's FARA table the three held-out-template models of this size are pooled over the 900 unseen-template test documents:

| Reader | Fields correct (95% CI) | Every field right | Invented fields | Answers that did not parse | Cost per 1,000 pages | Documents |
|---|---|---|---|---|---|---:|
| B, Gemma 4 E2B fine-tuned on the image | 69.0% (67.2 to 70.7) | 29.6% (26.6 to 32.6) | 5.9% (5.2 to 6.6) | 0.4% (0.1 to 0.9) | US$0.06 (0.06 to 0.06) | 900 |
| A, Gemini 3.8 Flash on the image | 80.6% (79.4 to 81.9) | 38.4% (35.3 to 41.7) | 8.5% (7.7 to 9.2) | 0.1% (0.0 to 0.3) | US$1.65 (1.57 to 1.73) | 900 |

Training variance: the same recipe at seeds 1 and 2, each on its own split's test set: seed 1, 79.8% (77.4 to 82.1); seed 2, 76.8% (74.1 to 79.3). The three seeds' point estimates span 7.6 points (their test sets differ where the split files do).

### The 03 release gate

- Against Claude Haiku 5.5: **block** (fields pass, block, under-powered: 2, 4, 0); worst: `registrant_name` -16.6% (-19.5 to -13.9); `signer_name` -13.5% (-16.1 to -10.9).
- Against Gemini 3.8 Flash: **block** (fields pass, block, under-powered: 0, 6, 0); worst: `registrant_name` -26.9% (-30.0 to -23.8); `foreign_principle_name` -16.4% (-21.2 to -11.5).
- The FARA decisions pool the three held-out-template E2B models, this one among them, over FARA's unseen-template test documents.

## Failure modes

- **A form design it has not seen.** The README's two tables, templates seen in training and not, for this size and the best frontier model: Gemma 4 E2B 75.7% (73.0 to 78.3) on templates seen in training and 69.0% (67.2 to 70.7) on templates not seen (-6.7 points); Gemini 3.8 Flash 76.2% (74.0 to 78.4) on templates seen in training and 80.6% (79.4 to 81.9) on templates not seen (+4.5 points). A fine-tune learns which box a value sits in on the templates it saw, and on a new one puts values in the wrong field or leaves them out.
- **A bad scan.** On the 9 of its test documents in the VRDU curve subset, real scans, degraded in the project's five reproducible steps (docs/degradation.md): level 0 83.3% (68.5 to 96.3), level 2 85.2% (72.2 to 96.3), level 4 79.6% (63.0 to 94.4).
- **Confidently wrong.** Its own token probability is not a reason to skip review. Of its dev fields written at a token probability of 0.999 or more (21), 0.0% (0.0 to 0.0) are right; the commonest error there is a null where the form carries a value (21). At 99% accuracy it sends 100.0% (100.0 to 100.0) of its test fields to a person, since no threshold reached 99% on dev. docs/rejected.md reports this family's case: pooled over the three held-out templates, the E2B's surest FARA dev fields are nulls where the form carries a value. The probability measures how sure the model is of its habit, not whether the page agrees (docs/review.md).
- **Training variance.** The same recipe at three seeds reads from 76.8% to 84.4% of fields on test (above); a retrained copy is not guaranteed to read like this one.
- **Not non-inferior to the frontier.** Project 03's gate blocks on this corpus at a 3-point margin per field (above). Do not take it as a drop-in for a frontier model's read.
- **Malformed answers.** 0.3% (0.0 to 1.0) of its test answers did not parse as JSON. It is read freely: holding the fine-tunes to the schema's grammar was tried on dev and rejected, because it pushed them off their trained spacing and the DeepForm E2B then answered null for every field (docs/rejected.md). A caller must count a parse failure as a document to type by hand.
- **Invented fields.** 0.8% (0.3 to 1.3) of scored fields carry a value where the form's box is blank.
- **One instruction.** Trained on one prompt and one schema; another wording, another field list or another language is untested.
- **Personal data.** The registration forms name individuals (registrants, signers, foreign principals). They are public records, but a model trained on 200 of them can write a name from its training forms onto a page that does not carry it.

## Intended use

Reading FARA registration forms of the kind it was trained on into JSON for a person to check, at a fraction of a frontier model's cost per page; and reproducing the measurements in this card. Plan on a person checking every field: no confidence measured in the project separates right fields from wrong ones well enough to skip review at 99% (the README's honest limitation).

## Out of scope

- Any decision about a person made on its output without a person checking it.
- Handwriting, other form families, long multi-page documents, or a form whose type is unknown.
- Unattended use on form designs it was not trained on, where it is worst.
- Pages that are not public: it was measured on public records and datasets only.

## Loading it

```python
from peft import PeftModel
from transformers import AutoModelForImageTextToText, AutoProcessor

base = AutoModelForImageTextToText.from_pretrained("google/gemma-4-E2B", revision="d29ff6b45f081a49ee2733a859c9c9c2d95d1a6f")
model = PeftModel.from_pretrained(base, "<this repository>")
processor = AutoProcessor.from_pretrained("<this repository>")
processor.image_processor.max_soft_tokens = 1120
```

Read it at temperature 0, with the prompt `legible.prompt.build_prompt` writes for its schema; the project served it merged into the bf16 base under vLLM (`legible serve merge`).
