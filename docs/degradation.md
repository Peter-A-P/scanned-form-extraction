# Degradation: what each level does to reading

Written by `legible calibrate` from the OCR stored at every level; do not edit. The method is in `legible/calibrate.py`; the levels are `LEVELS` in `legible/degrade.py`.

300 NIST SD2 pages (the curve pages, `manifests/nist-splits.json`), tesseract 5.3.4, run on the measuring machine (docs/ocr.md). Each cell is the mean over pages with its 95% bootstrap interval.

| Level | Resolution | Blur | Skew up to | Noise | JPEG quality | Word accuracy against the clean read | Field words recovered |
|---:|---:|---:|---:|---:|---:|---|---|
| 0 | 300 dpi | 0.0 px | 0.0 degrees | 0.0% | none | 100.0% (100.0 to 100.0) | 64.0% (62.2 to 65.9) |
| 1 | 200 dpi | 0.5 px | 0.5 degrees | 0.1% | 85 | 56.6% (55.1 to 58.1) | 39.3% (37.3 to 41.4) |
| 2 | 150 dpi | 0.8 px | 1.0 degrees | 0.5% | 60 | 53.2% (51.9 to 54.6) | 36.5% (34.6 to 38.5) |
| 3 | 120 dpi | 1.2 px | 2.0 degrees | 1.0% | 40 | 39.4% (37.9 to 40.8) | 29.1% (27.2 to 31.0) |
| 4 | 100 dpi | 1.6 px | 3.0 degrees | 2.0% | 25 | 16.1% (15.1 to 17.2) | 17.3% (15.8 to 18.8) |
