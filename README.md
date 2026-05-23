# 508 / WCAG 2.1 AA Accessibility Scanner — AI-Enhanced Build

Internal accessibility QA tool for scanning websites and documents against **Section 508** and **WCAG 2.1 AA** standards. This branch combines **deterministic rule-based checks** (axe-core, pikepdf, python-docx, etc.) with **AI-powered semantic checks** (Groq / llama-3.3-70b-versatile) for deeper analysis that rules alone cannot catch.

> **No-AI version:** The [`main`](../../tree/main) branch runs all deterministic checks without any API keys or LLM dependency.

---

## Standards Reference

### Section 508 (29 U.S.C. § 794d)
Federal law requiring federal agencies and contractors to make electronic and information technology accessible to people with disabilities. The **Revised 508 Standards (2018)** incorporate WCAG 2.0 Level AA by reference for web content (§ E205) and apply specific criteria for software (§ E207) and electronic documents (§ E205.4).

### WCAG 2.1 Level AA
The Web Content Accessibility Guidelines published by W3C/WAI, organized into four principles:

- **Perceivable** — information must be presentable in ways all users can perceive
- **Operable** — UI components must be operable by all users (keyboard, switch access, etc.)
- **Understandable** — information and UI operation must be understandable
- **Robust** — content must be interpretable by current and future assistive technologies

This tool targets **Level AA conformance**, which includes all Level A criteria.

---

## Why Both Deterministic and AI Checks?

Deterministic rules catch objective, binary failures: an image either has an `alt` attribute or it does not. But they cannot judge *quality*. Examples where deterministic tools pass but real users fail:

| Situation | Deterministic result | AI result |
|---|---|---|
| `alt="image"` on a chart of quarterly revenue | Pass (alt present) | Fail — "image" conveys nothing about the chart's data |
| `alt="chart.png"` | Pass (alt present) | Fail — filename is not a description |
| Link text "Read more" with no surrounding context | Pass (text present) | Fail — non-descriptive out of context |
| Headings H1, H2, H2, H3 with H2 titled "Section" twice | Structural pass | Fail — semantically illogical hierarchy |
| Error message "Invalid" on a date field | Pass (text present) | Fail — doesn't explain what is invalid or how to fix it |

The AI layer uses a prompted LLM as an accessibility expert evaluator, returning structured JSON (`passes`, `reasoning`, `suggested_fix`, `confidence`) that feeds directly into the findings pipeline.

---

## What Gets Checked and Why

### Web Pages (`scanners/web.py`)

Powered by **Playwright** (headless Chromium) + **axe-core 4.x** + **Groq semantic checks**.

**Deterministic checks (axe-core):**

| Check | WCAG SC | 508 Ref | How It Works |
|---|---|---|---|
| **Image alt text missing** | 1.1.1 | E205.4 | axe detects `<img>` with no `alt` attribute. Without alt text, screen readers announce the filename or skip the image entirely. |
| **Color contrast** | 1.4.3 | E207.2 | axe computes foreground/background luminance ratio using the WCAG relative luminance formula. Normal text requires >= 4.5:1; large text (18pt+ or 14pt bold) requires >= 3:1. |
| **Form label missing** | 1.3.1, 3.3.2 | E207.2 | axe checks that every `<input>`, `<select>`, `<textarea>` has an associated `<label>` via `for`/`id` pairing, `aria-label`, or `aria-labelledby`. Without a label, screen readers cannot identify the field's purpose. |
| **Heading order skipped** | 1.3.1 | E205.4 | axe flags heading level jumps (e.g., `<h1>` directly followed by `<h3>`). Skipped levels break the document outline screen reader users rely on for navigation. |
| **Generic link text** | 2.4.4 | E205.4 | axe flags links with empty or non-descriptive accessible names. Screen reader users often navigate by listing all links — "click here" provides no destination context. |
| **Document language missing** | 3.1.1 | E205.4 | axe checks the `lang` attribute on `<html>`. Without it, screen readers cannot select correct pronunciation rules. |
| **Keyboard trap** | 2.1.2 | E207.2 | axe verifies that keyboard focus is never trapped in a component without a documented escape mechanism. |
| **ARIA attribute invalid** | 4.1.2 | E207.2 | axe validates `role` and `aria-*` attributes against the ARIA spec — correct element, correct values, required attributes present. |
| **Page title missing** | 2.4.2 | E205.4 | axe checks for a non-empty `<title>`. Titles orient users in browser tabs and are announced on page load by screen readers. |
| **Skip navigation missing** | 2.4.1 | E205.4 | axe checks for a skip link that lets keyboard users bypass repeated navigation blocks. |
| **Landmark regions** | 1.3.1 | E205.4 | axe verifies all content is inside landmark regions (`<main>`, `<nav>`, `<header>`, etc.) for section-level screen reader navigation. |

