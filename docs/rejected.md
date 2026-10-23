# Tried and rejected

Two approaches the plan relied on were measured and did not survive. The first has the
stronger evidence; the second was caught on a handful of pages and is reported with that
caveat.

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
