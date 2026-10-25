# Arm F: Azure AI Document Intelligence

Added 2026-10-24 (PLAN.md 2.2 and 7): the managed document service a buyer with a paper
backlog is quoted first, measured on the same test documents, with the same grader, as every
other arm. The numbers are in the README's tables; this page says what was run and how.

## The service and its price

Azure AI Document Intelligence, API version 2024-11-30 (v4.0 GA), resource `legible-docintel`,
East US, S0, created 2026-10-24. Prices from Azure's retail prices API, read 2026-10-24, pay
as you go: custom extraction US$30 per 1,000 pages, prebuilt models and layout US$10, read
US$1.50; custom neural training free for ten hours a month, then US$3 an hour, with every
build billed at least half an hour. Every analysis goes through the 04 gateway (boundary 1.6,
`azure_docintel`), which writes each document's row before it is sent and costs it from the
pages the service reports, so the cost per 1,000 pages in the tables is the ledger's, as for
every other arm. There is no batch discount on this endpoint.

## Which model reads what

| Corpus | Model | Trained on |
|---|---|---|
| CORD | `prebuilt-receipt`, untrained | nothing; its fields are mapped onto CORD's by name (`RECEIPT_FIELDS` in `legible/arms/docintel.py`) |
| FARA | a custom neural model per unseen-template split (amendment, dissemination report, short form), each reading only its split's test documents | the first 100 training documents by id of the same split file arm B's fine-tune learned: templates other than the one it is tested on |
| DeepForm | a custom neural model on the unseen-template split | the first 100 of that split's training documents |
| NIST | a custom neural model per face, reading its face's test pages and its curve pages at levels 1 to 4 | the first 30 training pages of that face |

So a FARA or DeepForm model has never seen a page of the template it is tested on, exactly as
the fine-tune has not. It has seen fewer training documents than the fine-tune (100 against
200), because each training document is first read by the layout model at US$10 a 1,000 pages
and training time grows with the set.

## Teaching a custom model

The service learns fields from labels drawn on its own reading of the page, so each training
document was read once by `prebuilt-layout`, through the gateway, and each value of its truth
labelled on the words of that reading whose text it is: the value's tokens in order and
consecutive on one page, compared case-folded with surrounding punctuation stripped, and no
word labelled twice (`find_words`). A value the reading does not spell out is left unlabelled
on that document, never guessed at. Tables (DeepForm's line items) are labelled row by row,
`line_item/<row>/<column>`. The share of truth values found, per training set:

| Training set | Documents | Values labelled |
|---|---:|---:|
| FARA, amendment held out | 100 | 498 of 533 (93.4%) |
| FARA, dissemination report held out | 100 | 348 of 416 (83.7%) |
| FARA, short form held out | 100 | 459 of 519 (88.4%) |
| DeepForm, unseen templates | 100 | 6,878 of 7,722 (89.1%) |
| NIST, twenty faces | 30 each | 77.8% (Schedule D, page 1) to 95.0% (Form 4562, page 2) |

The values not found are, on a sample of the dissemination-report set and Schedule D page 1,
answers whose spacing differs from the layout model's words (VRDU's "Feb8,2013" against a
page that reads "Feb 8, 2013"; "16th day of June ,1995" split across lines), handwritten
signers' names the layout model read differently, and NIST amounts in dollars and cents boxes
("33834  01") whose two boxes did not come out as the two words the match looks for. They cost the service some training signal; that is
reported rather than hand-fixed.

## What it is sent, and what is read back

A document's pages as one multi-page TIFF, deflate-compressed, at the resolution they were
rendered or degraded at: the pixels every other arm reads, but whole, where the vision models
are sent each page scaled to their own limit. That is what a buyer would send the service.

The answer is read back into the corpus schema (`to_record`): each field's `content`, the text
as printed, which is what the corpus answers transcribe, else its typed value; a table's rows
into the schema's list. A field the model did not return is null. The service's own fields,
with its confidence for each, are kept beside every run in `fields.jsonl`.

## What is not measured

- **No dev reads, so no review rate.** Arm F has no prompt and no threshold to tune, so dev was
  not read, to keep the arm inside its budget. The service does return a confidence per field;
  a 99% review rate for it needs a dev read to set the threshold, about US$40 more.
- **The mixed-template gap and the VRDU curve subset** were not in arm F's scope.
- **Training hours are not in the ledger**: building a model reads no page and is not a call
  through the gateway. They are recorded from the service's own `trainingHours` in
  `data/docintel/meta/<set>-build.json` and summed in the README's cost note: 18.72 hours over
  the 24 builds (2026-10-24), US$26.16 past the ten free hours. Each build was given a
  one-hour ceiling; the three FARA models stopped at about the half-hour minimum, and DeepForm
  and most NIST faces used close to the full hour.
