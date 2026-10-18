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
  documents, except DeepForm at 560: its orders run to eleven pages, and at 1,120 the 2B ran
  out of memory on a 24 GB card at the third step (2026-10-18), with the documents over
  12,288 tokens already left out. 560 is the plan's own ablation value; on the other corpora
  it is the ablation.
- Checkpoints to the volume from the first save (`legible/train/checkpoint.py`, 06's, copied at
  3adf4fad); a run resumes from the newest complete one. `ops/train-queue.sh` runs a seed's
  list on one pod and skips what is done, so several pods can share a list.

## What the smoke runs found (2026-10-18, RTX A5000)

| Failure | Cause | Fix |
|---|---|---|
| `Could not import module 'Gemma4Processor'` | Gemma 4's image processor is written in torchvision, which 06 never needed | `torchvision==0.29.1` in the train extra |
| `assert module.weight.shape[1] == 1` in bitsandbytes at the first step | transformers 5.17 matched the skip list's short names (`vision_tower`) against nothing, so the vision tower and the tied output layer were quantised | The skip list by full module path (`model.vision_tower`, `lm_head`) |
| Out of memory in the loss | The logits of a whole page example over the 262k-token vocabulary, 2.6 GB in fp32 | Logits for the answer's positions only (`logits_to_keep`) |

After the fixes: two steps of 8 documents, 28 seconds a step for the 2B at 1,120 visual
tokens, train loss 0.78, both checkpoints written to the volume and listed back.
