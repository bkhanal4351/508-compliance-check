# 508 / WCAG 2.1 AA Accessibility Scanner

Internal accessibility QA tool for scanning websites and documents against Section 508 and WCAG 2.1 AA standards.

---

## What it checks

| Input | Engine | Rules |
|---|---|---|
| URL (+ crawl) | Playwright + axe-core | Alt text, contrast, labels, headings, links, ARIA |
| PDF | pikepdf + veraPDF (optional) | Tagged structure, language, title, form fields, figures |
| DOCX | python-docx | Headings, images, tables, hyperlinks, lists, language |
| PPTX | python-pptx | Slide titles, shape alt text, reading order, color contrast |
| XLSX | openpyxl | Workbook title, sheet names, table structure, merged cells |
| Image | Pillow | Alt text presence and basic quality check |

> **AI-enhanced version:** The `AI-enabled` branch adds Groq/LLM-powered semantic checks for alt text quality, link text analysis, and heading structure evaluation.

---

## Prerequisites

### System dependencies

**Python 3.10+**
```bash
# macOS
brew install python@3.10

# Ubuntu/Debian
sudo apt install python3.10 python3.10-venv
```

**Playwright (Chromium)**
```bash
pip install playwright
playwright install chromium
```

**WeasyPrint** (PDF report export)
```bash
# macOS
brew install pango cairo

# Ubuntu/Debian
sudo apt install libpango-1.0-0 libcairo2
```

**veraPDF** *(optional — deep PDF/UA validation)*
Requires Java 11+.
1. Download from https://verapdf.org/home/#download
2. Extract and add the `verapdf` script to your `PATH`
3. Set `VERAPDF_PATH=/path/to/verapdf` in `.env` if not on PATH

---

## Setup

```bash
# 1. Clone / enter the project directory
cd 508-scanner

# 2. Install Python dependencies
pip install -r requirements.txt

# 3. Install Playwright browsers
playwright install chromium

# 4. Configure environment
cp .env.example .env
# Edit .env and add your GROQ_API_KEY (get one free at https://console.groq.com)
```

---

## Running the app

```bash
streamlit run app.py
```

Open http://localhost:8501 in your browser.

---

## Running tests

```bash
pytest tests/ -v
```

All tests run offline against local fixtures — no API keys or network needed.

---

## Architecture

```
508-scanner/
├── app.py                   # Streamlit UI
├── scanners/
│   ├── base.py              # Finding model, Severity enum
│   ├── web.py               # Playwright + axe-core web scanner
│   ├── pdf.py               # pikepdf + veraPDF PDF scanner
│   ├── docx_scanner.py      # python-docx DOCX scanner
│   ├── pptx_scanner.py      # python-pptx PPTX scanner
│   ├── xlsx_scanner.py      # openpyxl XLSX scanner
│   └── image.py             # Pillow image scanner
├── ai/
│   ├── client.py            # Groq API wrapper (retry, JSON parsing)
│   └── prompts.py           # Semantic check prompts + dispatcher
├── report/
│   ├── builder.py           # Aggregate, dedupe, sort findings
│   ├── pdf_export.py        # WeasyPrint PDF + CSV export
│   └── templates/
│       └── report.html      # Jinja2 report template
└── utils/
    ├── crawler.py           # BFS URL discovery (same-origin + path-prefix)
    └── wcag_refs.py         # WCAG SC / Section 508 reference mapping
```

Data flow:
```
URL / File  →  Scanner(s)  →  List[Finding]  →  build_report()  →  Streamlit UI
                    ↕                                                    ↓
              ai/prompts.py                                    PDF / CSV export
            (semantic checks)
```

---

## Environment variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `GROQ_API_KEY` | Yes (for AI checks) | — | Groq API key — get free at console.groq.com |
| `GROQ_MODEL` | No | `llama-3.3-70b-versatile` | Override the Groq model |
| `VERAPDF_PATH` | No | `verapdf` | Path to veraPDF CLI executable |

---

## Known limitations

- **veraPDF** requires Java 11+ and must be separately installed. The scanner degrades gracefully to pikepdf-only checks when veraPDF is absent.
- **Playwright** must be run outside of certain async contexts. If you hit "Playwright must be run in the main thread" errors when using Streamlit, the scanner will fall back to a subprocess.
- **Groq rate limits**: free-tier accounts have per-minute caps. The client retries with exponential backoff, but very large scans may slow down during semantic checks.
- **Color contrast** in PPTX is checked only for explicitly set text/background colors; theme colors inherited from the slide master are not resolved.
- **Large PDFs**: input capped at 50 MB in the UI. Very large tagged PDFs may be slow due to structure tree traversal.
- **Images**: vision-model alt text evaluation requires a Groq model with vision support. Falls back to deterministic checks if unavailable.
- **VPAT generation** and cross-scan trend dashboards are planned for a future phase.
- **Crawling** is limited to same-origin and same-path-prefix URLs — no authentication support.
