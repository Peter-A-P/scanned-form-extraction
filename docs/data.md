# Data: licences, sources and layouts

Every licence below is quoted from its primary source, read on **2026-10-16**, before anything
was fetched. VRDU and CORD were fetched the same day, after this file was written, and every
file verified against the checksums committed in `legible/data/checksums/`. NIST SD2 has not
been fetched.

Fetched and rendered files live under the data root (`LEGIBLE_DATA`, default `./data`), never
in the repository; the page manifests in `manifests/` are committed, one line per page with its
sha256 and the renderer's version, and the split summaries beside them.

## Summary

| Corpus | Terms as found | Status |
|---|---|---|
| VRDU Registration Forms (FARA) | CC BY 4.0, stated only by a hyperlink in Google's release post; the repository has no licence file | Usable, with the provenance recorded below |
| VRDU Ad-buy Forms (DeepForm) | As above | Usable, with the provenance recorded below |
| CORD v2 | CC BY 4.0, stated in the GitHub README, the Hugging Face card and the repository's licence file | Usable |
| NIST Special Database 2 | **Not stated for SD2.** NIST's general statements point two ways (below) | **Not fetched until resolved** |
| SROIE | No licence or terms stated anywhere authoritative | Out, as the plan already said |

## VRDU

**Source.** https://github.com/google-research-datasets/vrdu, archived (read-only) since
2026-04-19. The GitHub API reports `"license": null` and the README has no licence section.

**Licence.** Google's release post, "Advances in document understanding" (2023-08-09),
https://research.google/blog/advances-in-document-understanding/:

> "We are excited to announce the public release of the VRDU dataset and evaluation code under
> a Creative Commons license."

In the page's HTML, "Creative Commons license" links to
`https://creativecommons.org/licenses/by/4.0/`. That hyperlink is the only statement of the
variant. The dataset page, https://research.google/resources/datasets/visually-rich-document-understanding/,
states no licence. The evaluation code lives in
https://github.com/google-research/google-research/tree/master/vrdu under Apache-2.0 (the file
headers say "Licensed under the Apache License, Version 2.0"); this repository reimplements
its matchers rather than importing it (`legible/grade.py`).

What this means here: the pages are US public records in any case (FARA filings published by
the Department of Justice, political-file orders published through the FCC); the benchmark's
annotations are used under CC BY 4.0 with attribution to Google Research and the VRDU paper
(Wang et al., KDD 2023). Nothing is redistributed: the loader fetches from the repository.

**Files** (raw base `https://raw.githubusercontent.com/google-research-datasets/vrdu/main/`;
plain files, not LFS; no checksum file exists, so the loader records the git blob SHA from the
trees API and a sha256 of its own on first fetch):

| File | Bytes | Git blob SHA |
|---|---:|---|
| `registration-form/main/dataset.jsonl.gz` | 54,839,306 | `0e969476fbd88196301bcb3d3c1da4a4c1645906` |
| `ad-buy-form/main/dataset.jsonl.gz` | 31,986,319 | `224b1ea96e7d09e613855480745e342cf702744a` |
| `{corpus}/main/meta.json`, `{corpus}/main/pdfs/*.pdf`, `{corpus}/few_shot-splits/*.json` | | |

**Counts.** 1,915 registration PDFs and 641 ad-buy PDFs in the repository tree, as the plan
assumed.

**Annotations.** Each `dataset.jsonl` record has `filename`, `ocr` (`text` in reading order,
`pages` with tokens, lines, paragraphs and blocks) and `annotations`. A simple entity is
`[name, [[text, [page, x1, y1, x2, y2], [[start, end], ...]], ...]]` with a normalised box; a
field can carry several truth candidates and matching any one counts. A line item has a list
of names and exactly one candidate.

Fields, from `meta.json`, with VRDU's matcher:

| Corpus | Field | VRDU matcher |
|---|---|---|
| FARA | `file_date` | DateMatch |
| FARA | `foreign_principle_name` (misspelled in the source; kept as is) | NameMatch |
| FARA | `registrant_name` | NameMatch |
| FARA | `registration_num` | NumericalStringMatch |
| FARA | `signer_name` | NameMatch |
| FARA | `signer_title` | GeneralStringMatch |
| DeepForm | `advertiser`, `agency`, `product`, `property` | GeneralStringMatch |
| DeepForm | `contract_num` | NumericalStringMatch |
| DeepForm | `flight_from`, `flight_to` | DateMatch |
| DeepForm | `gross_amount` | PriceMatch |
| DeepForm | `tv_address` | AddressMatch |
| DeepForm line item | `channel`, `program_desc` | GeneralStringMatch |
| DeepForm line item | `program_start_date`, `program_end_date` | DateMatch |
| DeepForm line item | `sub_amount` | PriceMatch |

**Splits.** Each split file has `train`, `valid` and `test`, three seeds (`SD_0` to `SD_2`) and
train sizes 10, 50, 100 and 200. FARA names its levels `lv1-single_*`, `lv2-mixed_template` and
`lv3-unk_*`; DeepForm names them `kno_template`, `mixed_template` and `unk_template`. **The
DeepForm unseen-template test set shrinks as the train size grows** (for `SD_0`: 294, 237, 215
and 159 documents at train 10, 50, 100 and 200), so the train size chosen fixes the headline
test set.

**Decided 2026-10-16: the headline is train size 200, at all three seeds.** For FARA that is
nine unseen-template files (three held-out templates at three seeds) and three mixed-template
files; for DeepForm three of each. Each arm reads every document in the union of those test
sets once, and each file's number is graded from those reads (`manifests/*-splits.json`
records the union's page count, which is what a full arm costs). The fine-tune trains once
per seed on that seed's train set, so the three seeds carry training variance as the plan
asks.