**Semantic checks (Groq / llama-3.3-70b-versatile):**

After axe-core runs on each page, the scanner collects additional context and sends it to the LLM for qualitative evaluation.

| Check | WCAG SC | What the AI evaluates |
|---|---|---|
| **Alt text quality** | 1.1.1 | For every `<img>` that has a non-empty `alt`, the AI receives the alt text, the image `src`, and the nearest heading as context. It evaluates whether the alt text meaningfully describes the image's content and function — not just whether text is present. Flags generic values ("image", "photo", a filename) and text that is redundant with surrounding visible content. |
| **Link text quality** | 2.4.4 | For links whose text matches a list of likely non-descriptive phrases ("click here", "here", "read more", "learn more", etc.) or whose text equals the raw URL, the AI receives the link text, surrounding paragraph context, and the href. It evaluates whether the link is understandable out of context as a screen reader user would encounter it when navigating by links. |
| **Heading structure** | 1.3.1 | The full ordered heading outline (level + text) for the page is sent to the AI. It evaluates whether the hierarchy is logical, each heading is meaningful, and the structure reflects the actual content organization — beyond just checking for level skips. |
| **Error message clarity** | 3.3.1, 3.3.3 | For elements with `role="alert"`, `aria-live="assertive"`, or `aria-invalid="true"`, the AI evaluates whether the error message is specific, actionable, and tells the user both what went wrong and how to fix it. |

**Crawl behavior:** BFS from the start URL, same origin and path prefix only. Respects `robots.txt`. Rate-limited to 1 page/second. Configurable max depth and max pages.

---

### PDF Documents (`scanners/pdf.py`)

Uses **pikepdf** for structural introspection and optionally **veraPDF** for PDF/UA validation.

| Check | WCAG SC | 508 Ref | How It Works |
|---|---|---|---|
| **Untagged PDF** | 1.3.1 | E205.4 | pikepdf checks for `/StructTreeRoot` in the document catalog and `/MarkInfo /Marked = true`. A PDF without a tag tree has no semantic structure — screen readers cannot determine reading order, identify headings, or distinguish figures from body text. This is the most critical PDF accessibility failure and requires full remediation, not just individual rule fixes. |
| **Document language not set** | 3.1.1 | E205.4 | pikepdf checks for a `/Lang` entry (e.g., `en-US`) in the document catalog. Required for correct screen reader pronunciation. |
| **Document title not set** | 2.4.2 | E205.4 | pikepdf reads `/Info /Title` from document metadata. Displayed in browser tabs and announced on document open. |
| **Figure missing alt text** | 1.1.1 | E205.4 | pikepdf walks the structure tree for `Figure` tagged elements and checks for `/Alt`. Tagged PDFs: figures without `/Alt` are announced as "Figure" with no description. Also sends existing alt text to the AI for quality evaluation when enabled. |
| **Form field missing accessible name** | 1.3.1, 3.3.2 | E207.2 | pikepdf iterates AcroForm fields and checks for a `/TU` (tooltip) entry, which is the accessible name for PDF form fields. |
| **veraPDF PDF/UA failures** | Various | E205.4 | veraPDF validates against PDF/UA-1 (ISO 14289-1), the normative standard for accessible PDFs. Each failed rule maps to a clause reference. |

---

### Word Documents (`scanners/docx_scanner.py`)

Uses **python-docx** with direct OPC XML inspection. Semantic checks via Groq when enabled.

