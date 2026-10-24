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
- deepform
legible_run_id: 4b-deepform-unseen-s0-v1120-s0-27c2e83f69
legible_publishable: true
# VRDU Ad-buy Forms (DeepForm) is not on the Hugging Face Hub; its source is under Training data.
---

# Gemma 4 E4B fine-tuned to read DeepForm ad-buy forms

A QLoRA adapter on `google/gemma-4-E4B` that reads the page images of one document and writes its fields as JSON. Trained and measured in Forms That Read Themselves (package `legible`), which compares frontier vision models, fine-tuned small vision models and OCR pipelines on scanned forms with known answers. Run `4b-deepform-unseen-s0-v1120-s0-27c2e83f69`. This card is written by `legible cards` from the run's records and graded reads; no number in it is typed by hand.

## What it reads and what it writes

Input: the document's pages as images, in page order, then the instruction every reader in the project is sent (`legible.prompt`, version 1), which describes each field and gives the JSON Schema. The adapter was trained on that instruction and nothing else.

One JSON object a document, every value a string or null, in the compact form it was trained on (`{"advertiser":null}`, no spaces). A political advertising order, invoice or contract from a US television station's FCC public file.

| Field | Kind | What it is |
|---|---|---|
| `advertiser` | string | The advertiser buying the airtime. |
| `agency` | string | The agency that placed the order, if any. |
| `contract_num` | code | The contract or order number. |
| `flight_from` | date | The first date of the flight (the run of the ads). |
| `flight_to` | date | The last date of the flight. |
| `gross_amount` | price | The gross total of the order. |
| `product` | string | The product, candidate or issue advertised. |
| `property` | string | The station's call letters. |
| `tv_address` | address | The station's postal address. |
| `line_item` | list | One scheduled row of the order. Each entry has: |
| `line_item[].channel` | string | The channel the row airs on. |
| `line_item[].program_desc` | string | The programme or daypart. |
| `line_item[].program_start_date` | date | The row's first air date. |
| `line_item[].program_end_date` | date | The row's last air date. |
| `line_item[].sub_amount` | price | The row's amount. |

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
| Training set | `deepform-unseen-s0` (200 documents) |
| Training documents and pages | 200 documents, 476 pages |
| Optimiser steps | 25, from 200 documents at 8 a step |
| Loss and timing | in `run.json`, the training record uploaded with the adapter; it was not on the machine that wrote this card |

## Training data and its licences

**VRDU Ad-buy Forms (DeepForm)**, https://github.com/google-research-datasets/vrdu (ad-buy-form). Terms: CC BY 4.0 for the benchmark's annotations; the pages are US public records, political advertising orders from television stations' FCC public files.

> "We are excited to announce the public release of the VRDU dataset and evaluation code under a Creative Commons license."

Quoted from Google's release post, "Advances in document understanding" (2023-08-09), https://research.google/blog/advances-in-document-understanding/, where "Creative Commons license" links to https://creativecommons.org/licenses/by/4.0/. That hyperlink is the only statement of the variant; the repository has no licence file (read 2026-10-16). Attribution: Google Research's VRDU benchmark (Wang et al., "VRDU: A Benchmark for Visually-rich Document Understanding", KDD 2023), annotations used under CC BY 4.0.

The adapter is released under apache-2.0, the base model's licence. Publication: VRDU's annotations are CC BY 4.0 and the pages are public records from the FCC's public files; neither forbids a derived model.

## Results

On the 159 test documents of VRDU's split file `DeepForm-unk_template-train_200-test_159-valid_100-SD_0`, templates never seen in training, read once, level 0, temperature 0, unconstrained. Field accuracy is VRDU's matchers, one grader for every reader; intervals are 95% bootstrap over documents. The adapter is costed at an RTX 3090 at US$0.50 an hour on RunPod (2026-10-18) over the measured wall time of its read; the frontier models at the gateway ledger's cost at the 2026-10-16 price list, batch rate.

