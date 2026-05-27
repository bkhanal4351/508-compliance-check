# EPA URL Checker

Internal tool for OFOM/OBP staff to detect dead, redirected, or suspicious URLs inside policy documents. Upload one or more files; get a prioritized report with export to Excel and CSV.

## Supported file types

`.docx` · `.pdf` · `.pptx` · `.xlsx` · `.txt` · `.html`

## Quick start

```bash
cd url_checker
pip install -r requirements.txt
streamlit run app.py
```

Open `http://localhost:8501` in your browser.

## Internal deployment

The app has no authentication layer in v1. Deploy behind an internal proxy (nginx, IIS, or SharePoint iframe) that enforces EPA network access. Streamlit can also be run as a Windows service using `nssm` if needed.

```bash
# Example: run on a specific port
streamlit run app.py --server.port 8502 --server.address 0.0.0.0
```

## Status tiers

| Tier | Meaning |
|------|---------|
| **Alive** | 2xx response, no soft-404 body markers, redirect (if any) ends at a real page |
| **Suspicious** | 200 OK but body looks like a 404; redirect lands at root homepage (link rot); 401/403; 5xx after retry |
| **Dead** | 404, 410, DNS failure, SSL error, connection refused, or timeout after retry |
| **Skipped** | `mailto:`, `tel:`, `javascript:`, anchor-only (`#section`), relative URLs, malformed URLs |

### How link rot is detected

A naive status-code check misses the most common real-world failure: a government agency removes a page and silently redirects the old URL to the homepage (returning HTTP 200). This tool catches it:

- If the original URL had a non-trivial path (e.g. `/resource-center/data/2019-report`) and the final URL after redirects is the root domain (`/`), the entry is marked **Suspicious** with the note "Cited content likely removed."
- First ~5 KB of each 200 response is scanned for soft-404 phrases ("page not found", "no longer available", etc.) and also marked **Suspicious**.

## Extending the tool

### Add a new file type

1. Create `extractors/myformat_extractor.py` subclassing `BaseExtractor` from `extractors/base.py`
2. Implement `extract() -> List[ExtractedUrl]`
3. Register the new suffix in `app.py → _get_extractor()`

### Add a new status-detection rule

Edit `validators/status_classifier.py`. All branching logic lives in `classify_url_result()`. Add a new condition and update `tests/test_status_classifier.py` with a corresponding test case.

## Running tests

```bash
cd url_checker
pytest tests/test_status_classifier.py -v
```

## Known limitations (v1)

- Scanned PDFs (image-only, no text layer) cannot have URLs extracted — a warning is shown
- Sites behind Cloudflare or Akamai WAFs may return 403 even with a browser User-Agent; these are marked Suspicious rather than Dead
- Very large documents (hundreds of pages) with thousands of URLs will be slower; increase the timeout and lower concurrent workers if needed
- No OCR support — scanned PDFs require a separate OCR step before upload
- No authentication support — cannot check URLs behind a login wall
