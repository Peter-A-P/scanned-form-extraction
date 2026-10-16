# Architecture

The diagrams behind [PLAN.md](../PLAN.md), in Mermaid so they render on GitHub and change in
the same commit as the code they describe. Six views: the system, one page through the five
arms, the fine-tuning and serving loop, the evaluation design, the review-rate computation, and
the public site.

## 1. The system

Public corpora in, numbers out, and one ledger for every model call.

```mermaid
flowchart LR
  subgraph corpora["Public corpora (fetched, checksummed, never committed)"]
    VRDU["VRDU<br/>registration and ad-buy forms<br/>PDF + annotations"]
    CORD["CORD v2<br/>receipts<br/>photos + annotations"]
    NIST["NIST SD2<br/>tax forms<br/>binary scans + field files"]
  end

  corpora --> fetch["legible data fetch<br/>loaders, checksums, licences quoted"]
  fetch --> render["render<br/>300 dpi pages + manifest"]
  render --> split["split<br/>benchmark splits, NIST by submission,<br/>dev carve-out, leakage check"]
  split --> degrade["degrade<br/>levels 0 to 4, fixed seed,<br/>calibrated to OCR word accuracy"]
  degrade --> pages[("data/pages<br/>data/degraded")]

  pages --> arms
  subgraph arms["Five arms, same pages"]
    A["A frontier vision"]
    B["B fine-tuned small vision"]
    C["C untuned small vision"]
    D["D OCR text + language model"]
    E["E OCR + rules"]
  end

  A & D -->|"image or text blocks,<br/>data_class=public"| GW["04 boundary gateway<br/>ledger, caps, batch, cache"]
  GW --> vendors["Anthropic / OpenAI / Google"]
  B & C -->|"served on rented GPU,<br/>registered as a host"| GW
  D & E --> OCR["Tesseract (hOCR)"]

  arms --> grade["grade<br/>schema matchers, miss taxonomy,<br/>bootstrap over documents, paired deltas"]
  grade --> results[("data/runs<br/>predictions + outcomes")]
  results --> review["review<br/>confidence thresholds on dev,<br/>review rate on test"]
  results --> verify["verify<br/>arithmetic and format checks"]
  results --> gate["03 gate<br/>non-inferiority per corpus"]
  GW -->|"cost per page"| cost["bench/cost + breakeven<br/>(06's arithmetic)"]
  review & verify & gate & cost --> report["report<br/>README tables, charts, cards"]
  report --> site["site<br/>forms.peterparker.ca (static)"]
```

## 2. One page through the five arms

What each arm sees and what it returns. The schema is one definition; the prompt, the training
target and the grader all read from it.

```mermaid
flowchart TB
  page["One page image<br/>(level 0 to 4)"] --> schema["Schema for its corpus<br/>fields, types, matchers, nesting"]

  schema --> A
  schema --> B
  schema --> C
  schema --> D
  schema --> E

  subgraph A["A: frontier vision"]
    A1["image block + instruction + schema"] --> A2["frontier model via gateway<br/>structured output where offered"] --> A3["JSON"]
  end
  subgraph B["B: fine-tuned small vision"]
    B1["image at 1120 or 560 visual tokens<br/>+ instruction"] --> B2["Gemma 4 E2B / E4B + QLoRA adapter<br/>served on rented GPU"] --> B3["JSON + per-field logprob confidence"]
  end
  subgraph C["C: untuned small vision"]
    C1["same input, zero- or few-shot"] --> C2["Gemma 4 E2B / E4B -it"] --> C3["JSON"]
  end
  subgraph D["D: OCR text + language model"]
    D1["Tesseract hOCR<br/>words with boxes"] --> D2["positioned text rendering"] --> D3["same frontier model as A,<br/>text only, via gateway"] --> D4["JSON"]
  end
  subgraph E["E: OCR + rules"]
    E1["Tesseract hOCR"] --> E2["per-template anchors<br/>+ patterns (training templates only)"] --> E3["JSON or blank"]
  end

  A3 & B3 & C3 & D4 & E3 --> grader["grader<br/>per field: right / wrong field / wrong value /<br/>blank filled / invented / malformed"]
  grader --> out["outcomes per document<br/>+ document-level all-right"]
```

