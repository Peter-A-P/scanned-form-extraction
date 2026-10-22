# The release gate

Project 03's gate decides whether a fine-tune is non-inferior to a frontier model: one suite
per field, one right-or-wrong outcome per document, a paired bootstrap test on the same test
documents, a three-point margin per field, Holm's adjustment across the fields it decides, and
a power screen that leaves a field it cannot resolve undecided (`legible/gate.py`, 03's
`docs/gate-adapter.md`). It grades nothing: this project's grader writes the outcomes
(`legible gate export`), and each decision's record names both side files by their hash. The
files, the decisions and the ledger are in [gate-runs/](../gate-runs); the README's table is
read from the decisions by `legible report`. Run on 2026-10-22 with gate 0.1.0, at 03's commit
`2849727`.

## Who is compared

Per corpus, the fine-tune (arm B, seed 0) of the size with the better field accuracy on dev,
against the frontier vision model (arm A) with the best field accuracy on dev, and against the
cost anchor, Claude Haiku 5.5. Choosing both on dev keeps the test set to the one comparison.
On dev the best frontier model was Gemini 3.8 Flash for FARA and CORD and GPT-6.1 Sol for
DeepForm and NIST; the better fine-tune was the 2B for FARA and the 4B elsewhere. NIST's twenty
form faces are gated as one spec, each face's fields its own suites.

## What it decided

- **FARA and DeepForm: blocked**, on both splits and against both frontier models. The
  fine-tunes cannot rule out a three-point loss on most fields, and on several the loss is
  certain and large: on FARA's unseen templates the registrant's name is 26.9 points behind
  Gemini (-30.0 to -23.8); on DeepForm the line items' channel column is about 30 points behind
  either. Against the cost anchor on FARA's mixed templates the 2B clears four fields of six.
- **CORD and NIST: no decision.** Every field is under-powered at three points. CORD's test
  set is 100 receipts, and a receipt field appears on a fraction of them; NIST's 500 test
  pages spread over twenty faces, so a field has at most about 80. The gate's "pass" for these
  is the absence of a block, not evidence of non-inferiority, and the README says so instead
  of printing pass. The point differences in the decision files lean the same way as the
  accuracy tables: the fine-tunes are behind on most CORD and NIST fields.

So no corpus supports the claim that a model you own reads its forms as well as the frontier
does, field by field, at three points. The accuracy tables put the fine-tunes closest on CORD
(77.6% against Gemini's 86.1%) at under a twentieth of the cost per page.

## Running it again

```bash
legible gate export          # writes gate-runs/<spec>-<size>-vs-<best|anchor>/
# in a checkout of ai-release-gate:
uv run gate compare --spec gate-runs/<name>/spec.yaml --baseline gate-runs/<name>/baseline.json \
  --candidate gate-runs/<name>/candidate.json --out gate-runs/<name>/decision.txt \
  --ledger gate-runs/ledger.jsonl
```

It exits 1 on a block.
