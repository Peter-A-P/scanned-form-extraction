# Label audit

Written by `legible data audit-report` from `docs/audit/decisions.json`; do not edit.

| Corpus | Labels | Audited | Disagreement (95% CI) | Unreadable |
|---|---|---:|---|---:|
| fara | all | 59 | 5.1% (0.0% to 11.9%, n = 59) | 1 |
| deepform | all | 79 | 6.3% (1.3% to 12.7%, n = 79) | 1 |
| deepform | fields | 40 | 5.0% (0.0% to 12.5%, n = 40) | 0 |
| deepform | line items | 39 | 7.7% (0.0% to 17.9%, n = 39) | 1 |
| cord | all | 60 | 0.0% (0.0% to 0.0%, n = 60) | 0 |
| cord | fields | 30 | 0.0% (0.0% to 0.0%, n = 30) | 0 |
| cord | line items | 30 | 0.0% (0.0% to 0.0%, n = 30) | 0 |

2 labels were looked at again on 2026-10-16 (`docs/audit/recheck.json`), after their crops came out blank: the pages had been rendered in the PDF's orientation, not the benchmark's (docs/ocr.md). The recheck replaces the first decision.

8 labels marked wrong with the value the page shows are corrected by the
loaders from `legible/data/patches.json`; each patched document names its patched fields.

| Corpus | Document | Field | Corrected to |
|---|---|---|---|
| deepform | 3446ada9-ed5c-86a8-f237-190be5851005.pdf | line_item[3].program_end_date | 03/04/20 |
| deepform | 416277-collect-files-72145-political-file-2012-federal.pdf | line_item[28].program_end_date | 08/26/12 |
| deepform | 493496-315597-up-obama-10-30-12-13516185156783-_-pdf.pdf | flight_to | 11/06/12 |
| deepform | 8dfa0ca9-2457-2309-3c1c-8301ca6a6d14.pdf | line_item[21].program_end_date | 06/09/20 |
| deepform | cfb3bae5-102b-8fcb-06a5-9a0bc89fa14f.pdf | flight_from | 02/26/20 |
| fara | (registration form) | file_date | 17 day of NOV |
| fara | (registration form) | file_date | 14th DECEMBER 1984 |
| fara | (registration form) | file_date | 02/20/2014 |
