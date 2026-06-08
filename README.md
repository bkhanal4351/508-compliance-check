# EPA Compliance Tools — 508 Scanner + URL Checker

React + FastAPI full-stack rewrite. Two tools in one tabbed interface:

- **508 Compliance Scanner** — checks web pages and documents against Section 508 / WCAG 2.1 AA
- **URL Checker** — finds dead, suspicious, and broken links inside uploaded policy documents

> **Branch guide:**
>
> - **`508-url-react`** ← _you are here_ — React + FastAPI (this rewrite)
> - **`508-and-docURL-check`** — original Streamlit version
> - **`main`** — 508 scanner only (Streamlit, no URL checker)

---

## Quick start

**Requirements:** Python 3.10+, Node.js 18+

```bash
# Terminal 1 — backend
cd backend
python3.10 -m uvicorn main:app --reload --port 8000

# Terminal 2 — frontend
cd frontend
npm install        # first time only
npm run dev        # → http://localhost:5173
```

> For web URL scanning you also need the Playwright browser installed once:
> `python3.10 -m playwright install chromium`

Visit `http://localhost:8000/docs` for the interactive API explorer.

---

## Project structure

```text
508-scanner/
│
├── backend/                          All server-side code lives here
│   ├── main.py                         FastAPI app: CORS config, route registration
│   ├── requirements.txt                All Python dependencies
│   ├── routers/
│   │   ├── scanner_508.py              HTTP routes for the 508 scanner
│   │   └── url_checker.py              HTTP routes for the URL checker
│   │
│   ├── scanners/                       508 scanner — core domain logic
│   │   ├── base.py                       Finding model (Pydantic) + Severity enum
│   │   ├── web.py                        Web scanner: Playwright + axe-core
│   │   ├── pdf.py                        PDF scanner: pikepdf + optional veraPDF
│   │   ├── docx_scanner.py               DOCX scanner: python-docx + XML
│   │   ├── pptx_scanner.py               PPTX scanner: python-pptx + shape tree
│   │   ├── xlsx_scanner.py               XLSX scanner: openpyxl + drawing XML
│   │   ├── image.py                      Image scanner: Pillow + alt text checks
│   │   └── axe.min.js                    Bundled axe-core 4.x (injected into pages)
│   │
│   ├── report/                         508 report builder
│   │   ├── builder.py                    Deduplication + sort by severity
│   │   └── pdf_export.py                 PDF (fpdf2) + CSV export
│   │
│   ├── utils/                          508 scanner utilities
│   │   ├── crawler.py                    BFS crawler: same-origin, robots.txt, 1 req/s
│   │   └── wcag_refs.py                  Rule ID → WCAG SC / 508 ref / severity map
│   │
│   └── url_checker/                    URL checker — core domain logic
│       ├── extractors/                   Extract URLs from documents
│       │   ├── base.py                     Shared data models (ExtractedUrl, CheckResult)
│       │   ├── docx_extractor.py
│       │   ├── pdf_extractor.py
│       │   ├── pptx_extractor.py
│       │   ├── xlsx_extractor.py
│       │   └── text_extractor.py
│       ├── validators/                   Check each URL via HTTP
│       │   ├── url_checker.py              Async HTTP engine (httpx)
│       │   ├── status_classifier.py        Dead / Suspicious / Alive / Skipped logic
│       │   └── wayback.py                  Archive.org snapshot lookup for dead URLs
│       ├── exporters/                    Export results
│       │   ├── csv_exporter.py
│       │   └── excel_exporter.py
│       └── url_checker_utils/            Shared constants + URL normalisation
│           ├── constants.py
│           └── url_utils.py
│
├── frontend/                         All browser-side code lives here
│   ├── public/epa_logo.png
│   ├── src/
│   │   ├── App.jsx                     Root: tab bar + tab switching
│   │   ├── App.css                     All styles
│   │   ├── api/
│   │   │   ├── scanner508.js           API calls for the 508 scanner
│   │   │   └── urlChecker.js           API calls for the URL checker
│   │   └── components/
│   │       ├── Header.jsx              EPA blue banner (shared)
│   │       ├── FileDropZone.jsx        Drag-and-drop uploader (shared)
│   │       ├── SummaryCards.jsx        Coloured count boxes (shared)
│   │       ├── StatusBadge.jsx         Severity / tier pill (shared)
│   │       ├── scanner-508/
│   │       │   ├── Scanner508Tab.jsx   Tab 1 UI + scan form
│   │       │   └── Findings508Table.jsx  Filterable findings table
│   │       └── url-checker/
│   │           ├── UrlCheckerTab.jsx   Tab 2 UI + settings form
│   │           └── UrlResultsTable.jsx   Filterable URL results table
│   ├── package.json
│   └── vite.config.js                  Dev server + /api proxy to :8000
│
└── tests/                            Offline test suite (18 tests, no network needed)
    ├── conftest.py                     Adds backend/ to sys.path for all tests
    ├── fixtures/                       Sample files: PDF, DOCX, PPTX, XLSX, HTML
    ├── test_pdf.py
    ├── test_docx.py
    ├── test_pptx.py
    ├── test_xlsx.py
    ├── test_web.py
    └── test_report.py
```

---

## API endpoints

### 508 Scanner — `backend/routers/scanner_508.py`

