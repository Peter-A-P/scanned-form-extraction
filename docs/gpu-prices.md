# Machines and their prices

Every machine this project rented, at the rate RunPod's API returned when the pod was created
(`costPerHr`), with the date. Costs per page in the README are computed from these rates.

| Machine | What it did | Cloud | US$ an hour | Date |
|---|---|---|---:|---|
| CPU pod `cpu3c`, 16 vCPU, 32 GB (EUR-IS-1, then EU-RO-1) | Tesseract on every dev, test and curve page; OCR is costed at a sixteenth of this a vCPU | Secure | 0.48 | 2026-10-17 |
| RTX A5000, 24 GB (CA-MTL-1) | Arm B's fine-tunes, 2B first | Secure | 0.27 | 2026-10-18 |
| RTX 4090, 24 GB (US) | Arm B's fine-tunes, 4B | Secure | 0.89 | 2026-10-18 |

**The provider rule** is 06's (`docs/gpu-prices.md` there): a hyperscaler's spot GPU if it is
within 20% of the rental marketplaces, otherwise the marketplace. 06 found GCP's L4 spot 24%
above a marketplace 4090 on 2026-09-21; it was not re-checked here, and RunPod was used.
On 2026-10-18 RunPod's Community Cloud had no 4090 or A5000 free, so both GPUs are Secure
Cloud; a first 4090 offered at US$0.89 on a host RunPod flagged with "a critical error" was
deleted unused.

Checkpoints and adapters go to 06's network volume (`smallprint-checkpoints`, 100 GB,
EU-RO-1) through RunPod's S3 API, under `legible/`, and each run's checkpoints are removed once
its adapter is stored.
