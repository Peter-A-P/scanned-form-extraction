# The review rate

How many fields a person still checks for the rest to be right 99% of the time. Each arm gives
every field a confidence; a threshold is chosen on dev, the lowest at which the accepted dev
fields are 99% right, and applied once to test (`legible/review.py`). A field with no
confidence goes to a person, and so does every field of an arm whose threshold could not reach
99% on dev. The tables are in the README, written by `legible report`.

## The two confidences

- **Frontier (arm A): agreement.** A field of Sonnet 5.5's read of the image is scored 1 when
  Sonnet 5.5's read of the OCR text gives the same value under the field's matcher, 0 when it
  does not (`legible/agreement.py`). It costs nothing extra, since both arms are read anyway.
- **Fine-tuned (arm B): token probability.** The seed-0 headline models read their level-0 dev
  and test documents a second time with each answer token's log-probability, at temperature 0
  (PLAN.md 2.6, decided by Peter on 2026-10-20 over dropping B's review rate). A field's
  confidence is the lowest probability among the tokens of its value, `null` included
  (`legible/tokenconf.py`). The accuracy tables keep the first test read.

## What happened

Neither reaches 99% on any corpus at a useful rate: every field goes to a person, except a
sliver of DeepForm where a threshold reached 99% on a handful of dev fields and accepted at most
0.2% of test fields.

The fine-tunes are confidently wrong, and mostly in one way. On dev, among fields read at a
token probability of 0.999 or more:

| Model | Corpus | Fields at 0.999 or more | Right | Most common error there |
|---|---|---:|---:|---|
| 2B | FARA, unseen templates | 60 | 0.0% | missing: `null` where the form carries a value (all 60) |
| 2B | DeepForm, unseen templates | 2,003 | 83.0% | the value of another field (153) |
| 2B | CORD | 242 | 80.2% | the value of another field (32) |
| 2B | NIST | 5,569 | 85.0% | missing (638) |
| 4B | FARA, unseen templates | 0 | | |
| 4B | DeepForm, unseen templates | 2,276 | 81.7% | a wrong value (193) |
| 4B | CORD | 167 | 77.8% | the value of another field (24) |
| 4B | NIST | 3,317 | 81.4% | missing (365) |

The most confident tenth of the 2B's FARA dev fields is 23.3% right. A fine-tune learns to
write `null` for a field it was usually trained to leave empty, and writes it with near
certainty on a form where the field is filled; it learns which box a value sits in on the
templates it saw, and on a template it did not see puts the value in the wrong field without
doubt. The token probability measures how sure the model is of its own habit, not whether the
page agrees.

This is reported as measured. The confidence was defined before the reads (PLAN.md 2.6) and
was not reworked after them: scoring `null` differently, or trying other aggregations, would be
choosing the confidence with the test result in view.
