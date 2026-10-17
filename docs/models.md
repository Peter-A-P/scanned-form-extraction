# Models

Arm A's and D's frontier models, chosen 2026-10-16 from 04's price file of that date
(`boundary/prices/2026-10-16.yaml`, gateway v1.4.0; run through v1.4.2, whose prices are the same) and confirmed by Peter the same day. The
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
