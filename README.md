# 508 / WCAG 2.1 AA Accessibility Scanner — Deterministic Build

Internal accessibility QA tool for scanning websites and documents against **Section 508** and **WCAG 2.1 AA** standards. All checks in this branch are **rule-based and deterministic** — no AI or API keys required.

> **AI-enhanced version:** The [`AI-enabled`](../../tree/AI-enabled) branch adds Groq/LLM-powered semantic checks for alt text quality, link text analysis, and heading structure evaluation on top of everything here.

---

## Standards Reference

### Section 508 (29 U.S.C. § 794d)
Federal law requiring federal agencies and their contractors to make electronic and information technology accessible to people with disabilities. The technical requirements are defined in the **Revised 508 Standards (2018)**, which incorporate WCAG 2.0 Level AA by reference for web content (§ E205) and apply specific criteria for software (§ E207) and documents (§ E205.4).

### WCAG 2.1 Level AA
The Web Content Accessibility Guidelines published by W3C/WAI, organized into four principles:
- **Perceivable** — information must be presentable in ways users can perceive
- **Operable** — UI components must be operable by all users
- **Understandable** — information and UI operation must be understandable
- **Robust** — content must be interpretable by current and future assistive technologies

This tool targets **Level AA conformance**, which includes all Level A criteria plus the additional Level AA criteria.

---

## What Gets Checked and Why

### Web Pages (`scanners/web.py`)

Powered by **Playwright** (headless Chromium) + **axe-core 4.x** (Deque's open-source accessibility engine). The scanner crawls in-scope pages, injects axe-core as a script tag, runs `axe.run()`, and converts each violation into a structured `Finding`.

| Check | WCAG SC | 508 Ref | How It Works |
|---|---|---|---|
| **Image alt text missing** | 1.1.1 | E205.4 | axe detects `<img>` with no `alt` attribute. Without alt text, screen readers announce the filename or skip the image entirely. |
| **Color contrast** | 1.4.3 | E207.2 | axe computes the foreground/background luminance ratio. Normal text requires ≥ 4.5:1; large text (18pt+ or 14pt bold) requires ≥ 3:1. |
| **Form label missing** | 1.3.1, 3.3.2 | E207.2 | axe checks that every `<input>`, `<select>`, `<textarea>` has an associated `<label>` (via `for`/`id`, `aria-label`, or `aria-labelledby`). Without a label, screen readers cannot identify the field's purpose. |
| **Heading order skipped** | 1.3.1 | E205.4 | axe flags heading level jumps (e.g., `<h1>` directly followed by `<h3>`). Skipped levels break the document outline that screen reader users rely on to navigate. |
| **Generic link text** | 2.4.4 | E205.4 | axe flags links whose accessible name is empty or non-descriptive. Screen reader users often navigate by listing all links — "click here" provides no destination context. |
| **Document language missing** | 3.1.1 | E205.4 | axe checks the `lang` attribute on `<html>`. Without it, screen readers cannot select correct pronunciation rules or apply language-specific processing. |
| **Keyboard trap** | 2.1.2 | E207.2 | axe verifies that keyboard focus is never trapped in a component without a documented escape mechanism. |
| **ARIA attribute invalid** | 4.1.2 | E207.2 | axe validates that `role`, `aria-*` attributes exist in the ARIA spec and are used correctly — e.g., `aria-required` on a role that supports it. |
| **Page title missing** | 2.4.2 | E205.4 | axe checks for a non-empty `<title>` element. Page titles orient users, especially those using screen readers or browser tabs. |
| **Skip navigation missing** | 2.4.1 | E205.4 | axe checks for a skip link (`<a href="#main">Skip to main content</a>`) that lets keyboard users bypass repeated navigation blocks. |
| **Landmark regions** | 1.3.1 | E205.4 | axe verifies that all content is contained within landmark regions (`<main>`, `<nav>`, `<header>`, etc.) so screen reader users can jump between sections. |

**Crawl behavior:** BFS from the start URL, constrained to the same origin and path prefix. Respects `robots.txt`. Rate-limited to 1 page/second. Capped at the configured max pages.

---

### PDF Documents (`scanners/pdf.py`)

Uses **pikepdf** (Python PDF library) for structural introspection and optionally **veraPDF** (industry-standard PDF/UA validator) for deep rule-based validation.

| Check | WCAG SC | 508 Ref | How It Works |
|---|---|---|---|
| **Untagged PDF** | 1.3.1 | E205.4 | pikepdf checks for `/StructTreeRoot` in the document catalog and `/MarkInfo /Marked = true`. A PDF without a tag tree has no semantic structure — screen readers cannot determine reading order, identify headings, or distinguish figures from body text. This is the most critical PDF accessibility failure. |
| **Document language not set** | 3.1.1 | E205.4 | pikepdf checks for a `/Lang` entry (e.g., `en-US`) in the document catalog. Required for correct screen reader pronunciation and language switching. |
| **Document title not set** | 2.4.2 | E205.4 | pikepdf reads `/Info /Title` from document metadata. The title is displayed in browser tabs and announced by screen readers when the document opens. |
| **Figure missing alt text** | 1.1.1 | E205.4 | pikepdf walks the structure tree for `Figure` tagged elements and checks for the `/Alt` attribute. Without `/Alt`, screen readers announce "Figure" with no description. |
| **Form field missing accessible name** | 1.3.1, 3.3.2 | E207.2 | pikepdf iterates AcroForm fields and checks for a `/TU` (tooltip) entry, which serves as the accessible name for PDF form fields. |
| **veraPDF PDF/UA rule failures** | Various | E205.4 | veraPDF validates against the PDF/UA-1 (ISO 14289-1) standard, which is the normative technical specification for accessible PDFs. Failures are mapped to findings with clause references. |

---

### Word Documents (`scanners/docx_scanner.py`)

Uses **python-docx** with direct XML inspection of the Open Packaging Conventions (OPC) structure.

| Check | WCAG SC | 508 Ref | How It Works |
|---|---|---|---|
| **No heading styles used** | 1.3.1 | E205.4 | Scans all paragraphs for `Heading 1`–`Heading 6` styles. Documents with no heading styles have no navigable structure for screen readers. |
| **Heading levels skipped** | 1.3.1 | E205.4 | Extracts the heading outline in document order and checks for level jumps. A jump from H1 to H3 means the implied H2 section doesn't exist, breaking hierarchical navigation. |
| **Fake headings** | 1.3.1 | E205.4 | Scans non-heading paragraphs for runs with bold + font size ≥ 14pt. Visually styled text is not exposed to assistive tech as a heading unless a Heading style is applied. |
| **Image alt text missing** | 1.1.1 | E205.4 | Inspects `<w:drawing>` XML elements for `<wp:docPr descr="">`. The `descr` attribute is the alt text for inline and floating images. Empty or absent `descr` means screen readers announce the image name or skip it. |
| **Table missing header row** | 1.3.1 | E205.4 | Checks for `<w:tblHeader/>` in the first row's `<w:trPr>`. Without a marked header row, screen readers cannot associate data cells with their column headers. |
| **Generic hyperlink text** | 2.4.4 | E205.4 | Parses `<w:hyperlink>` elements and checks display text against a list of non-descriptive phrases ("click here", "here", "read more", etc.). |
| **Document language not set** | 3.1.1 | E205.4 | Checks for `<w:lang>` in document settings XML. Required for correct screen reader language selection. |
| **Manual list formatting** | 1.3.1 | E205.4 | Detects paragraphs starting with bullet characters (•, -, *, etc.) or manual numbers (1., 2)) that don't use a List style. Manual lists are not exposed as list structures to assistive tech. |