Two things the files show that the plan did not say:

- **FARA's unseen-template files draw dev from the held-out template too**: in
  `FARA-lv3-unk_Amendment-...-SD_0`, train is 127 Short-Form and 73 Dissemination Report
  forms, and both valid and test are Amendments. Thresholds tuned on that dev set have seen
  the held-out template's layout, though not its test pages. The review rate on FARA's
  unseen split says so beside the number.
- **Templates are checkable for FARA and not for DeepForm.** FARA's file names end with the
  template (`..._Amendment.pdf`), and the build checks that no unseen-template file shares a
  template between train and held-out documents. DeepForm publishes no template label, so
  its unseen claim rests on the benchmark's construction.

Documents are multi-page: FARA 1 to 3 pages (most 2), DeepForm 1 to 12. Every arm reads a
document's pages together and is graded per document.

**Invented values** are told from misreads with the page text: for VRDU, the `ocr.text` the
benchmark ships.

## CORD v2

**Licence.** https://github.com/clovaai/cord README:

> "This work is licensed under a [Creative Commons Attribution 4.0 International License][cc-by]."

linking to http://creativecommons.org/licenses/by/4.0/. The repository's `LICENSE-CC-BY` is
the full CC BY 4.0 legal code. The Hugging Face card,
https://huggingface.co/datasets/naver-clova-ix/cord-v2, has `license: cc-by-4.0`, and its
`dataset_infos.json` says "Creative Commons Attribution 4.0 International License".

**Files.** Hugging Face `naver-clova-ix/cord-v2` at commit
`7f0115a4b758a71d6473b8d085751692da2fef98`: four train parquet shards, one validation, one
test, about 2.3 GB in all. Each file's LFS sha256 is the checksum the loader verifies; the
full hashes are read from the Hub's tree API at that commit and pinned in the loader.

**Counts.** train 800, validation 100, test 100.

**Annotations.** Columns `image` and `ground_truth` (a JSON string). `gt_parse` is the parse
tree: top-level `menu`, `void_menu`, `sub_total` and `total` (the README calls the
superclass `subtotal`; the key is `sub_total`). Thirty field classes, the README rows not
struck through. Sub-menu fields appear to sit under `menu[i].sub` in v2, and `menu` is a dict
rather than a list when there is one item; both confirmed on the test shard on 2026-10-16.
A few `sub_total` and `total` fields are lists (two tax lines, two cash tenders): the first is
the truth and the rest alternatives (`legible/data/cord.py`). Prices are printed as 60.000,
60,000, 60000.00, Rp.60.000 and @60,000 for the same amount, so CORD's numbers use the "auto"
decimal mark (`legible/grade.py`). `valid_line` holds only annotated words, not the whole
receipt, so CORD's invented-versus-blank-filled split waits for the Tesseract text of each
receipt; until then a filled blank box on a receipt counts as blank filled. The
README notes that store, payment and other information were removed "due to Indonesian legal
issues".

## NIST Special Database 2

**Terms: unresolved.** The SD2 page, https://www.nist.gov/srd/nist-special-database-2
(updated 2025-12-01), states no licence or terms; it says "Price: No charge". The plan's
"public domain" is not stated anywhere for SD2. The data.nist.gov record (DOI
10.18434/M3J08M) points to https://www.nist.gov/open/license, which carries two regimes:

For Standard Reference Data:

> "Copyright protection on this compilation of data has been secured by the Secretary of the
> U.S. Department of Commerce ... All rights reserved."

For other NIST data:

> "This data/work was created by employees of the National Institute of Standards and
> Technology (NIST), an agency of the Federal Government. Pursuant to title 17 United States
> Code Section 105, works of NIST employees are not subject to copyright protection in the
> United States. This data/work may be subject to foreign copyright. The data/work is provided
> by NIST as a public service and is expressly provided "AS IS." ..."

The Special Database Catalog says "Some of these databases will be designated as SRD
Databases", and nothing found says whether SD2 is one. If it is, https://www.nist.gov/srd/public-law
applies: "None of our SRD may be reproduced ... without prior permission." Using the pages
for measurement and training is likely fine under either regime; publishing derived adapters
and showing page images on the demo is what the answer decides. **SD2 is not fetched until
NIST confirms which regime applies.**

**Files.** `https://s3.amazonaws.com/nist-srd/SD2/sd02.zip` (938,768,464 bytes, Last-Modified
2017-02-16) and `sd02_md5.lst` (an MD5 for each file inside the archive, 11,200 lines). The
users' guide is `https://s3.amazonaws.com/nist-srd/SD2/users_guide_sd2.pdf` (February 2017).

**Layout.** `sd02/data/sfrs_{0..8}/r{NNNN}/r{NNNN}_{KK}.png` with a matching `.fmt` answer
file, 5,590 of each, submissions `r0000` to `r0899`. 300 ppi binary PNG, machine print of
synthesised values. `sd02/tables/` holds 20 `.tab` files, one per form face, each listing
field id, type (alphanumeric, floating point, integer, non-character) and context (data, name,
SSN). The first line of a `.fmt` names the form face; each following line is a field id and its
value, with `_ICON_` for check marks and signatures. The exact line syntax is confirmed on the
first fetch. The form type is known only from that first line, not from the file name.

**Counts.** 5,590 pages, 12 form types on 20 faces, 900 submissions, as the plan assumed.

## SROIE

https://rrc.cvc.uab.es/?ch=13 states no licence or terms of use, and the download section is
behind registration. Not used, as the plan already said.
