# The demo site, forms.peterparker.ca

A static site (PLAN.md 2.8): plain HTML, CSS and JavaScript in `legible/site/`, and the JSON
and page images `legible site` writes beside them into `site/out/` (gitignored). No framework,
no CDN, no build step beyond the command. Nothing is modelled in the browser and nothing is
uploaded: every read on it was made, and graded, before the site was built.

## What it shows

- **The page viewer.** Eight test pages from each of three corpora: NIST's synthesised tax
  forms, CORD's receipts (CC BY 4.0) and DeepForm's ad-buy forms (VRDU, FCC public files). For
  the reader chosen (any arm in `legible.report.ARMS`: the four frontier vision models,
  Sonnet on the OCR text, OCR plus rules, the two fine-tunes at seed 0 and the two untuned
  bases), each field it read is drawn on the page where the corpus says the field is printed,
  green when right and red, dashed, when wrong, with what it read and the truth beside it.
  Right and wrong are the project's grader's (`legible.grade.grade_document`), called exactly
  as `legible report` calls it; the browser draws the flags and never compares a value.
- **Where a field is.** DeepForm: VRDU's entity boxes. CORD: the word quads of the line CORD
  labels with the field. NIST: SD2 publishes no field positions, so the boxes are the zones arm
  E learned from the training pages (`legible/arms/nist_zones.json`), registered to the page by
  its own level-0 OCR; they show where the field sits on the form, and are approximate. A field
  with no location (a CORD value no labelled line carries, a NIST field with no learned zone),
  a value the truth does not carry (a filled blank, an extra line item), and a field on a page
  past the first two of a long document are listed beside the page instead of drawn.
- **The degradation slider.** NIST pages step through levels 0 to 4 and DeepForm pages through
  0, 2 and 4 (the VRDU curve subset); CORD was read at level 0 only. Each level shows the page
  as the arms were sent it (the stored degraded copy, or the same bytes made in memory by
  `legible.degrade`), each arm's read of that page at that level, and each arm's accuracy over
  all the curve pages at that level with its 95% interval, from the same rows as the README's
  curve tables. On a degraded page each box is turned by the skew `degrade` applied
  (`legible.degrade.skew_angle`). An arm with no read at a level says "not yet read".
- **The tables.** Every headline and template-gap table (fields correct, every field right,
  invented fields, cost per 1,000 pages), with each cost's price date; the curves; and the
  review rate at 99% for each confidence signal. They are serialised from
  `legible.report.Results`, the object the README's tables are formatted from, with the
  report's own cell text, so the site and the README cannot disagree.

**Registration forms are never shown.** FARA's forms name individuals, so FARA is in the
tables only. `legible.site.build` refuses to make an image or a page record of any corpus but
NIST, CORD and DeepForm, and checks the finished directory once more
(`tests/test_site.py` holds both).

**Which pages.** For each corpus, 8 ids drawn with `random.Random(16)` from the sorted set:
NIST from the 300 curve pages, CORD from its 100 test receipts, DeepForm from the 30
unseen-template test documents of the VRDU curve subset. The draw depends on the set alone,
never on how any arm did. Images are JPEG at 1,000 pixels wide.

## Build it

```powershell
$env:LEGIBLE_DATA = "C:/Users/peter/legible-data"   # where the runs are
uv run legible site                                  # writes site/out/, about 6 minutes
```

It grades every run the report grades (the tables), then the chosen pages. It reads the data
root and writes nothing there. Rebuild whenever `legible report` would change the README.

## Look at it locally

```powershell
uv run legible site --serve        # http://localhost:8016
```

`--serve` builds nothing: it serves `site/out/` with the headers and content types in its
`staticwebapp.config.json`, the content security policy included, as 08's `headroom serve`
does. **Not `python -m http.server`**, which sends no policy and so shows a page the live site
might partly refuse. Open the browser console and confirm it is empty: a policy violation is
reported there and nowhere else.

The policy is `default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'` with
no inline script or style, no frames, no form posts and no connections beyond the site.

## Deploy it

Not done yet. It follows 08's `docs/deploy.md`
([capacity-planning-forecaster](https://github.com/Peter-A-P/capacity-planning-forecaster/blob/main/docs/deploy.md)),
with these names:

1. **Check the subscription first.** `az login`, `az account set --subscription ...`, and
   `az staticwebapp list -o table` must list the other sites; note their resource group.
2. **Create the Static Web App** beside them: name `forms-peterparker-ca`, plan **Free**,
   deployment source **Other** (not GitHub, which would commit a workflow and an Azure
   credential to this public repository).

   ```powershell
   az staticwebapp create --name forms-peterparker-ca --resource-group <group> --location <region> --sku Free
   ```

3. **DNS at Cloudflare.** A CNAME `forms` to the app's `<generated-name>.azurestaticapps.net`,
   proxy status **DNS only** (the grey cloud: a proxied record hides the CNAME from Azure's
   validation and the certificate is never issued). Then in the app, Custom domains, add
   `forms.peterparker.ca` as a CNAME on other DNS, or:

   ```powershell
   az staticwebapp hostname set --name forms-peterparker-ca --resource-group <group> --hostname forms.peterparker.ca
   ```

4. **Publish the built files.** The token is read into one shell's environment, never typed
   on a command line, never committed, never put in `CLAUDE.local.md` or a chat:

   ```powershell
   $env:SWA_CLI_DEPLOYMENT_TOKEN = az staticwebapp secrets list --name forms-peterparker-ca --resource-group <group> --query properties.apiKey -o tsv
   npx --yes @azure/static-web-apps-cli deploy ./site/out --env production
   ```

5. **Check it.** `https://forms.peterparker.ca` over HTTPS with no warning, the numbers on the
   tables tab equal to the README's, and an empty browser console.
