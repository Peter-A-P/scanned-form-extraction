# Serving: latency, throughput and break-even

PLAN.md 2.7. The numbers are in the README's serving tables, written by `legible report` from
the load-test records; this page says how they were measured and what they do and do not say.

## The load test

Each fine-tune is merged into its bf16 base (`legible serve merge`, the merge checked against
the adapter on training examples), served by vLLM 0.30.0 alone on one RTX 3090 24 GB rented
from RunPod's Secure Cloud at the rate its API returned when the pod was created
(docs/gpu-prices.md), and read through the gateway by 06's closed-loop load client
(`legible bench run`, `ops/bench.sh`, `legible/bench/`).

- **What is sent.** The model's own test documents at level 0, built by the same function and
  with the same prompt, visual-token budget, output budget and temperature 0 as its accuracy
  reads, cycled in order. A read is one document with every page of it as an image, so the
  latency is the latency of the answers graded, not of a synthetic prompt.
- **Closed loop at 1, 8 and 32 in flight.** The next read is sent as each one returns, the way
  a pool of N workers behaves. A level is 100 reads, or ten rounds of the loop if more, and
  goes on for at least three minutes after a 30-second warm-up that is discarded: a CORD
  receipt at 32 in flight returns in under three seconds, and a level of 320 reads alone was
  over in half a minute.
- **One attempt.** The served configuration sets the gateway's retries to one attempt, so a
  read that fails is counted as an error, not hidden inside a percentile; every level reports
  its errors and retries.
- **Percentiles are nearest-rank** and every figure carries a 95% bootstrap interval over
  reads. With 100 reads a p99 is close to the maximum, and its interval says so.
- **Throughput** is the pages of the successful reads over the measured window, from the first
  read sent to the last finished. The cost per 1,000 pages beside it is the card's hourly rate
  over that throughput with the card kept busy all hour; the break-even tables show what a
  lower utilisation does to it.

One FARA model was load-tested (the amendment template's), since FARA's three held-out
templates' models are the same architecture reading the same kind of page; DeepForm, CORD and
NIST each have one model a size.

## What it does not measure

- **The frontier models' latency.** They were read through the vendors' batch interfaces, at
  half price, whose answers arrive within a 24-hour window; a batch read's latency is the
  batch's, not the page's. Their synchronous latency would have to be measured
  from a machine that is not the laptop (CLAUDE.md), and was not.
- **Arm C.** The untuned bases are the same two architectures; their reads are too inaccurate
  to serve (the README's tables), so they were not load-tested.
- **Run-to-run variation.** The throughput interval resamples reads with the window fixed, as
  06's does: honest for one steady run on one card, narrower than across cards or days.

## The break-even

06's arithmetic, unchanged (`legible/bench/breakeven.py`): the API is paid per page; a card is
rented whole, by the hour, all month. The self-hosted monthly cost is a staircase of whole
cards at the planned utilisation, and the break-even is the smallest monthly page volume at
which that staircase costs no more than paying a frontier model per page. With no fixed cost
the first card breaks even at one month's rent in API pages, whatever the utilisation, until
the utilisation is too low for one card to carry that volume; below the utilisation at which a
self-hosted page costs more than the API's, no volume breaks even and the table says "never".

Per corpus the table uses the fine-tune the 03 gate compared, the size better on dev
(docs/gate.md), at its best measured throughput, against each frontier vision model at its
headline test cost from the gateway ledger. Fixed costs (an engineer's time, storage) are zero
and printed as such; a reader with their own adds them to the rent. The break-even says
nothing about accuracy: on no corpus did a fine-tune match the frontier field by field
(docs/gate.md), so a volume at which it is cheaper is not a volume at which it is as good.
