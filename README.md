# 508-scanner-local

`508-scanner-local` is a local-first, free, open-source CLI for automated and semi-automated Section 508 / WCAG accessibility issue detection.

It crawls rendered web pages with Playwright, runs axe-core checks, discovers downloadable documents, performs basic local document checks, and writes HTML, JSON, CSV, and Markdown reports.

This tool does **not** provide legal certification or prove complete accessibility compliance. Automated checks are only one part of a complete accessibility review.

## What It Does

- Crawls a starting website URL with Playwright Chromium.
- Runs axe-core checks for WCAG 2.0 A/AA oriented rules, plus Section 508 tags when supported by axe-core.
- Captures page metadata such as title, language, headings, landmarks, links, images, and form controls.
- Finds downloadable documents and can download them locally.
- Performs basic local checks for PDF, DOCX, PPTX, and XLSX files.
- Records manual review tasks for checks that require human judgment.
- Generates:
  - `report.html`
  - `report.json`
  - `findings.csv`
  - `summary.json`
  - `manual-review.md`

## What It Does Not Do

- It does not certify Section 508 or WCAG compliance.
- It does not use cloud services, paid APIs, OCR, SaaS tools, or external databases.
- It does not fully validate PDFs, Office documents, captions, reading order, keyboard behavior, or screen reader experience.
- It does not bypass authentication.

## Install

```bash
npm install
npx playwright install chromium
npm run build
```

## Usage

Start the local browser UI:

```bash
npm run ui
```

Then open:

```text
http://127.0.0.1:5081
```

Scan a small website:

```bash
npm run scan -- --url https://example.com --max-pages 5 --out ./reports/example
```

Scan a website with depth and concurrency settings:

```bash
npm run scan -- --url https://example.gov --max-pages 50 --max-depth 3 --concurrency 2 --out ./reports/example-scan
```

Scan local documents:

```bash
npm run scan -- --files ./some-file.pdf ./some-file.docx --out ./reports/docs
```

Include screenshots:

```bash
npm run scan -- --url https://example.com --include-screenshots --out ./reports/with-shots
```

## CLI Options

- `--url <url>` starting website URL
- `--files <paths...>` local document files to scan
- `--max-pages <number>` default `25`
- `--max-depth <number>` default `3`
- `--concurrency <number>` default `2`
- `--out <directory>` default `./reports/<timestamp>`
- `--include-screenshots` default `false`
- `--download-documents` default `true`
- `--timeout-ms <number>` default `60000`
- `--same-origin` default `true`
- `--same-host` default `true`
- `--verbose` default `false`

## Output Files

- `report.html`: accessible human-readable report.
- `report.json`: complete structured scan result.
- `findings.csv`: normalized findings for spreadsheet use.
- `summary.json`: short metrics summary.
- `manual-review.md`: human review checklist grouped by asset.
- `raw/web/`: raw axe results per page.
- `raw/pdf/`: raw veraPDF output when available.
- `downloads/`: downloaded documents discovered during crawling.
- `screenshots/`: optional page screenshots.

## Section 508 / WCAG Baseline

The default web baseline is Section 508-oriented reporting with WCAG 2.0 Level A and AA automated checks. The scanner runs axe-core with `wcag2a` and `wcag2aa` tags, and attempts `section508` when supported. If axe-core does not support that tag in the installed version, the scanner falls back gracefully to WCAG 2.0 A/AA.

WCAG 2.1 and 2.2 tags may appear when axe-core reports them.

## veraPDF

If the `verapdf` CLI is installed locally and available in `PATH`, PDF files are also checked with veraPDF and raw output is saved under `raw/pdf/`.

Install veraPDF separately from:

```text
https://verapdf.org/software/
```

The scanner still works without veraPDF and will add manual review findings recommending PDF/UA or tagged PDF validation.

## Security Notes

The crawler blocks localhost, private network ranges, link-local addresses, and the AWS metadata IP by default. This is SSRF protection, even though the app runs locally, because crawled pages can contain links to internal services.

## Troubleshooting

If Playwright cannot launch Chromium:

```bash
npx playwright install chromium
```

If tests or builds fail after upgrading dependencies:

```bash
npm install
npm run build
npm run test
```

## Development

```bash
npm run dev -- --url https://example.com --max-pages 2
npm run test
npm run build
```
