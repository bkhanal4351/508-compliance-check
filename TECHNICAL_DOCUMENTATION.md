# Section 508 / WCAG 2.1 AA Accessibility Scanner — Technical Documentation

---

## Table of Contents

1. [Purpose and Scope](#1-purpose-and-scope)
2. [Regulatory Standards Reference](#2-regulatory-standards-reference)
3. [Repository Structure](#3-repository-structure)
4. [Architecture Overview](#4-architecture-overview)
5. [How a Scan Works — End to End](#5-how-a-scan-works--end-to-end)
6. [Scanner Modules — What Each One Does](#6-scanner-modules--what-each-one-does)
   - 6.1 [Web Scanner](#61-web-scanner-scannerswebpy)
   - 6.2 [PDF Scanner](#62-pdf-scanner-scannerspdfpy)
   - 6.3 [DOCX Scanner](#63-docx-scanner-scannersdocx_scannerpy)
   - 6.4 [PPTX Scanner](#64-pptx-scanner-scannerspptx_scannerpy)
   - 6.5 [XLSX Scanner](#65-xlsx-scanner-scannersxlsx_scannerpy)
   - 6.6 [Image Scanner](#66-image-scanner-scannersimgpy)
7. [The Finding Data Model](#7-the-finding-data-model)
8. [Severity Levels — Definition and Meaning](#8-severity-levels--definition-and-meaning)
9. [WCAG Success Criteria Reference](#9-wcag-success-criteria-reference)
10. [Section 508 Reference Codes](#10-section-508-reference-codes)
11. [The Rule Registry (wcag_refs.py)](#11-the-rule-registry-wcag_refspy)
12. [Report Builder — Deduplication and Sorting](#12-report-builder--deduplication-and-sorting)
13. [PDF and CSV Export](#13-pdf-and-csv-export)
14. [How to Read the Results](#14-how-to-read-the-results)
15. [AI-Enabled Branch — Semantic Checks](#15-ai-enabled-branch--semantic-checks)
16. [Web Crawler (utils/crawler.py)](#16-web-crawler-utilscrawlerpy)
17. [Branches and What They Contain](#17-branches-and-what-they-contain)
18. [Running the App Locally](#18-running-the-app-locally)
19. [Limitations and Known Constraints](#19-limitations-and-known-constraints)

---

## 1. Purpose and Scope

This tool automates accessibility compliance checking against two overlapping regulatory frameworks:

- **Section 508 of the Rehabilitation Act (29 U.S.C. § 794d)** — U.S. federal law requiring federal agencies and contractors to make electronic and information technology accessible to people with disabilities. The Revised 508 Standards (effective January 2018) adopt WCAG 2.0 Level AA as the technical baseline for web content and electronic documents.
- **WCAG 2.1 Level AA** — The Web Content Accessibility Guidelines published by the W3C Web Accessibility Initiative. WCAG 2.1 adds 17 success criteria beyond WCAG 2.0, primarily addressing mobile accessibility and low-vision users.

The scanner covers six content types: websites, PDFs, Word documents (DOCX), PowerPoint presentations (PPTX), Excel workbooks (XLSX), and standalone images.

---

## 2. Regulatory Standards Reference

### WCAG 2.1 Four Principles (POUR)

Every WCAG success criterion falls under one of four principles:

| Principle | Meaning | Example rules covered |
|---|---|---|
| **Perceivable** | Information must be presentable to users in ways they can perceive | Alt text (1.1.1), color contrast (1.4.3), captions |
| **Operable** | UI components and navigation must be operable | Keyboard access (2.1.x), skip links (2.4.1), page titles (2.4.2) |
| **Understandable** | Information and UI operation must be understandable | Language of page (3.1.1), error identification (3.3.1) |
| **Robust** | Content must be robust enough to be interpreted by assistive technologies | ARIA validity (4.1.2), name/role/value (4.1.2) |

### Conformance Levels

| Level | Meaning |
|---|---|
| **A** | Minimum; must satisfy |
| **AA** | Standard legal threshold; what Section 508 (2018) requires |
| **AAA** | Enhanced; aspirational, not legally required |

This scanner targets **Level AA** exclusively, which is what federal agencies must meet.

### Revised Section 508 Standards (2018) — Key Subparts

| Code | What it covers |
|---|---|
| **E205.4** | Web content must conform to WCAG 2.0 Level AA (by reference) |
| **E207.2** | Software (including web apps) must conform to WCAG 2.0 Level AA |
| **E501–E504** | Support documentation and authoring tools |

When a finding cites **E205.4**, the violation is in a document or web page. When it cites **E207.2**, the violation is in interactive software behavior (keyboard traps, ARIA, color contrast in UI controls).

---

## 3. Repository Structure

```
508-scanner/
├── app.py                      # Streamlit UI — entry point
├── requirements.txt            # Python dependencies
├── scanners/
│   ├── base.py                 # Finding and Severity data models (Pydantic)
│   ├── web.py                  # Website scanner (Playwright + axe-core)
│   ├── pdf.py                  # PDF scanner (pikepdf + optional veraPDF)
│   ├── docx_scanner.py         # Word document scanner (python-docx)
│   ├── pptx_scanner.py         # PowerPoint scanner (python-pptx)
│   ├── xlsx_scanner.py         # Excel scanner (openpyxl)
│   ├── image.py                # Standalone image scanner (Pillow)
│   └── axe.min.js              # axe-core 4.x bundled JS (injected into pages)
├── utils/
│   ├── wcag_refs.py            # Rule ID → WCAG SC / 508 ref / severity mapping
│   └── crawler.py              # BFS web crawler with robots.txt support
├── report/
│   ├── builder.py              # Deduplication, sorting, summary generation
│   └── pdf_export.py           # PDF report generation (fpdf2) + CSV export
├── ai/
│   ├── client.py               # Groq API wrapper (AI-enabled branch only)
│   └── prompts.py              # Semantic check functions (AI-enabled branch only)
└── tests/
    ├── fixtures/               # Pre-built test files (PDF, DOCX, PPTX, XLSX)
    ├── test_pdf.py
    ├── test_docx.py
    ├── test_pptx.py
    ├── test_xlsx.py
    ├── test_report.py
    └── test_web.py
```

---

## 4. Architecture Overview

```
User (browser)
     │
     ▼
 app.py  (Streamlit)
     │
     ├── URL input ──────────────► utils/crawler.py  (discover URLs)
     │                                    │
     │                                    ▼
     │                             scanners/web.py
     │                          (Playwright headless Chromium)
     │                          (axe-core JS injected per page)
     │
     └── File upload ────────────► scanners/pdf.py
                                   scanners/docx_scanner.py
                                   scanners/pptx_scanner.py
                                   scanners/xlsx_scanner.py
                                   scanners/image.py
                                         │
                                         ▼
                                  List[Finding]  (scanners/base.py)
                                         │
                                         ▼
                                  report/builder.py
                                  (deduplicate + sort + summarize)
                                         │
                                         ▼
                               Streamlit results display
                               + report/pdf_export.py (download)
```

Every scanner produces a `list[Finding]`. The report builder consumes that list and produces the structured report dict that drives both the UI display and the export functions.

---

## 5. How a Scan Works — End to End

### Step 1 — Input

The user provides either:
- A URL (with crawl depth 0–3 and page limit 1–50)
- A file upload (PDF, DOCX, PPTX, XLSX, PNG/JPG/JPEG)

### Step 2 — Routing

`app.py` determines which scanner to invoke based on scan type or file extension:

```
.pdf   → scanners/pdf.py
.docx  → scanners/docx_scanner.py
.pptx  → scanners/pptx_scanner.py
.xlsx  → scanners/xlsx_scanner.py
.png / .jpg / .jpeg → scanners/image.py
URL    → utils/crawler.py → scanners/web.py
```

For file uploads, the file bytes are written to a temporary file on disk (using Python's `tempfile.NamedTemporaryFile`). The scanner receives the temporary file path. The temp file is deleted after scanning regardless of success or failure.

### Step 3 — Scanning

Each scanner runs a series of deterministic checks. These are rule-based: they inspect the file's structure, metadata, and content against known accessibility requirements. No network calls are made during document scanning.

For web scans, each discovered page is loaded in a headless Chromium browser (via Playwright), axe-core is injected and run, and the results are converted to Findings.

### Step 4 — Finding creation

Each check produces zero or more `Finding` objects. A Finding is a structured record of one specific accessibility issue at one specific location (see Section 7).

### Step 5 — Report building

`report/builder.py` receives the full flat list of Findings and:
1. **Deduplicates** — collapses findings with the same rule ID and location into one
2. **Sorts** — Critical → Serious → Moderate → Minor, then alphabetically by location within each severity
3. **Summarizes** — counts by severity, records total, timestamp, and scan target

### Step 6 — Display and export

The Streamlit UI displays the summary metrics, a filterable/searchable table, and per-finding detail expanders. The user can download a PDF report or CSV.

---

## 6. Scanner Modules — What Each One Does

### 6.1 Web Scanner (`scanners/web.py`)

**Technology:** Playwright (headless Chromium) + axe-core 4.x

**How it works:**

1. `utils/crawler.py` performs a breadth-first crawl starting from the given URL, respecting `robots.txt` and staying within the same domain scope and path prefix. It collects up to `max_pages` URLs at up to `max_depth` link-hops from the start.
2. For each URL, Playwright opens a new browser page and navigates to it (`wait_until="networkidle"` — waits until no network requests for 500ms, ensuring JS-rendered content is loaded).
3. `axe.min.js` is injected into the page DOM via `page.add_script_tag()`.
4. `axe.run()` is evaluated asynchronously and returns a JSON result with `violations`, `passes`, `incomplete`, and `inapplicable` arrays. Only `violations` are processed.
5. Each axe violation is converted to one Finding per affected DOM node (element).

**axe-core rule mapping:**

axe-core uses its own rule IDs. The scanner maps them to internal rule IDs before looking up WCAG/508 references:

| axe rule ID | Internal rule ID |
|---|---|
| `image-alt` | `image-alt-missing` |
| `color-contrast` | `color-contrast-insufficient` |
| `label` | `form-label-missing` |
| `heading-order` | `heading-order-skipped` |
| `link-name` | `link-text-generic` |
| `html-has-lang` | `language-of-page-missing` |
| `html-lang-valid` | `language-of-page-missing` |
| `keyboard` | `keyboard-trap` |
| `aria-required-attr` | `aria-label-invalid` |
| `aria-valid-attr` | `aria-label-invalid` |
| `aria-valid-attr-value` | `aria-label-invalid` |
| `button-name` | `form-label-missing` |
| `bypass` | `skip-link-missing` |
| `document-title` | `page-title-missing` |
| `region` | `landmark-missing` |

axe rules not in this map fall through with the axe rule ID as-is.

**Finding location format:** `Page N: css-selector > css-selector` where the CSS selector chain is derived from axe's `node.target` array.

**Rate limiting:** 1 second sleep between pages to avoid overloading the target server.

---

### 6.2 PDF Scanner (`scanners/pdf.py`)

**Technology:** pikepdf (Python PDF library) + optional veraPDF (external Java tool)

PDF accessibility relies on the PDF having a logical structure tree (tagged PDF). Without tags, screen readers cannot determine reading order, element roles, or alternative text.

**Checks performed:**

| Check | How it works | Rule ID | WCAG |
|---|---|---|---|
| **Tagged PDF** | Looks for `/StructTreeRoot` key in PDF root dictionary AND `/MarkInfo /Marked = true`. If either is missing, the PDF is untagged. | `pdf-untagged` | 1.3.1 |
| **Document language** | Reads `/Lang` from the PDF root dictionary. Must be a non-empty BCP-47 language tag (e.g., `en-US`). | `pdf-no-lang` | 3.1.1 |
| **Document title** | Reads `/Title` from the document info dictionary (`pdf.docinfo`). Must be non-empty. | `pdf-no-title` | 2.4.2 |
| **Form field names** | Iterates AcroForm `/Fields` array. Each field must have a `/TU` (tooltip) entry — this is the accessible name announced by screen readers. Fields with empty or missing `/TU` are flagged. | `pdf-form-field-no-name` | 1.3.1, 3.3.2 |
| **Figure alt text** | Recursively walks the structure tree starting at `/StructTreeRoot`. Any `Figure` element (`/S /Figure`) missing an `/Alt` attribute is flagged. Recursion depth is capped at 20 levels. | `pdf-figure-no-alt` | 1.1.1 |
| **veraPDF (optional)** | If `verapdf` is on the system PATH (requires Java 11+), the scanner runs `verapdf --format json --profile ua1` against the file and converts any FAILED rules to Findings. veraPDF performs deep PDF/UA-1 (ISO 14289-1) structural validation beyond what pikepdf checks. If veraPDF is not installed, this step is silently skipped. | `verapdf-*` | varies |

**Why pikepdf and not PyMuPDF or pdfminer?** pikepdf gives direct access to the PDF object model (the raw `/Root`, `/StructTreeRoot`, `/AcroForm` dictionary entries), which is what accessibility checking requires. Text-extraction libraries don't expose these structural elements.

---

### 6.3 DOCX Scanner (`scanners/docx_scanner.py`)

**Technology:** python-docx

Word documents are ZIP archives containing XML files. python-docx parses `document.xml` and exposes paragraphs, runs, tables, relationships, and settings as Python objects.

**Checks performed:**

#### Heading styles (`_check_headings`)
Iterates all paragraphs and collects those whose style name starts with `"Heading"`. Checks:
- If no headings found at all → flags `docx-no-heading`
- If first heading is not Heading 1 → flags `docx-heading-skipped`
- If any heading jumps more than one level (e.g., H1 → H3) → flags `docx-heading-skipped` per occurrence

The level number is extracted from the style name via regex `Heading (\d+)`.

#### Fake headings (`_check_fake_headings`)
Iterates non-heading paragraphs and inspects each run's font properties. If a run is bold AND has a font size ≥ 14pt, it looks visually like a heading but is not marked as one in the document structure. Screen readers will not announce it as a heading. Flags `docx-fake-heading`.

#### Image alt text (`_check_images`)
Searches each paragraph's raw XML for `w:drawing` elements (inline and floating images). For each drawing, looks for a `wp:docPr` element which holds the image's accessible name (`name` attribute) and description (`descr` attribute — this is the alt text). Flags `docx-image-alt-missing` if:
- No `docPr` element exists at all (image has no accessible metadata)
- `docPr` exists but `descr` is empty

#### Table headers (`_check_tables`)
For each table, inspects the first row's XML for `w:tblHeader` inside `w:trPr` (table row properties). This marker tells screen readers to treat the row as a header row and associate its cells with data cells in subsequent rows. Flags `docx-table-no-header` if the marker is absent.

#### Hyperlink text (`_check_links`)
Searches paragraph XML for `w:hyperlink` elements. Extracts the visible link text from nested `w:t` elements. If the text is empty or matches the generic list (`click here`, `here`, `read more`, `link`, `more`, `learn more`, `details`), flags `docx-link-text-generic`. The href is resolved through the document's relationship table (`doc.part.rels`).

#### Document language (`_check_language`)
Reads the document settings XML (`doc.settings.element`) and looks for a `w:lang` element. Flags `docx-no-language` if absent. Without a language, screen readers cannot select the correct speech synthesizer.

#### Fake lists (`_check_fake_lists`)
Checks paragraphs that are not using a List style but whose text begins with a manual bullet character (`•`, `‣`, `◦`, `⁃`, `∙`, `-`, `*`) or a number pattern (`1.`, `1)`, `2.`, etc.). Flags `docx-fake-list`. Manual characters are invisible to assistive technology list navigation.

---

### 6.4 PPTX Scanner (`scanners/pptx_scanner.py`)

**Technology:** python-pptx

PowerPoint files are also ZIP archives with XML. python-pptx exposes slides, shapes, text frames, and placeholder formats.

**Checks performed:**

#### Slide titles (`_check_slide_titles`)
For each slide, searches the shape tree for a placeholder with `idx == 0` (the title placeholder). Flags `pptx-slide-title-missing` if:
- No title placeholder exists on the slide
- The title placeholder exists but has empty text

Also flags `pptx-slide-title-duplicate` if the same title text appears on more than one slide — duplicate titles prevent users from identifying which slide they are on.

#### Shape alt text (`_check_shape_alt_text`)
For each shape on each slide that could represent visual content (shape types: auto_shape=1, chart=3, picture=5, text_box=6, picture=13, media=14), the scanner:
1. Skips title (idx=0) and body (idx=1) placeholders — these have their own text and don't need alt text
2. Looks for the `cNvPr` element inside the shape's `nvSpPr`, `nvPicPr`, `nvGraphicFramePr`, or `nvGrpSpPr` XML namespace, and reads the `descr` attribute (the alt text)
3. Falls back to `shape.alt_text` (python-pptx 0.6.23+ API)
4. Flags `pptx-shape-alt-missing` if the description is empty

#### Reading order (`_check_reading_order`)
The shape tree order in the XML is the order screen readers traverse content. The title should always be the first shape (index 0) so it is announced before any slide content. Flags `pptx-reading-order` if the title placeholder exists but is not at position 0 in the shape tree.

#### Color contrast (`_check_color_contrast`)
For each text run in each text frame on each slide:
1. Gets the run's foreground color from `run.font.color.rgb`
2. Gets the slide background color from `slide.background.fill.fore_color.rgb` (defaults to white `(255,255,255)` if unavailable)
3. Computes relative luminance for both colors using the WCAG formula: `0.2126R + 0.7152G + 0.0722B` after gamma correction
4. Computes contrast ratio: `(L_lighter + 0.05) / (L_darker + 0.05)`
5. Applies WCAG 1.4.3 thresholds: ≥ 4.5:1 for normal text, ≥ 3.0:1 for large text (≥ 18pt)
6. Flags `pptx-color-contrast` if the ratio is below threshold

---

### 6.5 XLSX Scanner (`scanners/xlsx_scanner.py`)

**Technology:** openpyxl + Python's built-in `zipfile` + `xml.etree.ElementTree`

Excel files are ZIP archives. openpyxl parses workbook structure; drawing XML (images, charts) is parsed directly from the ZIP because openpyxl does not expose alt text attributes.

**Checks performed:**

#### Workbook title (`_check_workbook_title`)
Reads `wb.properties.title` from the document core properties. Flags `xlsx-no-title` if empty or absent. Assistive technology uses the workbook title to identify the file.

#### Sheet names (`_check_sheet_names`)
Checks each worksheet's `.title` against the set `{"sheet1", "sheet2", "sheet3", "sheet4", "sheet5"}` (case-insensitive). Flags `xlsx-default-sheet-name` for matches. Default names give no indication of content.

#### Table structure (`_check_table_structure`)
For each worksheet:
- If `ws.tables` is empty AND the sheet has ≥ 3 rows and ≥ 2 columns of data, flags `xlsx-no-table-structure`. Screen readers treat Excel Tables as structured data with header semantics; raw ranges have no such semantics.
- If a Table exists but its `headerRowCount` is 0, flags `xlsx-no-table-structure` for that table. The header row is what screen readers announce as column names.

#### Merged cells (`_check_merged_cells`)
Iterates `ws.merged_cells.ranges`. Any merged cell range is flagged as `xlsx-merged-cells`. Merging breaks the row/column relationship that screen readers rely on for table navigation — a cell spanning three columns is announced as a single column, destroying the header-to-data association.

#### Image and chart alt text (`_check_image_alt_text`)
Opens the XLSX file as a ZIP archive and reads all files matching `xl/drawings/drawing*.xml`. Each drawing XML is parsed with ElementTree. The scanner searches for `xdr:cNvPr` elements (non-visual properties in the spreadsheet drawing namespace) and reads the `descr` attribute. An empty `descr` means the image or chart has no alt text. Flags `xlsx-image-alt-missing`.

---

### 6.6 Image Scanner (`scanners/image.py`)

**Technology:** Pillow (PIL)

Handles standalone image uploads (PNG, JPG, JPEG, GIF, WEBP). Images embedded in documents are handled by their respective document scanners.

**Checks performed:**

1. Opens the image with Pillow to validate it can be read and to record its dimensions and color mode.
2. If no alt text was provided by the user (via the optional text field in the UI), flags `standalone-image-alt-missing` immediately and returns.
3. If alt text was provided, on the `main` branch: checks against a hardcoded set of obviously-bad alt texts (`"image"`, `"photo"`, `"picture"`, `"graphic"`, `"icon"`, `"img"`, the filename stem, the filename) and flags `standalone-image-alt-poor` if matched or if the alt text is fewer than 3 characters.

On the `AI-enabled` branch, the scanner additionally runs a semantic quality check using the Groq LLM (see Section 15).

---

## 7. The Finding Data Model

Every issue the scanner identifies is represented as a `Finding` (defined in `scanners/base.py` as a Pydantic v2 model):

```
Finding
├── id           — 8-character UUID fragment (for UI keying, not globally unique)
├── rule         — Internal rule identifier (e.g., "image-alt-missing")
├── wcag_sc      — WCAG 2.1 Success Criterion number (e.g., "1.1.1")
├── sec508_ref   — Section 508 reference code (e.g., "E205.4")
├── severity     — One of: Critical, Serious, Moderate, Minor
├── title        — Short human-readable label
├── description  — Full explanation of the specific failure at this location
├── location     — Where in the document/page the issue was found
├── snippet      — Optional: the actual HTML/XML/text that is failing
├── suggested_fix— Optional: actionable remediation instruction
├── source       — "deterministic" (rule-based) or "semantic" (AI-evaluated)
└── needs_human_review — true for AI-generated findings only
```

**Why Pydantic?** Pydantic v2 validates field types at instantiation time, ensuring all scanners produce structurally consistent Findings regardless of which module created them. It also makes serialization (for CSV/JSON export) trivial.

---

## 8. Severity Levels — Definition and Meaning

| Severity | Color | Meaning | Action required |
|---|---|---|---|
| **Critical** | Red | Completely blocks access for users with disabilities. A screen reader user cannot use the feature at all. | Fix before launch. Cannot be deferred. |
| **Serious** | Orange | Significantly impairs access. Users may be able to work around it but with substantial difficulty. | Fix as soon as possible. Should block release. |
| **Moderate** | Blue | Creates friction or confusion. Users with disabilities can still access content but the experience is degraded. | Fix in the next sprint. Plan remediation. |
| **Minor** | Green | Best-practice violation. May affect some users but is a low-impact issue. | Fix when convenient. |

**Important:** Severity reflects the *impact on users*, not the ease of fixing. A missing alt text on a decorative image is Minor; missing alt text on an informational chart is Critical.

---

## 9. WCAG Success Criteria Reference

These are the success criteria this scanner checks against:

| SC | Name | Level | What it means |
|---|---|---|---|
| **1.1.1** | Non-text Content | A | All non-text content (images, charts, icons) must have a text alternative |
| **1.3.1** | Info and Relationships | A | Structure and relationships conveyed visually must also be conveyed programmatically (headings, tables, lists) |
| **1.3.2** | Meaningful Sequence | A | Reading order must be deterministic and logical |
| **1.4.3** | Contrast (Minimum) | AA | Text must have ≥ 4.5:1 contrast ratio (≥ 3:1 for large text) |
| **2.1.2** | No Keyboard Trap | A | Keyboard users must be able to move focus away from any component |
| **2.4.1** | Bypass Blocks | A | A skip navigation link must exist to bypass repetitive content |
| **2.4.2** | Page Titled | A | Pages and documents must have descriptive titles |
| **2.4.4** | Link Purpose (In Context) | AA | Link purpose must be clear from the link text or its context |
| **2.4.6** | Headings and Labels | AA | Headings and labels must be descriptive |
| **3.1.1** | Language of Page | A | The default human language of each page or document must be programmatically determinable |
| **3.3.2** | Labels or Instructions | A | Labels or instructions must be provided for user input |
| **4.1.2** | Name, Role, Value | A | All UI components must have names and roles that can be programmatically determined |

---

## 10. Section 508 Reference Codes

| Code | Full title | What types of issues map here |
|---|---|---|
| **E205.4** | Web content must conform to WCAG 2.0 Level AA | Documents (PDF, DOCX, PPTX, XLSX), web pages, images |
| **E207.2** | Software must conform to WCAG 2.0 Level AA | Interactive web app behaviors: keyboard traps, color contrast in controls, ARIA |

All findings in this scanner cite one of these two codes. E205.4 is the most common because it covers all content conformance requirements. E207.2 appears when the issue is specifically about interactive behavior (keyboard access, ARIA attribute validity, contrast in form controls).

---

## 11. The Rule Registry (`utils/wcag_refs.py`)

`wcag_refs.py` is a single flat dictionary (`_REFS`) mapping every internal rule ID to a 3-tuple:

```
rule_id → (wcag_sc, sec508_ref, default_severity)
```

The function `get_refs(rule_id)` looks up this dictionary. If a rule ID is not found (e.g., a veraPDF rule like `verapdf-6-3-4`), it returns the fallback `("Unknown", "Unknown", Severity.MODERATE)`.

Every scanner calls `get_refs()` when creating a Finding to populate `wcag_sc`, `sec508_ref`, and `severity` consistently. This means severity is defined centrally — changing the severity of a rule type requires editing only one line in `wcag_refs.py`.

**Full rule registry:**

| Rule ID | WCAG SC | 508 Ref | Default Severity |
|---|---|---|---|
| `image-alt-missing` | 1.1.1 | E205.4 | Critical |
| `image-alt-not-meaningful` | 1.1.1 | E205.4 | Serious |
| `color-contrast-insufficient` | 1.4.3 | E207.2 | Serious |
| `form-label-missing` | 1.3.1, 3.3.2 | E207.2 | Critical |
| `heading-order-skipped` | 1.3.1 | E205.4 | Moderate |
| `link-text-generic` | 2.4.4 | E205.4 | Moderate |
| `document-language-missing` | 3.1.1 | E205.4 | Serious |
| `pdf-untagged` | 1.3.1 | E205.4 | Critical |
| `pdf-no-title` | 2.4.2 | E205.4 | Moderate |
| `pdf-no-lang` | 3.1.1 | E205.4 | Serious |
| `pdf-no-mark-info` | 1.3.1 | E205.4 | Serious |
| `pdf-figure-no-alt` | 1.1.1 | E205.4 | Serious |
| `pdf-form-field-no-name` | 1.3.1, 3.3.2 | E207.2 | Critical |
| `table-header-missing` | 1.3.1 | E205.4 | Serious |
| `slide-title-missing` | 2.4.6 | E205.4 | Serious |
| `keyboard-trap` | 2.1.2 | E207.2 | Critical |
| `aria-label-invalid` | 4.1.2 | E207.2 | Serious |
| `page-title-missing` | 2.4.2 | E205.4 | Serious |
| `landmark-missing` | 1.3.1 | E205.4 | Moderate |
| `skip-link-missing` | 2.4.1 | E205.4 | Moderate |
| `focus-visible-missing` | 2.4.7 | E207.2 | Serious |
| `language-of-page-missing` | 3.1.1 | E205.4 | Serious |
| `docx-image-alt-missing` | 1.1.1 | E205.4 | Serious |
| `docx-no-heading` | 1.3.1 | E205.4 | Moderate |
| `docx-heading-skipped` | 1.3.1 | E205.4 | Moderate |
| `docx-fake-heading` | 1.3.1 | E205.4 | Moderate |
| `docx-table-no-header` | 1.3.1 | E205.4 | Serious |
| `docx-link-text-generic` | 2.4.4 | E205.4 | Moderate |
| `docx-no-language` | 3.1.1 | E205.4 | Serious |
| `docx-fake-list` | 1.3.1 | E205.4 | Minor |
| `pptx-slide-title-missing` | 2.4.6 | E205.4 | Serious |
| `pptx-slide-title-duplicate` | 2.4.6 | E205.4 | Minor |
| `pptx-shape-alt-missing` | 1.1.1 | E205.4 | Serious |
| `pptx-reading-order` | 1.3.2 | E205.4 | Moderate |
| `pptx-color-contrast` | 1.4.3 | E207.2 | Serious |
| `xlsx-no-title` | 2.4.2 | E205.4 | Moderate |
| `xlsx-default-sheet-name` | 2.4.6 | E205.4 | Minor |
| `xlsx-no-table-structure` | 1.3.1 | E205.4 | Moderate |
| `xlsx-merged-cells` | 1.3.1 | E205.4 | Moderate |
| `xlsx-image-alt-missing` | 1.1.1 | E205.4 | Serious |
| `standalone-image-alt-missing` | 1.1.1 | E205.4 | Critical |
| `standalone-image-alt-poor` | 1.1.1 | E205.4 | Serious |

---

## 12. Report Builder — Deduplication and Sorting

`report/builder.py` performs two operations before displaying results:

### Deduplication

The deduplication key is `"{rule_id}|{location}"`. If the same rule fires at the same location more than once (which can happen when a page is scanned multiple times, or when axe-core and a semantic check both flag the same element), only the first occurrence is kept. The count of collapsed duplicates is shown in the UI as a caption.

This is intentional: a developer remediating findings should not see the same issue listed twice at the same location.

### Sort order

Findings are sorted by:
1. Severity (Critical=0, Serious=1, Moderate=2, Minor=3) — most impactful issues first
2. Location (alphabetical) — within the same severity, grouped by where they appear

This means a Critical finding on Page 3 appears before a Serious finding on Page 1.

---

## 13. PDF and CSV Export

### PDF Report (`report/pdf_export.py`)

Generated using **fpdf2** (pure Python, no native library dependencies).

**Font handling:** The exporter attempts to register all four Arial variants (regular, bold, italic, bold-italic) from `/System/Library/Fonts/Supplemental/`. If any variant is missing (non-macOS systems), it falls back to fpdf2's built-in Helvetica.

**Text sanitization:** The `_clean()` function replaces Unicode characters outside the Latin-1 range (em dashes, smart quotes, ellipses, etc.) with ASCII equivalents before writing to the PDF. This prevents font encoding errors.

**Report structure:**
- Header on every page: scan target and timestamp
- Summary section: four severity metric cards
- Findings table: one row per finding with Severity, Rule, WCAG SC, 508 Ref, Location
- Detail blocks: for Critical and Serious findings, a full description and suggested fix block
- Footer on every page: page number

### CSV Export

`export_csv()` writes a flat CSV with columns: ID, Rule, Severity, WCAG SC, 508 Ref, Title, Description, Location, Snippet, Suggested Fix, Source, Needs Human Review.

The CSV uses Python's `csv.DictWriter` via an in-memory `StringIO` buffer and is returned as a string for Streamlit's `st.download_button`.

---

## 14. How to Read the Results

### Summary Metrics

The four metric cards at the top show counts by severity after deduplication. These are your headline numbers for reporting:

- **Critical** — Must fix before the content is published or distributed. A screen reader user hits a complete wall.
- **Serious** — Should fix before publication. May block or significantly impair access.
- **Moderate** — Plan to fix. Does not block access but degrades the experience.
- **Minor** — Fix when convenient. Best-practice violations.

If the deduplication caption appears (e.g., "3 duplicate findings collapsed"), it means the raw scanner output contained 3 repeated findings that were merged.

### Findings Table

Each row is one unique accessibility issue. Columns:

| Column | What it tells you |
|---|---|
| **Severity** | How badly this impacts users |
| **Title** | Short label for the type of issue |
| **Location** | Where in the document or page — e.g., `Page 2: img[src='...']` or `Table 3, Row 1` or `Slide 4: shape 'Rectangle 12'` |
| **WCAG SC** | The WCAG 2.1 success criterion number this violates |
| **508 Ref** | The Section 508 subpart reference |
| **Rule** | The internal rule ID — use this for searching documentation or filing issues |

### Filtering

- **Severity filter** — multiselect; defaults to all four levels. Uncheck Minor and Moderate to focus only on blockers.
- **Source filter** (AI-enabled branch only) — `deterministic` (rule-based, high confidence) vs. `semantic` (AI-evaluated, needs human verification).
- **Search** — free-text search across title, rule ID, and location. Use this to find all findings related to a specific element or page.

### Finding Detail Expanders

Click any finding in the table to expand its detail panel. Each panel shows:

- **Rule** — internal ID in monospace
- **WCAG** — success criterion number
- **508** — subpart reference
- **Source** — deterministic or semantic
- **Needs human review** — appears only on semantic findings
- **Description** — full explanation of what is wrong and why it matters to users with disabilities
- **Code snippet** — the actual HTML, XML attribute, or text that is failing (shown in a code block)
- **Suggested fix** — actionable instruction for the developer or content author

### Reading Locations

Locations are formatted consistently per scanner:

| Scanner | Location format | Example |
|---|---|---|
| Web | `Page N: css-selector` | `Page 1: main > article > img` |
| PDF | Free text describing the PDF structure | `AcroForm field: First_Name` |
| DOCX | `Paragraph N: 'text...'` or `Table N, Row 1` | `Paragraph 7: 'Introduction'` |
| PPTX | `Slide N: shape 'name'` | `Slide 3: shape 'Chart 2'` |
| XLSX | `Sheet: 'name', Range: A1:C1` | `Sheet: 'Budget', Range: A1:C1` |
| Image | `Image: filename.png (WxH)` | `Image: chart.png (1200×800)` |

### What "Deterministic" vs. "Semantic" Means

**Deterministic** — The rule fires based on a binary structural condition. Either the `alt` attribute is present or it is not. Either the heading level skips or it does not. These findings have essentially zero false-positive rate — if the scanner says it's missing, it's missing.

**Semantic** (AI-enabled branch only) — The finding is based on the *quality* or *meaning* of content, evaluated by an LLM. For example: the `alt` attribute exists and is non-empty, but is it actually describing the image meaningfully? These findings have a confidence score and are marked "needs human review." A human should confirm before acting on them.

### What This Scanner Does NOT Catch

- **Manual review items:** Logical reading order in complex layouts, meaningful sequence of content, cognitive accessibility, time-based media (video captions/audio descriptions)
- **Dynamic content:** State changes triggered by JavaScript after page load (axe-core captures one point in time)
- **PDF remediation quality:** pikepdf can detect that tags are present but cannot assess whether the tags are correctly applied to the right elements
- **Color contrast in images:** Contrast within image files (e.g., text on a background in a JPEG) requires pixel-level analysis not performed here
- **Custom ARIA patterns:** Complex widgets (date pickers, data grids) require behavioral testing with actual screen readers

---

## 15. AI-Enabled Branch — Semantic Checks

The `AI-enabled` branch adds an AI layer on top of the deterministic scanners. This layer uses the **Groq API** with model `llama-3.3-70b-versatile` to evaluate content quality that cannot be checked by rules alone.

### Setup

```bash
export GROQ_API_KEY=your_key_here
```

The app shows a status indicator in the sidebar confirming whether the key is found. Without it, semantic checks are silently skipped — the deterministic checks still run normally.

### What the AI evaluates

| Check | Where it runs | What it asks the model |
|---|---|---|
| **Alt text quality** | Web, DOCX, Image | Is this alt text meaningful and accurate given the image context and nearby heading? |
| **Link text quality** | Web | Does this link text make sense out of context — could a screen reader user understand the destination? |
| **Heading structure** | Web | Does this heading outline reflect a logical document hierarchy? |
| **Error message clarity** | Web | Is this error message specific and actionable? |

### How it works (`ai/client.py`, `ai/prompts.py`)

1. The scanner collects the element and its context (e.g., `alt` text + image src + nearby heading text)
2. `run_semantic_check(check_type, kwargs)` dispatches to the appropriate prompt function
3. The prompt function formats a structured prompt and calls `complete_json(prompt, system)` in `ai/client.py`
4. `complete_json` sends the request to Groq, strips any markdown fencing from the response, parses JSON, and returns the result
5. On rate-limit or transient errors, it retries up to 3 times with exponential backoff (1s, 2s, 4s)
6. If the model returns anything other than valid JSON, it retries once with a "raw JSON only" reminder appended

Every AI check returns:
```json
{
  "passes": true,
  "reasoning": "1-2 sentence explanation",
  "suggested_fix": "improved text or null",
  "confidence": 0.0-1.0
}
```

Findings from the AI layer have `source="semantic"` and `needs_human_review=True`.

---

## 16. Web Crawler (`utils/crawler.py`)

The crawler implements **breadth-first search** starting from the user-supplied URL.

**robots.txt compliance:**
- For `file://` URLs (used in testing), robots.txt is bypassed entirely
- For `http://` and `https://` URLs, the crawler fetches `robots.txt` from the root of the domain using Python's `urllib.robotparser.RobotFileParser`
- If robots.txt cannot be fetched (network error, 404, timeout), the crawler is permissive (allows all)
- The crawler identifies itself as `508-Scanner/1.0` in the User-Agent

**Scope restriction:**
The crawler stays within the same scheme, domain, and path prefix as the starting URL. Given start URL `https://example.com/docs/`, it will follow links to `https://example.com/docs/guide/` but not to `https://example.com/blog/` or `https://other.com/`. This prevents accidentally crawling a whole domain when only a section is intended.

**Link extraction:**
Uses BeautifulSoup to parse HTML and extract all `<a href="...">` tags. Skips `mailto:`, `javascript:`, `#fragment-only`, and `tel:` hrefs. Resolves relative URLs to absolute using `urljoin`.

**Rate limiting:** 200ms sleep between page fetches during crawl (separate from the 1-second sleep between Playwright page loads during scanning).

---

## 17. Branches and What They Contain

| File | `main` | `AI-enabled` |
|---|---|---|
| `ai/client.py` | Stub (no-op comment) | Groq API wrapper with retry logic |
| `ai/prompts.py` | Stub | 5 semantic check functions + dispatcher |
| `scanners/web.py` | Deterministic only | + `_collect_semantic_context()` + `_semantic_findings()` |
| `scanners/docx_scanner.py` | Deterministic only | + `_semantic_docx_findings()` |
| `scanners/image.py` | Hardcoded bad-alt detection | + Groq semantic quality check |
| `app.py` | No Groq references, 2-column filter | Groq status indicator, `use_semantic` flag, source filter |
| `requirements.txt` | `fpdf2>=2.7.9` (no Groq) | + `groq>=0.9.0` |
| `README.md` | Deterministic checks only | + AI layer documentation |

The PDF, PPTX, and XLSX scanners are identical between branches — they do not have semantic checks.

---

## 18. Running the App Locally

**Prerequisites:**
- Python 3.10+
- `pip install -r requirements.txt`
- For web scanning: `playwright install chromium`
- For PDF scanning with veraPDF: Java 11+ and veraPDF installed and on PATH
- For AI-enabled branch: `GROQ_API_KEY` environment variable

**Start the app:**
```bash
python3.10 -m streamlit run app.py --server.port 8501
```

Open `http://localhost:8501` in a browser.

**Run tests:**
```bash
python3.10 -m pytest tests/ -q
```
All 18 tests run offline against pre-built fixtures in `tests/fixtures/`. No network or API calls are required.

---

## 19. Limitations and Known Constraints

| Limitation | Detail |
|---|---|
| **No WCAG 2.2** | The scanner targets WCAG 2.1 AA. WCAG 2.2 adds 9 new success criteria (including 2.4.11 Focus Appearance) not covered here. |
| **Axe-core is a snapshot** | Web scanning captures one DOM state. Pages that change significantly after user interaction (login flows, SPA route changes) require multiple targeted scans. |
| **PDF tag quality** | pikepdf can verify tags exist but cannot assess whether the tag types, reading order, or heading levels within the tag tree are semantically correct. |
| **Color contrast in raster images** | Text embedded inside image files (JPEGs, PNGs) is not analyzed for contrast. |
| **No audio/video** | Captions, audio descriptions, and time-based media are not checked. |
| **PPTX contrast accuracy** | PPTX color contrast is checked per-run using explicit font colors. Inherited theme colors that are not explicitly set on the run may not be picked up. |
| **50 MB file limit** | File uploads are capped at 50 MB in the UI. |
| **macOS font paths** | The PDF exporter uses Arial from `/System/Library/Fonts/Supplemental/` (macOS-specific). On Linux/Windows, it falls back to Helvetica (Latin-1 only). |
| **veraPDF requires Java** | Deep PDF/UA-1 validation via veraPDF is optional and requires a separate Java 11+ installation. Without it, only pikepdf structural checks run. |
