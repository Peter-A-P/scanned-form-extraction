# Models

Arm A's and D's frontier models, chosen 2026-10-16 from 04's price file of that date
(`boundary/prices/2026-10-16.yaml`, gateway v1.4.0; run through v1.4.3, whose prices are the same) and confirmed by Peter the same day. The
identifiers are the ones the gateway routes to (`boundary.yaml`); a run records the identifier
each vendor returned, so a silent model change shows in the ledger.

| Route | Provider | Model id | Role | Standard US$ per million in / out | Batch |
|---|---|---|---|---|---|
| `quality` | Anthropic | `claude-sonnet-5-5` | Arm A quality model; arm D's reader | 2.00 / 10.00 | half |
| `anchor` | Anthropic | `claude-haiku-5-5` | Arm A cost anchor, the cheapest Anthropic model | 0.10 / 0.50 (0.50 / 2.50 over 100,000 prompt tokens) | half |
| `ceiling` | Anthropic | `claude-fable-5-1` | Arm A ceiling, on a 600-page subset of the test union | 10.00 / 50.00 | half |
| `openai` | OpenAI | `gpt-6.1-sol` | Arm A, OpenAI | 2.00 / 10.00 (4.00 / 15.00 over 272,000 prompt tokens) | half |
| `google` | Google | `gemini-3.8-flash` | Arm A, Google | 0.75 / 3.75 until 2026-12-31, then 1.50 / 7.50 | half |

Why these, as decided on 2026-10-16:

- **The OpenAI arm is GPT-6.1 Sol, not GPT-5.6 Terra.** It is the closest OpenAI model to the
  Claude 5.5 family by price and generation (released after GPT-6 Sol of 2026-09-22), costs
  the same as GPT-6 Sol for input and output with a cheaper cached read, and is cheaper than
  Terra's US$12 output. Rates read from https://developers.openai.com/api/docs/pricing on
  2026-10-16 and added to 04's price list for this project (04 v1.4.0).
- **The ceiling is Claude Fable 5.1, not Opus 5.5.** The plan says the ceiling is the most
  expensive model, and on 2026-10-16 that is Fable. Its 600-page subset costs about US$13 at the
  batch rate, against the US$6 the plan budgeted for an Opus-class ceiling.
- **Gemini 3.8 Flash is Google's newest Flash model** (https://ai.google.dev/gemini-api/docs/pricing,
  read 2026-10-16). Its introductory price doubles on 2027-01-01, so the Google arm runs before
  then, and the cost table prints the rate the run was billed at, from the ledger.

Arm B and C's bases (Gemma 4 E2B and E4B, Apache 2.0) are recorded here with their revisions
when the fine-tunes start.

## Arm A on dev

2026-10-17, level 0, prompt version 1, batch rate, submitted from the laptop through the
gateway (PLAN.md, risks). Field accuracy with its 95% bootstrap interval over documents;
invented is the share of scored fields given a value the page does not carry. Cost is the
gateway ledger's for all 580 dev documents. The validation part is the same in every seed of a
split, so each row stands for three split files. Dev numbers choose prompts and settings; they
are not results.

| Split | Sonnet 5.5 | Haiku 5.5 | GPT-6.1 Sol | Gemini 3.8 Flash |
|---|---|---|---|---|
| FARA, mixed | 77.8% (73.8 to 81.6) | 74.3% (69.8 to 78.6) | 70.0% (65.7 to 74.2) | 80.0% (76.3 to 83.7) |
| FARA, Amendment held out | 71.8% (68.1 to 75.4) | 69.3% (65.6 to 73.0) | 68.2% (64.6 to 71.7) | 67.2% (63.4 to 70.8) |
| FARA, Dissemination held out | 90.0% (87.5 to 92.4) | 93.0% (90.5 to 95.3) | 87.0% (82.9 to 90.5) | 92.9% (90.4 to 95.2) |
| FARA, Short-Form held out | 67.5% (63.2 to 71.8) | 60.6% (56.2 to 64.8) | 52.1% (48.3 to 55.9) | 75.0% (70.6 to 79.4) |
| DeepForm | 72.6% (66.5 to 78.4) | 69.7% (63.5 to 75.7) | 78.2% (73.1 to 82.9) | 71.0% (64.3 to 77.4) |
| CORD | 90.7% (87.6 to 93.7) | 84.1% (77.6 to 88.9) | 91.8% (88.9 to 94.5) | 92.2% (88.5 to 95.2) |
| Invented, FARA held out (range) | 1.2 to 14.2% | 0.2 to 19.5% | 1.2 to 23.5% | 1.2 to 15.8% |
| Cost, US$ | 4.07 | 0.26 | 3.71 | 2.29 |

Two settings came out of dev:

- **Gemini's output budget.** Gemini 3.8 Flash thinks before it answers and counts its
  thoughts against `maxOutputTokens`: at the 1,024 tokens every other model gets for FARA, 128
  of 380 answers were cut off mid-record (35 to 43% unparsed on the FARA splits). It now gets
  4,096 tokens more (`REASONING_HEADROOM` in `legible/arms/read_run.py`), still at Google's
  default reasoning; the cut-off run is archived, not deleted, and the table is the rerun.
- **OpenAI's batch window.** Six of GPT-6.1 Sol's 380 FARA requests never came back within the
  24-hour window (`batch_missing` in the ledger) and are graded as unread.