| Check | WCAG SC | 508 Ref | How It Works |
|---|---|---|---|
| **No heading styles** | 1.3.1 | E205.4 | Scans all paragraphs for `Heading 1`-`Heading 6` styles. No heading styles = no navigable structure for screen readers. |
| **Heading levels skipped** | 1.3.1 | E205.4 | Extracts heading outline in document order and checks for level jumps. A jump from H1 to H3 implies a missing H2 section, breaking hierarchical navigation. |
| **Fake headings** | 1.3.1 | E205.4 | Scans non-heading paragraphs for runs with bold + font size >= 14pt. Visually styled text is not exposed to assistive tech as a heading unless a Heading style is applied. |
| **Image alt text missing** | 1.1.1 | E205.4 | Inspects `<w:drawing>` XML for `<wp:docPr descr="">`. The `descr` attribute is the alt text for inline and floating images. Empty `descr` means screen readers announce the image name or skip it. |
| **Image alt text quality (AI)** | 1.1.1 | E205.4 | For images with non-empty `descr`, the AI evaluates quality using the same criteria as web alt text checks. Returns a finding if the alt text is generic, filename-based, or fails to convey the image's informational purpose. |
| **Table missing header row** | 1.3.1 | E205.4 | Checks for `<w:tblHeader/>` in the first row's `<w:trPr>`. Without a marked header row, screen readers cannot associate data cells with column headers. |
| **Generic hyperlink text** | 2.4.4 | E205.4 | Parses `<w:hyperlink>` elements and checks display text against non-descriptive phrases. |
| **Document language not set** | 3.1.1 | E205.4 | Checks `<w:lang>` in document settings XML. |
| **Manual list formatting** | 1.3.1 | E205.4 | Detects paragraphs using bullet characters or manual numbering instead of List styles. Manual lists are not exposed as list structures to assistive tech. |

---

### PowerPoint Presentations (`scanners/pptx_scanner.py`)

Uses **python-pptx** with XML inspection of the PPTX package.

| Check | WCAG SC | 508 Ref | How It Works |
|---|---|---|---|
| **Slide title missing or empty** | 2.4.6 | E205.4 | Checks each slide for a placeholder with `idx=0` (title placeholder) with non-empty text. Screen reader users rely on slide titles to identify and navigate between slides. |
| **Duplicate slide titles** | 2.4.6 | E205.4 | Compares all slide titles for exact duplicates. Users cannot distinguish slides by title when navigating. |
| **Shape missing alt text** | 1.1.1 | E205.4 | Inspects `<p:cNvPr>` XML for each picture, chart, text box, and group shape, reading the `descr` attribute. Shapes without `descr` are announced only by shape name ("Picture 3") with no content description. |
| **Reading order incorrect** | 1.3.2 | E205.4 | Checks that the title placeholder appears first in the shape tree (`<p:spTree>`). Screen readers follow shape tree order — content before the title is read before the slide is identified. |
| **Color contrast insufficient** | 1.4.3 | E207.2 | For text runs with explicitly set foreground colors, computes relative luminance of foreground and background using the WCAG formula. Flags text below 4.5:1 (normal) or 3:1 (large >= 18pt). |

---

### Excel Workbooks (`scanners/xlsx_scanner.py`)

Uses **openpyxl** plus direct ZIP/XML inspection of the XLSX package.

| Check | WCAG SC | 508 Ref | How It Works |
|---|---|---|---|
| **Workbook title not set** | 2.4.2 | E205.4 | Reads `docProps/core.xml` via `workbook.properties.title`. A meaningful title helps users identify the file. |
| **Default sheet names** | 2.4.6 | E205.4 | Checks sheet names against defaults ("Sheet1", "Sheet2", etc.). Descriptive sheet names are required for screen reader workbook navigation. |
| **Data not in an Excel Table** | 1.3.1 | E205.4 | For sheets with data (>= 3 rows, >= 2 columns) but no `ws.tables`, flags the data as unstructured. Excel Table objects expose header row semantics that screen readers announce as column headers. |
| **Table missing header row** | 1.3.1 | E205.4 | For defined Table objects, checks `headerRowCount`. Without a header row, column names cannot be associated with data cells. |
| **Merged cells** | 1.3.1 | E205.4 | Lists all merged cell ranges via `ws.merged_cells`. Merged cells break the row/column grid that screen readers use to navigate and announce cell position. |
| **Image or chart missing alt text** | 1.1.1 | E205.4 | Opens the XLSX ZIP archive, parses `xl/drawings/*.xml` for `<xdr:cNvPr>` elements, reads the `descr` attribute. |

