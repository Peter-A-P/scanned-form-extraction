# Arm B: the fine-tunes

`legible train sets` writes one training set per headline split file (`legible/train/dataset.py`):
FARA's unseen level one per held-out template and seed, DeepForm's one per seed, the mixed
level one per corpus and seed, CORD's training part, and NIST's twenty faces, each with the
prompt every other arm is sent and the schema's JSON of the truth as the answer. Only
training documents are written; a held-out document refuses the set. NIST's faces are trained
as one model on all twenty sets, each face asked with its own prompt.

`legible train run` (`legible/train/vision.py`) is 06's QLoRA recipe on page images:

- Gemma 4 E2B and E4B at 06's revisions, `AutoModelForImageTextToText`, NF4 4-bit with double
  quantisation and bf16 compute; the vision and audio towers, the vision projector and the
  output layer are kept out of the quantisation.
- LoRA on the language model's attention and MLP projections and on the vision projector,
  never on the towers (`TARGET_MODULES`, checked at the start of every run). 06's chosen
  recipes: 2B at rank 64 and 1e-4, 4B at rank 16 and 2e-4, alpha twice the rank, one epoch,
  one document a step, 8 steps accumulated, cosine schedule.
- One user turn of page images then the prompt, one assistant turn of the JSON; the loss on
  the answer's tokens only, computed from the answer's logits alone.
- 1,120 visual tokens a page, the top of Gemma 4's range and what the card recommends for
  documents; 560 is the ablation.
- Checkpoints to the volume from the first save (`legible/train/checkpoint.py`, 06's, copied at
  3adf4fad); a run resumes from the newest complete one. `ops/train-queue.sh` runs a seed's
  list on one pod and skips what is done, so several pods can share a list.

## What the smoke runs found (2026-10-18, RTX A5000)

| Failure | Cause | Fix |
|---|---|---|
| `Could not import module 'Gemma4Processor'` | Gemma 4's image processor is written in torchvision, which 06 never needed | `torchvision==0.29.1` in the train extra |
| `assert module.weight.shape[1] == 1` in bitsandbytes at the first step | transformers 5.17 matched the skip list's short names (`vision_tower`) against nothing, so the vision tower and the tied output layer were quantised | The skip list by full module path (`model.vision_tower`, `lm_head`) |
| Out of memory in the loss | The logits of a whole page example over the 262k-token vocabulary, 2.6 GB in fp32 | Logits for the answer's positions only (`logits_to_keep`) |
| Out of memory again on DeepForm, at 1,120 and at 560 visual tokens | A DeepForm answer runs to about 5,000 tokens, and its logits alone are 5 GB in fp32 | The loss over the answer in chunks of 512 positions, each recomputed in the backward pass (`AnswerLossTrainer`); DeepForm then trained at 1,120, 80 seconds a step on the A5000 |

After the fixes: two steps of 8 documents, 28 seconds a step for the 2B at 1,120 visual
tokens, train loss 0.78, both checkpoints written to the volume and listed back.

## Reading the fine-tunes: what was tried on dev

The self-hosted models are read through vLLM and the gateway (`ops/serve-eval.sh`). Four
settings were changed on 2026-10-18 before any of their numbers were kept, each on dev or on a
read that was archived, not reported:

| Setting | What happened | Kept |
|---|---|---|
| vLLM's default temperature, 1 | The merged checkpoint carries no sampling defaults, so every read was sampled | No: temperature 0, 06's rule |
| The vendors' 1,568-pixel page | The fine-tunes were trained on the page as rendered and their processor scales it to the visual budget itself | No: the page as rendered |
| A 120-second read timeout | A DeepForm answer of up to 8,192 tokens outran it and stopped the pass | No: 900 seconds, and a failed call left unread for a second pass |
| **Constrained JSON decoding** (vLLM structured outputs on the schema) | It cut unparsed answers from 15% to 1% on the first FARA model, but it writes JSON in the grammar's spacing (`"advertiser": null`) rather than the compact form the models were trained on (`"advertiser":null`). Pushed off its trained format, the DeepForm 2B answered null for every field: on 6 dev orders it filled the advertiser on none, against all 6 read freely. Without optional whitespace, it looped on spaces to the token limit instead | **No: rejected.** The models are read freely and their malformed answers are counted as malformed |

NIST's fine-tunes read 800 of its 3,850 training faces, the first 800 in the interleaved order,
about 40 a face (`VOLUME_FOR` in `legible/train/recipe.py`). The whole part ran at 145 seconds a
step for the 4B on an RTX A6000, its prompts listing every field of a face: nineteen hours for
one run. The 4B's full-volume run was stopped at step 34 of 463.

## Two seeds that learned to answer in the schema's shape (found 2026-10-23)

Seed 1 of the 4B on FARA's Short-Form template and seed 1 of the 4B on DeepForm's unseen
templates wrap their answers in the prompt's JSON schema: `{"type":"object","properties":
{"registrant_name":"Charles N. Conconi",...}}` instead of the record itself. 294 of the 300
FARA test answers and 132 of the 157 DeepForm ones have that shape; the values inside are
often right, but the record is not where the grader reads it, so the two runs score 0.9% and
8.0% of fields correct, far below the same configuration at seeds 0 and 2. The grader is not
loosened to unwrap them: the answers are graded as written, as every arm's are, and the runs
stand as part of the training variance the seeds measure. They are the evidence that one seed
of a fine-tune can learn the wrong output format from the same data and recipe, which a
buyer serving one model without a held-out check would not see.
