# The verifier's rules against the training truth

Written by `legible verify hold`; do not edit. Each rule in `legible/verify_rules.py`, how many training documents it applies to, and on how many the corpus's own answers satisfy it. A rule is kept at 99% or more.

| Corpus | Rule | Applies to | Holds on | Run |
|---|---|---:|---:|---|
| fara | a registration number is digits | 1391 | 1380 (99.2%) | yes |
| nist_1040_1 | line 23, total income, adds lines 7 to 22 | 620 | 620 (100.0%) | yes |
| nist_1040_1 | line 30, total adjustments, adds lines 24 to 29 | 620 | 620 (100.0%) | yes |
| nist_1040_1 | line 31, adjusted gross income, is line 23 less line 30 | 620 | 620 (100.0%) | yes |
| nist_1040_2 | line 35 is line 32 less line 34 | 620 | 620 (100.0%) | yes |
| nist_1040_2 | line 40 adds lines 38 and 39 | 620 | 620 (100.0%) | yes |
| nist_1040_2 | line 46, total credits, adds lines 41 to 45 | 620 | 620 (100.0%) | yes |
| nist_1040_2 | line 53, other taxes, adds lines 48 to 52 | 620 | 620 (100.0%) | yes |
| nist_1040_2 | line 61, total payments, adds lines 54 to 60 | 620 | 620 (100.0%) | yes |
| nist_1040_2 | line 64 is line 62 less line 63 | 475 | 475 (100.0%) | yes |
| nist_sch_a | line 17 adds lines 14 to 16 | 135 | 135 (100.0%) | yes |
| nist_sch_b | line 3, total interest, adds lines 1 and 2 | 215 | 215 (100.0%) | yes |
| nist_sch_b | line 5, total dividends, adds line 4 | 49 | 49 (100.0%) | yes |
| nist_sch_b | line 8 adds lines 6 and 7 | 29 | 29 (100.0%) | yes |
| fara | the filing date is a date | 1374 | 1094 (79.6%) | no: below 99% |
| deepform | the flight starts on a date | 205 | 178 (86.8%) | no: below 99% |
| deepform | the flight ends on a date | 205 | 177 (86.3%) | no: below 99% |
| cord | the items, less their discounts, add up to the subtotal | 530 | 486 (91.7%) | no: below 99% |
| cord | the items, less their discounts, add up to the subtotal (to 100) | 530 | 490 (92.5%) | no: below 99% |
| cord | subtotal, tax, service and discount add up to the total | 522 | 451 (86.4%) | no: below 99% |
| cord | subtotal, tax, service and discount add up to the total (to 100) | 522 | 488 (93.5%) | no: below 99% |
| nist_1040_2 | line 47 is line 40 less line 46 | 620 | 597 (96.3%) | no: below 99% |
| nist_sch_b | line 9 adds lines 5 and 8 | 42 | 41 (97.6%) | no: below 99% |
