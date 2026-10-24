---
base_model: google/gemma-4-E4B
base_model_revision: 411aa17b749aa952df1359d2dcea73917a544d9a
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
legible_run_id: 4b-fara-unseen-amendment-s0-v1120-s0-6866f31af9
legible_publishable: true
# VRDU Registration Forms (FARA) is not on the Hugging Face Hub; its source is under Training data.
---

# Gemma 4 E4B fine-tuned to read FARA registration forms, Amendment template held out

A QLoRA adapter on `google/gemma-4-E4B` that reads the page images of one document and writes its fields as JSON. Trained and measured in Forms That Read Themselves (package `legible`), which compares frontier vision models, fine-tuned small vision models and OCR pipelines on scanned forms with known answers. Run `4b-fara-unseen-amendment-s0-v1120-s0-6866f31af9`. This card is written by `legible cards` from the run's records and graded reads; no number in it is typed by hand.

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
| Base | `google/gemma-4-E4B` at revision `411aa17b749aa952df1359d2dcea73917a544d9a` |
| Chat template | `google/gemma-4-E4B-it` at revision `ee0ef6023621cff504d758262d4e04895a5af4a2` |
| Quantisation | NF4 4-bit with double quantisation, bf16 compute; the vision and audio towers, the vision projector and the output layer kept at full precision |
| LoRA | rank 16, alpha 32, dropout 0.05, on the language model's attention and MLP projections and the vision projector, never the towers |
| Optimisation | learning rate 0.0002, cosine schedule, warmup 0.03, 1 epoch, 1 document a step, 8 steps accumulated |
| Visual tokens a page | 1,120 |
| Sequence limit | 12,288 tokens |
| Seed | 0 |
| Training set | `fara-unseen-amendment-s0` (200 documents) |
| Training documents and pages | 200 documents, 402 pages |
| Optimiser steps | 25, from 200 documents at 8 a step |
| Loss and timing | in `run.json`, the training record uploaded with the adapter; it was not on the machine that wrote this card |
| Templates trained on | Dissemination_Report 73, Short-Form 127 |

## Training data and its licences

**VRDU Registration Forms (FARA)**, https://github.com/google-research-datasets/vrdu (registration-form). Terms: CC BY 4.0 for the benchmark's annotations; the pages are US public records, Foreign Agents Registration Act filings published by the Department of Justice.

> "We are excited to announce the public release of the VRDU dataset and evaluation code under a Creative Commons license."

Quoted from Google's release post, "Advances in document understanding" (2023-08-09), https://research.google/blog/advances-in-document-understanding/, where "Creative Commons license" links to https://creativecommons.org/licenses/by/4.0/. That hyperlink is the only statement of the variant; the repository has no licence file (read 2026-10-16). Attribution: Google Research's VRDU benchmark (Wang et al., "VRDU: A Benchmark for Visually-rich Document Understanding", KDD 2023), annotations used under CC BY 4.0.

The adapter is released under apache-2.0, the base model's licence. Publication: VRDU's annotations are CC BY 4.0 and the pages are public records the Department of Justice publishes for inspection; neither forbids a derived model. The forms name individuals, and an adapter trained on them can write a name it saw in training: it is uploaded private, and making it public is a decision recorded in docs/models.md, not a default.

## Results

On the 300 test documents of VRDU's split file `FARA-lv3-unk_Amendment-train_200-test_300-valid_100-SD_0`, templates never seen in training, read once, level 0, temperature 0, unconstrained. Field accuracy is VRDU's matchers, one grader for every reader; intervals are 95% bootstrap over documents. The adapter is costed at an RTX 3090 at US$0.50 an hour on RunPod (2026-10-18) over the measured wall time of its read; the frontier models at the gateway ledger's cost at the 2026-10-16 price list, batch rate.

| Reader | Fields correct (95% CI) | Every field right | Invented fields | Answers that did not parse | Cost per 1,000 pages | Documents |
|---|---|---|---|---|---|---:|
| B, Gemma 4 E4B fine-tuned (this adapter) | 61.6% (59.5 to 63.7) | 0.3% (0.0 to 1.0) | 15.0% (13.4 to 16.6) | 0.3% (0.0 to 1.0) | US$0.07 (0.07 to 0.08) | 300 |
| C, Gemma 4 E4B untuned on the image | 72.2% (69.4 to 75.0) | 34.3% (29.0 to 39.7) | 11.7% (9.9 to 13.6) | 0.0% (0.0 to 0.0) | US$0.09 (0.09 to 0.09) | 300 |
| A, Claude Sonnet 5.5 on the image | 75.5% (73.6 to 77.4) | 21.0% (16.3 to 25.7) | 13.1% (11.8 to 14.4) | 0.0% (0.0 to 0.0) | US$2.91 (2.88 to 2.93) | 300 |
| A, Claude Haiku 5.5 on the image | 73.7% (71.7 to 75.8) | 19.0% (14.7 to 23.7) | 14.0% (12.7 to 15.3) | 0.0% (0.0 to 0.0) | US$0.17 (0.17 to 0.17) | 300 |
| A, GPT-6.1 Sol on the image | 72.3% (70.3 to 74.2) | 13.7% (10.0 to 17.7) | 15.1% (13.9 to 16.4) | 0.0% (0.0 to 0.0) | US$2.76 (2.73 to 2.80) | 300 |
| A, Gemini 3.8 Flash on the image | 71.9% (69.9 to 73.8) | 16.7% (12.7 to 21.0) | 13.8% (12.6 to 15.1) | 0.3% (0.0 to 1.0) | US$1.70 (1.55 to 1.85) | 300 |