---

### Standalone Images (`scanners/image.py`)

Uses **Pillow** for image validation + **Groq** for alt text quality evaluation.

| Check | WCAG SC | 508 Ref | How It Works |
|---|---|---|---|
| **No alt text provided** | 1.1.1 | E205.4 | Critical finding if an image is uploaded with no alt text. Images without text alternatives are completely inaccessible to blind users. |
| **Alt text quality (AI)** | 1.1.1 | E205.4 | When alt text is provided, the AI evaluates it against WCAG 1.1.1 quality criteria: does it describe the content and function? Is it concise (under 125 chars)? Does it avoid generic phrases and filenames? Where available, OCR-extracted text from the image is included as additional context for the model. |
| **Alt text generic (fallback)** | 1.1.1 | E205.4 | If the AI check is unavailable, a deterministic check flags alt text matching known-bad values ("image", "photo", "picture", "graphic", the filename itself) or under 3 characters. |

---

## AI Layer Architecture

### `ai/client.py` — Groq API Wrapper

- Reads `GROQ_API_KEY` from `.env`
- Default model: `llama-3.3-70b-versatile`
- All calls go through `complete_json(prompt, system)` which:
  1. Sends a chat completion request with `temperature=0.1` for consistent, low-creativity responses
  2. Strips markdown fences from the response before JSON parsing
  3. On JSON parse failure, retries once with an explicit "respond with raw JSON only" reminder turn
  4. On rate-limit or transient errors (429, 503, 502, timeout): retries with exponential backoff — 1s, 2s, 4s
  5. Returns `{}` on hard failure so callers degrade gracefully

### `ai/prompts.py` — Semantic Check Functions

Each function constructs a structured prompt with:
- A system message establishing the LLM as an accessibility expert
- Specific evaluation criteria drawn from WCAG guidance
- A required JSON response shape: `{"passes": bool, "reasoning": str, "suggested_fix": str|null, "confidence": float}`

Functions:

| Function | Input | What it evaluates |
|---|---|---|
| `check_alt_text_quality` | alt text, image context, nearby heading | Whether the alt text meaningfully describes the image's content and function in context |
| `check_link_text_quality` | link text, surrounding paragraph, href | Whether the link is understandable out of context by a screen reader user navigating by links |
| `check_heading_order` | ordered list of (level, text) pairs | Whether the heading hierarchy is logically consistent and each heading is meaningful |
| `check_error_message_clarity` | error message text, field context | Whether the error message identifies the problem and gives actionable correction guidance |
| `suggest_remediation` | full Finding object | Generates a 1-3 sentence concrete remediation a developer can act on immediately |
| `run_semantic_check` | check type + params dict | Dispatcher called by all scanners — routes to the above functions |

**Confidence scoring:** Each AI response includes a `confidence` float (0.0-1.0). Findings from semantic checks are always tagged `needs_human_review=True` because LLM judgment can be wrong — especially for images the model cannot see.

---

## Severity Levels

| Level | Meaning | Examples |
|---|---|---|
| **Critical** | Blocks assistive technology entirely | Untagged PDF, missing form label, image with no alt |
| **Serious** | Major barrier — content inaccessible to many users | Low color contrast, document language missing, slide title empty |
| **Moderate** | Significant friction — usable but difficult | Skipped heading level, generic link text (AI-confirmed), default sheet name |
| **Minor** | Best-practice gap — minor friction | Manual list formatting, duplicate slide title |

---

## Prerequisites

**Python 3.10+**

**Playwright (Chromium) — required for web scanning**

```bash
pip install playwright
playwright install chromium
```

**Groq API key — required for semantic checks**