---

### PowerPoint Presentations (`scanners/pptx_scanner.py`)

Uses **python-pptx** with XML inspection of the PPTX package.

| Check | WCAG SC | 508 Ref | How It Works |
|---|---|---|---|
| **Slide title missing or empty** | 2.4.6 | E205.4 | Checks each slide for a placeholder with `idx=0` (the title placeholder) and verifies it has non-empty text. Screen reader users rely on slide titles to understand which slide they are on and to navigate between slides. |
| **Duplicate slide titles** | 2.4.6 | E205.4 | Compares all slide titles for exact duplicates. Each slide should have a unique title so users can distinguish slides when navigating. |
| **Shape missing alt text** | 1.1.1 | E205.4 | Inspects `<p:cNvPr>` XML for each picture, chart, text box, and group shape and reads the `descr` attribute. Shapes without `descr` are announced only by their shape name (e.g., "Picture 3") with no content description. |
| **Reading order incorrect** | 1.3.2 | E205.4 | Checks that the title placeholder appears first in the shape tree (`<p:spTree>`). Screen readers follow the shape tree order — content before the title is read before the slide is identified. |
| **Color contrast insufficient** | 1.4.3 | E207.2 | For text runs with explicitly set foreground colors, computes relative luminance of foreground and background using the WCAG formula. Flags text below 4.5:1 (normal) or 3:1 (large, ≥ 18pt). |

---

### Excel Workbooks (`scanners/xlsx_scanner.py`)

Uses **openpyxl** plus direct ZIP/XML inspection of the XLSX package.

| Check | WCAG SC | 508 Ref | How It Works |
|---|---|---|---|
| **Workbook title not set** | 2.4.2 | E205.4 | Reads `docProps/core.xml` via openpyxl's `workbook.properties.title`. A meaningful title helps users identify the file in assistive tech and browser tabs. |
| **Default sheet names** | 2.4.6 | E205.4 | Checks sheet names against a set of default values ("Sheet1", "Sheet2", etc.). Descriptive sheet names are required for users navigating a multi-sheet workbook with a screen reader. |
| **Data not in an Excel Table** | 1.3.1 | E205.4 | For sheets with data (≥ 3 rows, ≥ 2 columns) but no `ws.tables` defined, flags the data as unstructured. Excel Table objects expose header row semantics that screen readers can announce as column headers. |
| **Table missing header row** | 1.3.1 | E205.4 | For defined Table objects, checks `headerRowCount`. Without a header row, screen readers cannot associate column names with data cells. |
| **Merged cells in data area** | 1.3.1 | E205.4 | Lists all merged cell ranges via `ws.merged_cells`. Merged cells break the row/column grid that screen readers use to navigate and announce cell position. |
| **Image or chart missing alt text** | 1.1.1 | E205.4 | Opens the XLSX ZIP archive and parses `xl/drawings/*.xml` for `<xdr:cNvPr>` elements, reading the `descr` attribute. Drawings without `descr` have no accessible description. |