The best frontier model on these documents is Claude Sonnet 5.5, at 75.5% (73.6 to 77.4) of fields for US$2.91 (2.88 to 2.93) a thousand pages. This adapter's field accuracy differs from it by -13.9 points, at US$0.07 (0.07 to 0.08) a thousand pages, about 1/39 of the cost. Against its untuned base it reads -10.6 points.

In the README's FARA table the three held-out-template models of this size are pooled over the 900 unseen-template test documents:

| Reader | Fields correct (95% CI) | Every field right | Invented fields | Answers that did not parse | Cost per 1,000 pages | Documents |
|---|---|---|---|---|---|---:|
| B, Gemma 4 E4B fine-tuned on the image | 66.8% (65.3 to 68.3) | 14.3% (12.1 to 16.6) | 13.2% (12.3 to 14.2) | 0.2% (0.0 to 0.6) | US$0.07 (0.07 to 0.08) | 900 |
| A, Claude Sonnet 5.5 on the image | 78.8% (77.5 to 80.0) | 31.4% (28.4 to 34.4) | 8.9% (8.1 to 9.7) | 0.0% (0.0 to 0.0) | US$2.96 (2.95 to 2.97) | 900 |

Training variance: the same recipe at seeds 1 and 2, each on its own split's test set: seed 1, 57.5% (55.7 to 59.3); seed 2, 53.0% (50.8 to 55.2). The three seeds' point estimates span 8.6 points (their test sets differ where the split files do).

### The 03 release gate

Not gated. Project 03's gate compared the E2B, the better of the two sizes on dev, for this corpus (docs/gate.md); its decision is on that card.

## Failure modes

- **A form design it has not seen.** The README's two tables, templates seen in training and not, for this size and the best frontier model: Gemma 4 E4B 72.2% (69.7 to 74.7) on templates seen in training and 66.8% (65.3 to 68.3) on templates not seen (-5.4 points); Claude Sonnet 5.5 74.2% (71.9 to 76.4) on templates seen in training and 78.8% (77.5 to 80.0) on templates not seen (+4.6 points). A fine-tune learns which box a value sits in on the templates it saw, and on a new one puts values in the wrong field or leaves them out.
- **A bad scan.** On the 15 of its test documents in the VRDU curve subset, real scans, degraded in the project's five reproducible steps (docs/degradation.md): level 0 53.5% (43.3 to 63.5), level 2 52.3% (43.0 to 61.6), level 4 54.0% (43.8 to 64.3).
- **Confidently wrong.** Its own token probability is not a reason to skip review. None of its dev fields is written at a token probability of 0.999 or more. At 99% accuracy it sends 94.6% (93.5 to 95.6) of its test fields to a person. The probability measures how sure the model is of its habit, not whether the page agrees (docs/review.md).
- **Training variance.** The same recipe at three seeds reads from 53.0% to 61.6% of fields on test (above); a retrained copy is not guaranteed to read like this one.
- **Not non-inferior to the frontier.** Project 03's gate blocks for the E2B, the size it compared, on this corpus at a 3-point margin per field (above). Do not take it as a drop-in for a frontier model's read.
- **Malformed answers.** 0.3% (0.0 to 1.0) of its test answers did not parse as JSON. It is read freely: holding the fine-tunes to the schema's grammar was tried on dev and rejected, because it pushed them off their trained spacing and the DeepForm E2B then answered null for every field (docs/rejected.md). A caller must count a parse failure as a document to type by hand.
- **Invented fields.** 15.0% (13.4 to 16.6) of scored fields carry a value where the form's box is blank.
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

base = AutoModelForImageTextToText.from_pretrained("google/gemma-4-E4B", revision="411aa17b749aa952df1359d2dcea73917a544d9a")
model = PeftModel.from_pretrained(base, "<this repository>")
processor = AutoProcessor.from_pretrained("<this repository>")
processor.image_processor.max_soft_tokens = 1120
```

Read it at temperature 0, with the prompt `legible.prompt.build_prompt` writes for its schema; the project served it merged into the bf16 base under vLLM (`legible serve merge`).