Sign up free at [console.groq.com](https://console.groq.com). The free tier includes generous per-minute token limits sufficient for normal scan volumes.

**veraPDF — optional, for deep PDF/UA validation**

Requires Java 11+. Download from [verapdf.org](https://verapdf.org/home/#download), extract, and add to `PATH`. Without it, the scanner runs pikepdf-only PDF checks.

---

## Setup

```bash
# 1. Clone the repo and switch to this branch
git clone https://github.com/bkhanal4351/508-compliance-check.git
cd 508-compliance-check
git checkout AI-enabled

# 2. Install Python dependencies
pip install -r requirements.txt

# 3. Install Playwright browser
playwright install chromium

# 4. Configure environment
cp .env.example .env
# Edit .env — set GROQ_API_KEY (required for semantic checks)
# Set VERAPDF_PATH if veraPDF is not on PATH
```

---

## Running

```bash
streamlit run app.py
# Open http://localhost:8501
```

The sidebar shows a GROQ_API_KEY status indicator. If the key is missing, semantic checks are automatically disabled and the scanner falls back to deterministic-only mode.

---

## Running Tests

```bash
pytest tests/ -v
```

All 18 tests run fully offline — deterministic checks only, no API calls.

---

## Architecture

```
508-scanner/
├── app.py                    Streamlit UI — Groq status, scan runner, source filter
├── scanners/
│   ├── base.py               Finding model (Pydantic), Severity enum
│   ├── web.py                Playwright + axe-core + semantic checks via ai/prompts
│   ├── pdf.py                pikepdf + veraPDF + optional figure alt AI check
│   ├── docx_scanner.py       python-docx + OPC XML + image alt AI check
│   ├── pptx_scanner.py       python-pptx + shape tree XML (deterministic only)
│   ├── xlsx_scanner.py       openpyxl + drawing XML (deterministic only)
│   └── image.py              Pillow + Groq alt text quality evaluation
├── ai/
│   ├── client.py             Groq wrapper — complete_json(), retry, JSON parsing
│   └── prompts.py            Five semantic check functions + run_semantic_check dispatcher
├── report/
│   ├── builder.py            Dedupe (same rule+location), sort by severity
│   ├── pdf_export.py         fpdf2 PDF generation (Arial Unicode font, no native deps)
│   └── templates/            (reserved)
└── utils/
    ├── crawler.py            BFS; same-origin + path-prefix; robots.txt; 1 req/s
    └── wcag_refs.py          Rule ID -> (WCAG SC, 508 ref, default severity) map
```

**Data flow:**

```
URL / File
    |
    v
Scanner (web / pdf / docx / pptx / xlsx / image)
    |          |
    |          v
    |     ai/prompts.py  <-->  Groq API (llama-3.3-70b-versatile)
    |          |                  - check_alt_text_quality
    |          |                  - check_link_text_quality
    |          |                  - check_heading_order
    |          |                  - check_error_message_clarity
    v
List[Finding]  (deterministic + semantic, tagged by source)
    |
    v
report/builder.py  -->  dedupe + sort by severity
    |
    |-->  Streamlit UI (table, expanders, source filter: deterministic / semantic / both)
    |-->  PDF export (fpdf2)
    └-->  CSV export
```

---

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `GROQ_API_KEY` | Yes (for AI checks) | — | Groq API key — get free at console.groq.com |
| `GROQ_MODEL` | No | `llama-3.3-70b-versatile` | Override the Groq model (e.g., for a newer release) |
| `VERAPDF_PATH` | No | `verapdf` | Path to veraPDF CLI if not on PATH |

---

## Known Limitations

- **Semantic checks require GROQ_API_KEY.** Without it, the scanner silently falls back to deterministic-only mode. The sidebar shows the key status.
- **Groq free-tier rate limits** (per-minute token caps) may slow large scans. The client retries with exponential backoff but a scan with many images and links will pace itself.
- **The AI cannot see images** — alt text quality for web images is evaluated using the `src` URL, nearby heading, and alt text string only, not the actual image content. Confidence scores reflect this uncertainty.
- **Color contrast in PPTX** is checked only for text runs with explicitly set colors. Colors inherited from the slide master theme are not resolved.
- **veraPDF** must be separately installed (requires Java 11+). Without it, PDF checks are limited to pikepdf structural inspection.
- **Crawling** is restricted to the same origin and path prefix as the start URL. Password-protected pages are not supported.
- **VPAT generation**, scheduled scans, and cross-scan trend reports are planned for a future phase.