---

### Standalone Images (`scanners/image.py`)

Uses **Pillow** for image validation.

| Check | WCAG SC | 508 Ref | How It Works |
|---|---|---|---|
| **No alt text provided** | 1.1.1 | E205.4 | If an image is uploaded with no alt text field filled in, a Critical finding is raised. Images without text alternatives cannot be perceived by blind users. |
| **Alt text is generic or too short** | 1.1.1 | E205.4 | Checks the provided alt text against a set of known-bad values ("image", "photo", "picture", "graphic", the filename itself) and flags text under 3 characters. These provide no meaningful information. |

---

## Severity Levels

| Level | Meaning | Examples |
|---|---|---|
| **Critical** | Blocks assistive technology entirely | Untagged PDF, missing form label, image with no alt |
| **Serious** | Major barrier — content inaccessible to many users | Low color contrast, document language missing, slide title missing |
| **Moderate** | Significant friction — usable but difficult | Skipped heading level, generic link text, default sheet name |
| **Minor** | Best-practice gap — minor friction | Manual list formatting, duplicate slide title |

---

## Prerequisites

**Python 3.10+**

**Playwright (Chromium) — required for web scanning**
```bash
pip install playwright
playwright install chromium
```

**veraPDF — optional, for deep PDF/UA validation**
Requires Java 11+. Download from [verapdf.org](https://verapdf.org/home/#download), extract, and add to `PATH`. Without it, the scanner runs pikepdf-only PDF checks.

**fpdf2 system fonts — macOS only**
`fpdf2` uses Arial from `/System/Library/Fonts/Supplemental/` which ships with macOS. No additional install needed.

---

## Setup

```bash
# 1. Clone the repo
git clone https://github.com/bkhanal4351/508-compliance-check.git
cd 508-compliance-check

# 2. Install Python dependencies
pip install -r requirements.txt

# 3. Install Playwright browser
playwright install chromium

# 4. (Optional) Configure veraPDF path
cp .env.example .env
# Edit .env if veraPDF is not on PATH
```

---

## Running

```bash
streamlit run app.py
# Open http://localhost:8501
```

---

## Running Tests

```bash
pytest tests/ -v
```

All 18 tests run fully offline against local fixture files — no network, no API keys.

---

## Architecture

```
508-scanner/
├── app.py                    Streamlit UI — sidebar, scan runner, results display
├── scanners/
│   ├── base.py               Finding model (Pydantic), Severity enum
│   ├── web.py                Playwright + axe-core; BFS crawl via crawler.py
│   ├── pdf.py                pikepdf structural checks + veraPDF subprocess
│   ├── docx_scanner.py       python-docx + OPC XML inspection
│   ├── pptx_scanner.py       python-pptx + shape tree XML inspection
│   ├── xlsx_scanner.py       openpyxl + drawing XML inspection
│   └── image.py              Pillow; deterministic alt text quality check
├── ai/
│   └── (stubs)               Reserved — see AI-enabled branch
├── report/
│   ├── builder.py            Deduplication (same rule+location), sort by severity
│   ├── pdf_export.py         fpdf2 PDF generation (Arial Unicode font)
│   └── templates/            (unused in this branch — fpdf2 is code-driven)
└── utils/
    ├── crawler.py            BFS; same-origin + path-prefix; robots.txt; 1 req/s
    └── wcag_refs.py          Rule ID → (WCAG SC, 508 ref, default severity) map
```

**Data flow:**
```
URL / File
    │
    ▼
Scanner (web / pdf / docx / pptx / xlsx / image)
    │
    ▼  List[Finding]
report/builder.py  ──▶  dedupe + sort
    │
    ├──▶  Streamlit UI (table, expanders, filters)
    ├──▶  PDF export (fpdf2)
    └──▶  CSV export
```

---

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `VERAPDF_PATH` | No | `verapdf` | Path to veraPDF CLI if not on PATH |

---

## Known Limitations

- **Color contrast in PPTX** is checked only for text runs with explicitly set colors. Colors inherited from the slide master theme are not resolved.
- **veraPDF** must be separately installed (requires Java 11+). Without it, PDF checks are limited to pikepdf's structural inspection.
- **Crawling** is restricted to the same origin and path prefix as the start URL. Password-protected pages and pages requiring JavaScript-rendered navigation are not supported.
- **Excel merged cells** are flagged regardless of location. Merges in title/header areas outside the data range are commonly acceptable but are still reported for human review.
- **VPAT generation**, scheduled scans, and cross-scan trend reports are planned for a future phase.
