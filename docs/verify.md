# The verifier

Checks a form defines, run on every arm's answer after extraction, with no model
(`legible/verify.py`, PLAN.md 2.6). A sum that does not add up flags every field it reads,
because arithmetic says one of them is wrong and not which; a pattern or date that does not
parse flags its field. The README reports, per arm on test, the share of wrong fields flagged
(over every field, and over the fields some rule reads) and the share of right fields flagged,
the false alarms a reviewer pays for.

## Which rules run

A rule the corpus's own answers break would flag right fields, so each rule the forms define
was checked against the training split's truth before it ran, and kept only where the truth
obeys it on 99% of the documents it applies to. The measurement is
[verify-rules.md](verify-rules.md), written by `legible verify hold`; the rules are
`legible/verify_rules.py`.

- **NIST:** thirteen sums from the 1988 Form 1040 (lines 23, 30, 31, 35, 40, 46, 53, 61 and
  64), Schedule A (line 17) and Schedule B (lines 3, 5 and 8). All hold on every training
  document they apply to, once two things about the corpus are allowed for. The answers keep
  the form's dollars and cents boxes ("5140  00", "36237  -", "(4238  16)"), which
  `parse_box_amount` reads. And SD2's filled-in amounts are whole dollars rounded line by
  line, so a total sits up to half a dollar a line from its parts (51,319 against 7,664 plus
  43,654); each sum allows that and no more. Line 47 (tax less credits) is not run: the form
  enters zero rather than a negative, which breaks the sum on 3.7% of the training pages.
- **FARA:** a registration number is one to five digits (99.2%). Its filing date is not run:
  VRDU's answers transcribe what the page prints ("23rd day of March 1962"), and 20% of them
  are not dates a parser reads.
- **DeepForm:** none. Its flight dates often lose their year on the page and in the answer
  ("05/28/"), so a date rule held on 87%.
- **CORD:** none. A receipt follows no one arithmetic: some print prices with tax in and a
  pre-tax subtotal, some print discounts without a sign, some round the total to 100 rupiah.
  The best sum held on 93.5% of the training receipts, and a rule that flags a right total on
  one receipt in fifteen costs a reviewer more than it saves.

The plan named receipt arithmetic as the verifier's first example; on CORD's labels it is the
one that does not survive.