| Reader | Fields correct (95% CI) | Every field right | Invented fields | Answers that did not parse | Cost per 1,000 pages | Documents |
|---|---|---|---|---|---|---:|
| B, Gemma 4 E4B fine-tuned (this adapter) | 59.6% (53.7 to 65.3) | 3.1% (0.6 to 6.3) | 7.6% (5.4 to 10.3) | 1.9% (0.0 to 4.4) | US$0.19 (0.17 to 0.20) | 159 |
| C, Gemma 4 E4B untuned on the image | 47.2% (42.6 to 51.9) | 0.0% (0.0 to 0.0) | 13.5% (10.4 to 16.9) | 0.6% (0.0 to 1.9) | US$0.22 (0.20 to 0.24) | 159 |
| A, Claude Sonnet 5.5 on the image | 69.8% (65.4 to 74.2) | 0.6% (0.0 to 1.9) | 10.0% (7.7 to 12.4) | 0.0% (0.0 to 0.0) | US$5.19 (4.94 to 5.45) | 159 |
| A, Claude Haiku 5.5 on the image | 66.4% (61.5 to 71.0) | 1.3% (0.0 to 3.1) | 11.1% (8.7 to 13.8) | 0.6% (0.0 to 1.9) | US$0.35 (0.33 to 0.37) | 159 |
| A, GPT-6.1 Sol on the image | 71.4% (66.7 to 76.0) | 2.5% (0.6 to 5.0) | 8.6% (6.5 to 10.9) | 3.8% (1.3 to 6.9) | US$4.53 (4.32 to 4.75) | 159 |
| A, Gemini 3.8 Flash on the image | 70.0% (64.4 to 75.1) | 2.5% (0.6 to 5.0) | 7.0% (5.3 to 9.0) | 3.1% (0.6 to 6.3) | US$2.73 (2.39 to 3.14) | 159 |

The best frontier model on these documents is GPT-6.1 Sol, at 71.4% (66.7 to 76.0) of fields for US$4.53 (4.32 to 4.75) a thousand pages. This adapter's field accuracy differs from it by -11.8 points, at US$0.19 (0.17 to 0.20) a thousand pages, about 1/24 of the cost. Against its untuned base it reads +12.4 points.

Training variance: the same recipe at seeds 1 and 2, each on its own split's test set: seed 1, 8.0% (4.6 to 12.1); seed 2, 57.1% (51.1 to 62.9). The three seeds' point estimates span 51.6 points (their test sets differ where the split files do).

### The 03 release gate

- Against Claude Haiku 5.5: **block** (fields pass, block, under-powered: 0, 9, 5); worst: `line_item-channel` -29.6% (-38.8 to -19.7); `contract_num` -23.3% (-30.2 to -15.7).
- Against GPT-6.1 Sol: **block** (fields pass, block, under-powered: 0, 10, 4); worst: `line_item-channel` -32.2% (-41.8 to -22.6); `line_item-sub_amount` -25.0% (-33.6 to -16.4).

## Failure modes

- **A form design it has not seen.** The README's two tables, templates seen in training and not, for this size and the best frontier model: Gemma 4 E4B 58.2% (53.0 to 63.2) on templates seen in training and 59.6% (53.7 to 65.3) on templates not seen (+1.4 points); GPT-6.1 Sol 72.3% (68.5 to 75.9) on templates seen in training and 71.4% (66.7 to 76.0) on templates not seen (-0.9 points).
- **A bad scan.** On the 30 of its test documents in the VRDU curve subset, real scans, degraded in the project's five reproducible steps (docs/degradation.md): level 0 67.7% (53.3 to 79.1), level 2 64.0% (49.2 to 75.5), level 4 63.0% (47.8 to 75.6).
- **Confidently wrong.** Its own token probability is not a reason to skip review. Of its dev fields written at a token probability of 0.999 or more (2,276), 81.7% (72.2 to 89.4) are right; the commonest error there is a wrong value (193). At 99% accuracy it sends 99.8% (99.5 to 99.9) of its test fields to a person. The probability measures how sure the model is of its habit, not whether the page agrees (docs/review.md).
- **Training variance.** The same recipe at three seeds reads from 8.0% to 59.6% of fields on test (above); a retrained copy is not guaranteed to read like this one.
- **Not non-inferior to the frontier.** Project 03's gate blocks on this corpus at a 3-point margin per field (above). Do not take it as a drop-in for a frontier model's read.
- **Malformed answers.** 1.9% (0.0 to 4.4) of its test answers did not parse as JSON. It is read freely: holding the fine-tunes to the schema's grammar was tried on dev and rejected, because it pushed them off their trained spacing and the DeepForm E2B then answered null for every field (docs/rejected.md). A caller must count a parse failure as a document to type by hand.
- **Invented fields.** 7.6% (5.4 to 10.3) of scored fields carry a value where the form's box is blank.
- **One instruction.** Trained on one prompt and one schema; another wording, another field list or another language is untested.

## Intended use

Reading DeepForm ad-buy forms of the kind it was trained on into JSON for a person to check, at a fraction of a frontier model's cost per page; and reproducing the measurements in this card. Plan on a person checking every field: no confidence measured in the project separates right fields from wrong ones well enough to skip review at 99% (the README's honest limitation).

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
