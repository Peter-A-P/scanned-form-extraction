# Tried and rejected

Three approaches the plan relied on or hoped for were measured and did not survive. The first
and the third have the stronger evidence; the second was caught on a handful of pages and is
reported with that caveat.

## The fine-tune's own token probability as the review signal

**The idea.** A model that writes each field token by token gives every token a probability.
If the probability of a field's tokens says how likely the field is right, a review queue can
accept the sure fields and send the rest to a person, at no extra cost: it is the confidence a
self-hosted model brings for free, and the plan built the fine-tuned arm's review rate on it
(PLAN.md 2.6).

**The test.** The seed-0 fine-tunes of both sizes read their dev and test documents again with
every answer token's log-probability, at temperature 0. A field's confidence is the lowest
probability among the tokens of its value (`legible/tokenconf.py`). The threshold is the lowest
at which the accepted dev fields are 99% right, applied once to test (`legible/review.py`).

**The result.** No threshold reaches 99% on FARA, CORD or NIST, for either size, so every field
goes to a person. On DeepForm one does, on a handful of dev fields, and on test it accepts none
of the 2B's fields and 0.2% of the 4B's. The fine-tunes are confidently wrong. Among dev fields
written at a probability of 0.999 or more:

| Model | Corpus | Fields at 0.999 or more | Right |
|---|---|---:|---:|
| 2B | FARA, unseen templates | 60 | 0.0% |
| 2B | NIST | 5,569 | 85.0% |
| 4B | DeepForm, unseen templates | 2,276 | 81.7% |
| 4B | NIST | 3,317 | 81.4% |

All 60 of the 2B's surest FARA fields are a `null` where the form carries a value. A fine-tune
learns which fields are usually empty and which box a value sits in on the templates it saw,
and writes both with near certainty on a template it did not see. The probability measures how
sure the model is of its habit, not whether the page agrees. The full table is in
[review.md](review.md).

**What it changes.** A buyer cannot take the self-hosted model's confidence as a reason to
skip review. The confidence was defined before the reads and not reworked after them: scoring
`null` differently, or another aggregation, would be choosing the measure with the test result
in view.

## Holding the fine-tunes to the schema's grammar

**The idea.** About 15% of the first FARA fine-tune's answers did not parse as JSON. vLLM can
constrain decoding to the schema, which makes every answer parse.

**The test and the result.** Constrained, the unparsed share fell from 15% to 1% on that model.
But the grammar writes JSON in its own spacing (`"advertiser": null`), not the compact form the
models were trained to write (`"advertiser":null`), and pushed off its trained format the
DeepForm 2B answered `null` for every field: on 6 dev orders it filled the advertiser on none,
against all 6 read freely. With optional whitespace removed from the grammar, it looped on
spaces to the token limit instead. Six pages is thin evidence for a number, and enough for a
verdict: a constraint that turns a model's answers into nulls costs more than the parse
failures it removes. The fine-tunes are read freely, and an answer that does not parse is
counted as malformed ([training.md](training.md)).

## Half the visual tokens a page

**The idea.** Gemma 4 takes a page at a token budget the caller chooses. At 560 tokens instead
of the headline's 1,120 a page costs less to train on and to serve, and the plan hoped the
smaller budget would hold accuracy and become the cheaper recipe (PLAN.md 2.3).

**The test.** One E2B fine-tune per headline training set at 560 tokens, at training and at
serving, seed 0, otherwise the headline recipe (`legible/train/ablate.py`), read through the
gateway on the same RTX 3090 and graded like every other reader. The difference is paired over
the documents both models read, with its 95% interval (the README's ablation tables).

**The result.** It lost accuracy on every test set it was read on, each interval wholly below
zero: 3.6 points on FARA's unseen templates (-4.9 to -2.3), 10.0 on DeepForm's (-17.0 to
-3.2), 4.4 on CORD (-8.2 to -0.5), 9.4 on NIST (-12.0 to -6.9), and 8.6 to 10.9 on NIST's
scans at levels 2 to 4. The saving is small: the cost a thousand pages fell from
US$0.06 to US$0.03 on FARA, US$0.11 to US$0.08 on CORD, US$0.19 to US$0.18 on DeepForm and
US$0.40 to US$0.35 on NIST (RTX 3090 at US$0.50 an hour, 2026-10-18).

**What it changes.** The headline recipe keeps 1,120 tokens. A few cents a thousand pages is
not worth three to ten points of fields right.