## 3. Fine-tuning and serving

06's loop with a vision encoder. Spot GPUs, so every run resumes from object storage.

```mermaid
flowchart LR
  train_pages["training split pages<br/>+ JSON targets from the schema"] --> ds["train/dataset.py"]
  ds --> qlora["train/qlora.py<br/>4-bit base, PEFT rank 16,<br/>vision encoder frozen,<br/>projector + language layers trained"]
  prices["docs/gpu-prices.md<br/>day-one table, provider rule"] --> gpu["rented spot GPU<br/>L4 / 4090 class; A100 for E4B at 1120"]
  qlora --> gpu
  gpu -->|"every N steps"| ckpt[("object storage<br/>checkpoints")]
  ckpt -->|"resume after interruption"| gpu
  gpu --> ablate["ablate: token budget 1120 vs 560,<br/>data volume all / half / quarter,<br/>three seeds, multi-corpus run"]
  ablate --> merge["merge to bf16"]
  merge --> hf["Hugging Face<br/>adapters + cards with failure modes"]
  merge --> serve["serve: vLLM if Gemma 4 vision is supported,<br/>else batched Transformers"]
  serve --> reg["gateway host registration<br/>price = GPU-hour rate / measured pages per hour"]
  reg --> load["bench/load.py<br/>concurrency 1, 8, 32; p50, p99"]
  load --> be["breakeven over utilisation<br/>(06's staircase)"]
```

## 4. Evaluation design

Which pages carry which claim, and why the test sets are touched once.

```mermaid
flowchart TB
  subgraph vrdu["VRDU (both corpora)"]
    v_train["train templates"] --> v_dev["dev (carved from train)"]
    v_train --> v_mtl["mixed-template test<br/>(reported as the gap)"]
    v_utl["unseen-template test<br/>(templates disjoint from train)<br/>HEADLINE"]
  end
  subgraph cord["CORD"]
    c_train["800 train"] --> c_dev["100 dev"]
    c_test["100 test"]
  end
  subgraph nist["NIST SD2"]
    n_sub["split by simulated submission<br/>leakage check on every build"] --> n_train["train"]
    n_sub --> n_test["test: 500 clean pages"]
    n_test --> n_deg["300 pages x levels 1 to 4<br/>DEGRADATION CURVE"]
    n_train --> n_vol["data-volume curve<br/>all / half / quarter"]
  end

  v_dev & c_dev --> thresholds["prompt iteration and<br/>confidence thresholds<br/>(dev only)"]
  thresholds --> once["each test set run once per arm"]
  v_utl & v_mtl & c_test & n_test & n_deg --> once
  once --> boot["bootstrap over documents,<br/>95% intervals,<br/>paired deltas on identical items"]
  boot --> gate["03 gate: non-inferiority,<br/>delta 3 points, per corpus"]
```

## 5. Review rate

The product number: at 99 percent accuracy on the fields a machine keeps, how many fields go
to a person.

```mermaid
flowchart LR
  B_conf["arm B: per-field<br/>logprob confidence"] --> thr
  AD_agree["arms A and D: agreement<br/>between vision read and OCR text read<br/>of the same page"] --> thr
  thr["choose threshold on dev<br/>so accepted fields are 99% right"] --> apply["apply to test"]
  apply --> keep["accepted fields<br/>(accuracy reported)"]
  apply --> route["routed to a person<br/>= review rate"]
  verify["verify: arithmetic and format checks"] --> caught["errors caught before review<br/>(catch rate)"]
  keep --> caught
```

## 6. The public site

Static, free, nothing modelled in the browser, nothing uploaded.

```mermaid
flowchart LR
  report["legible report"] --> json["site JSON:<br/>per-page reads per arm with boxes,<br/>tables, degradation series"]
  images["page images shown:<br/>NIST (synthetic), CORD (CC BY 4.0),<br/>VRDU ad-buy (business documents)<br/>never registration forms"] --> build
  json --> build["legible site<br/>writes site/out"]
  build --> swa["Azure Static Web Apps (free tier)<br/>forms.peterparker.ca"]
  swa --> viewer["viewer: boxes right/wrong with truth<br/>slider: levels 0 to 4<br/>tables: cost, review rate, intervals"]
```
