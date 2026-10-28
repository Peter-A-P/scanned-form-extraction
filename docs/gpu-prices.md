# Machines and their prices

Every machine this project rented, at the rate RunPod's API returned when the pod was created
(`costPerHr`), with the date. Costs per page in the README are computed from these rates.

| Machine | What it did | Cloud | US$ an hour | Date |
|---|---|---|---:|---|
| CPU pod `cpu3c`, 16 vCPU, 32 GB (EUR-IS-1, then EU-RO-1) | Tesseract on every dev, test and curve page; OCR is costed at a sixteenth of this a vCPU | Secure | 0.48 | 2026-10-17 |
| RTX A5000, 24 GB (CA-MTL-1) | Arm B's fine-tunes, 2B first | Secure | 0.27 | 2026-10-18 |
| RTX 4090, 24 GB (US) | Arm B's fine-tunes, 4B | Secure | 0.89 | 2026-10-18 |
| RTX 3090, 24 GB | Arms B and C served by vLLM and read through the gateway | Secure | 0.50 | 2026-10-18 |
| RTX A6000, 48 GB | Arm B's 4B on DeepForm, which ran out of memory on 24 GB at its first step | Secure | 0.59 | 2026-10-18 |
| RTX 3090, 24 GB (EU-CZ-1) | The load test of both sizes (docs/serving.md), then the 4B NIST seed 1's reads | Secure | 0.50 | 2026-10-23 |
| CPU pod, 16 vCPU, 32 GB (US-CA-2) | Tesseract on the VRDU curve subset at levels 2 and 4 | Secure | 0.48 | 2026-10-23 |
| RTX A5000, 24 GB (CA) | The ablations: the 560-token runs and CORD's data-volume runs (NIST's 560-token run ran out of memory on it) | Secure | 0.27 | 2026-10-27 |
| RTX A6000, 48 GB (SE) | The ablations: the multi-corpus E2B run (no A5000 or 3090 free) | Secure | 0.59 | 2026-10-27 |
| RTX 3090, 24 GB (CZ) | The ablations served by vLLM and read through the gateway | Secure | 0.50 | 2026-10-27 |
| RTX A6000, 48 GB, two pods | The ablations: NIST's 560-token run, and NIST's data-volume runs | Secure | 0.59 | 2026-10-27 |
| RTX 3090, 24 GB | NIST's data-volume ablations read through the gateway | Secure | 0.50 | 2026-10-28 |

**The provider rule** is 06's (`docs/gpu-prices.md` there): a hyperscaler's spot GPU if it is
within 20% of the rental marketplaces, otherwise the marketplace. 06 found GCP's L4 spot 24%
above a marketplace 4090 on 2026-09-21; it was not re-checked here, and RunPod was used.
On 2026-10-18 RunPod's Community Cloud had no 4090 or A5000 free, so both GPUs are Secure
Cloud; a first 4090 offered at US$0.89 on a host RunPod flagged with "a critical error" was
deleted unused.

Checkpoints and adapters go to this project's network volume (`legible-checkpoints`, 60 GB,
EU-RO-1, created 2026-10-18) through RunPod's S3 API, under `legible/`, and each run's
checkpoints are removed once its adapter is stored. The first runs used 06's volume, which 06's
merged formats nearly fill: an upload of the rendered pages (6.2 GB, to give the other pods the
pages rather than render them again) was refused for quota, and the three adapters already
there were moved across.