| Method | Path | What it does |
| --- | --- | --- |
| `POST` | `/api/scan/url` | Scan a live web page with Playwright + axe-core |
| `POST` | `/api/scan/document` | Upload a file (PDF/DOCX/PPTX/XLSX/image) and scan it |
| `POST` | `/api/scan/export/pdf` | Generate a formatted PDF report from findings |
| `POST` | `/api/scan/export/csv` | Generate a CSV from findings |

**Scan response shape:**

```json
{
  "findings":      [{ "id": "…", "severity": "Critical", "title": "…", "location": "…", … }],
  "summary":       { "Critical": 2, "Serious": 5, "Moderate": 3, "Minor": 1, "total": 11 },
  "scanned_at":    "2026-06-08T14:00:00+00:00",
  "deduped_count": 3
}
```

### URL Checker — `backend/routers/url_checker.py`

| Method | Path | What it does |
| --- | --- | --- |
| `POST` | `/api/urlcheck/check` | Upload documents, extract all URLs, check each one |
| `POST` | `/api/urlcheck/export/csv` | Download results as CSV |
| `POST` | `/api/urlcheck/export/excel` | Download results as Excel (.xlsx) |

**Check request** — `multipart/form-data`:

- `files` — one or more document files
- `timeout` (float, default `10`) — seconds per URL
- `max_workers` (int, default `20`) — parallel checks
- `fetch_titles` (bool, default `false`) — also read page `<title>` tags
- `retry` (bool, default `true`) — retry once on 5xx / 429 errors

**Check response shape:**

```json
{
  "results":  [{ "url": "…", "tier": "Dead", "status_code": 404, "reason": "…", … }],
  "summary":  { "Dead": 3, "Suspicious": 1, "Alive": 42, "Skipped": 5, "total": 51 },
  "warnings": ["report.docx: unsupported format (.odt)"]
}
```

URL tiers: **Dead** (404/timeout/DNS fail) · **Suspicious** (soft 404/silent redirect) · **Alive** (HTTP 2xx) · **Skipped** (mailto:, tel:, relative)

---

## What gets checked

### 508 Scanner

**Web pages** — Playwright loads the page in headless Chromium, axe-core runs in the browser context:

| Check | WCAG SC | What it detects |
| --- | --- | --- |
| Image alt text missing | 1.1.1 | `<img>` with no `alt` attribute |
| Color contrast | 1.4.3 | Foreground/background ratio below 4.5:1 (normal) or 3:1 (large text) |
| Form label missing | 1.3.1 | `<input>` / `<select>` / `<textarea>` with no associated label |
| Heading order skipped | 1.3.1 | Level jumps like H1 → H3 |
| Generic link text | 2.4.4 | Links whose text is "click here", "here", "read more", etc. |
| Document language missing | 3.1.1 | No `lang` attribute on `<html>` |
| Keyboard trap | 2.1.2 | Focus cannot escape a component via keyboard |
| ARIA attribute invalid | 4.1.2 | `role` / `aria-*` used incorrectly |
| Page title missing | 2.4.2 | Empty or absent `<title>` element |
| Skip navigation missing | 2.4.1 | No skip-to-main-content link |
| Landmark regions missing | 1.3.1 | Content not inside `<main>`, `<nav>`, etc. |

**PDF** (pikepdf + optional veraPDF): untagged structure, missing `/Lang`, missing `/Title`, figures without `/Alt`, form fields without tooltip names.

**DOCX** (python-docx + XML): no heading styles, skipped levels, fake bold headings, images without `descr`, tables without header row, generic hyperlinks, manual list formatting.

**PPTX** (python-pptx + XML): missing/duplicate slide titles, shapes without alt text, reading order, color contrast on explicit fills.

**XLSX** (openpyxl + ZIP/XML): default title, default sheet names, data not in an Excel Table, merged cells in data area, drawings without alt text.

**Images** (Pillow): generic or missing alt text.

### URL Checker

Extracts every URL (embedded hyperlinks + plain-text) from uploaded DOCX, PDF, PPTX, XLSX, TXT, or HTML files. For each unique URL:

1. Skips non-checkable schemes (mailto:, tel:, relative paths)
2. Fires an async HTTP GET with a fake browser User-Agent
3. Follows redirects, records the full chain
4. Reads up to 5 KB of the response body to detect soft 404s
5. For Dead URLs, queries the Wayback Machine for the last archived snapshot

---

## Severity levels (508 Scanner)

| Level | Meaning |
| --- | --- |
| **Critical** | Blocks assistive technology entirely — fix first |
| **Serious** | Major barrier — content inaccessible to many users |
| **Moderate** | Significant friction — usable but difficult |
| **Minor** | Best-practice gap — minor friction |

---

## Running tests

All 18 tests run fully offline against fixture files — no network, no API keys.

```bash
python3.10 -m pytest tests/ -v
```

---

## Environment variables

| Variable | Default | Description |
| --- | --- | --- |
| `VERAPDF_PATH` | `verapdf` | Path to the veraPDF CLI if it is not on `PATH`. veraPDF requires Java 11+ and must be downloaded separately from [verapdf.org](https://verapdf.org). Without it, PDF checks use pikepdf only. |

---

## Known limitations

- PPTX color contrast is checked only for runs with explicitly set colors; theme-inherited colors are not resolved.
- PDF checks are limited to pikepdf structural inspection unless veraPDF is installed.
- Web crawling is restricted to the same origin and path prefix as the start URL. JavaScript-rendered navigation and password-protected pages are not supported.
- Excel merged cells are flagged regardless of location; merges in title areas are common false positives.
