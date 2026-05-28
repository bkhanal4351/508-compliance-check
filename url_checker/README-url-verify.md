# EPA URL Checker — Complete Guide

**Branch:** `url-verify`  
**Tool location:** `url_checker/`  
**Run command:** `streamlit run app.py`  
**Purpose:** Find every dead, broken, or suspicious hyperlink inside EPA policy documents before they are published or distributed.

---

## Table of Contents

1. [What the Tool Does](#1-what-the-tool-does)
2. [Who It Is For](#2-who-it-is-for)
3. [How to Install and Run](#3-how-to-install-and-run)
4. [How the Tool Works — End to End](#4-how-the-tool-works--end-to-end)
5. [Walking Through the Application UI](#5-walking-through-the-application-ui)
6. [Understanding the Status Tiers](#6-understanding-the-status-tiers)
7. [How Dead and Suspicious Links Are Detected](#7-how-dead-and-suspicious-links-are-detected)
8. [Reading the Results on Screen](#8-reading-the-results-on-screen)
9. [Reading the Exported Reports](#9-reading-the-exported-reports)
10. [What Each Report Column Means](#10-what-each-report-column-means)
11. [Wayback Machine — Archived Snapshots](#11-wayback-machine--archived-snapshots)
12. [Settings Explained](#12-settings-explained)
13. [Supported File Types and Their Limitations](#13-supported-file-types-and-their-limitations)
14. [Code Architecture — How the Modules Fit Together](#14-code-architecture--how-the-modules-fit-together)
15. [Known Limitations](#15-known-limitations)
16. [Extending the Tool](#16-extending-the-tool)

---

## 1. What the Tool Does

The EPA URL Checker is an internal web application that accepts uploaded documents, finds every URL inside them, visits each URL automatically, and produces a prioritized report telling staff which links are broken and why.

**The problem it solves:**  
Policy documents, guidance memos, and reports often contain dozens of hyperlinks to external websites, data portals, and other agency pages. Over time, those websites restructure, pages get deleted, or content moves — leaving the document pointing to broken links. Staff who manually click every link spend hours on a task that a tool can do in seconds.

**What it catches that a simple click-check does not:**

| Problem type | Example | How the tool catches it |
|---|---|---|
| Completely dead link | Domain no longer exists | DNS failure → marked Dead |
| Page deleted | Returns 404 Not Found | HTTP 404 → marked Dead |
| Deliberately removed | Returns 410 Gone | HTTP 410 → marked Dead |
| Silent redirect to homepage | Agency deleted old page, now all URLs redirect to their homepage with a 200 OK | Redirect-to-root detection → marked Suspicious |
| Soft 404 | Server returns 200 OK but the page says "Page Not Found" | Body text scan → marked Suspicious |
| SSL certificate problem | HTTPS site has an expired or invalid certificate | SSL error → marked Dead |
| Requires login | Page exists but returns 401 or 403 | Auth error → marked Suspicious |
| Archived / removed content | Returns 410 or redirect to archive notice | Classified Dead or Suspicious |

---

## 2. Who It Is For

- **OFOM/OBP staff** reviewing or publishing policy documents
- **Web coordinators** auditing existing EPA web content
- **Records managers** verifying that references in archived documents are still reachable
- Anyone who needs to validate that links in a Word, PDF, PowerPoint, Excel, or text file still work

No programming knowledge is required to use the tool.

---

## 3. How to Install and Run

### Prerequisites

- Python 3.9 or higher (Python 3.13 recommended)
- Terminal / command prompt access

### Setup

```bash
# From the repo root
cd url_checker

# Create a virtual environment (keeps dependencies isolated)
python3 -m venv .venv
source .venv/bin/activate        # Mac/Linux
# .venv\Scripts\activate         # Windows

# Install all required libraries
pip install -r requirements.txt
```

### Start the app

```bash
streamlit run app.py
```

Open `http://localhost:8501` in your browser. The app loads immediately — no login required.

To run on a custom port (useful when multiple tools are running):

```bash
streamlit run app.py --server.port 8502
```

### Run the test suite

```bash
cd url_checker
pytest tests/test_status_classifier.py -v
```

All 25 unit tests should pass. These tests verify the detection logic without making any real web requests.

---

## 4. How the Tool Works — End to End

The scan happens in two sequential phases. Here is exactly what happens after you click **Run Check**:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  PHASE 1 — EXTRACTION                                                        │
│                                                                               │
│  For each uploaded document:                                                  │
│    1. Save the upload to a temporary file on disk                             │
│    2. Open the file with the appropriate library (python-docx, PyMuPDF, etc.)│
│    3. Collect TWO types of URLs:                                              │
│       a. EMBEDDED hyperlinks — invisible links behind clickable text          │
│          (stored in the document's relationship/annotation data)              │
│       b. PLAIN-TEXT URLs — URLs literally typed into the document body        │
│          (found using a regular expression pattern)                           │
│    4. Record WHERE each URL was found (page number, paragraph, slide, etc.)  │
│                                                                               │
│  After all documents: deduplicate — if the same URL appears in 3 documents, │
│  check it only ONCE but remember all 3 locations.                            │
└────────────────────────┬────────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  PHASE 2 — CHECKING                                                          │
│                                                                               │
│  For each unique URL (up to 20 checked simultaneously):                       │
│    1. Decide if it should be SKIPPED (mailto:, tel:, relative path, etc.)    │
│    2. If not skipped, send an HTTP GET request — like a browser visiting it  │
│    3. Follow any redirects automatically (up to the final destination)        │
│    4. Read the first 5 KB of the response body                                │
│    5. Run 4 detection checks (see Section 7)                                 │
│    6. Assign a verdict: Alive / Suspicious / Dead / Skipped                  │
│    7. If Dead → ask the Wayback Machine for the last archived snapshot        │
│    8. If server error (5xx) or rate limit (429) → retry once automatically   │
│                                                                               │
│  All checks run concurrently (in parallel) using async Python + httpx.       │
│  A semaphore caps parallelism at 20 (default) to avoid overloading servers.  │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 5. Walking Through the Application UI

### Sidebar (left panel)

| Element | What it does |
|---|---|
| **Upload documents** | Drag and drop or click to select files. Multiple files are accepted at once. |
| **Timeout per URL (s)** | How many seconds to wait for a server to respond before giving up. Default: 10s. |
| **Concurrent checks** | How many URLs are checked simultaneously. Default: 20. Reduce if you see rate-limiting. |
| **Fetch page titles** | If on, reads the `<title>` tag from each page and shows it in the details panel. Slightly slower. |
| **Retry on failure** | If on, automatically retries once on timeout, 5xx errors, and 429 rate limits. |
| **▶ Run Check** | Starts the scan. Disabled until at least one file is uploaded. |
| **↺ Re-check Dead & Suspicious** | Appears after a scan completes. Re-visits only the failed URLs without re-scanning documents. Useful if you fixed a server issue and want to confirm. |

### Main area — before a scan

An instruction screen explaining how to use the tool.

### Main area — during a scan

A real-time progress bar shows which URL is being checked and how many have finished. Example: `Checking (14/47) https://www.epa.gov/some-page`

### Main area — after a scan

Five sections appear (described in detail in Section 8):

1. **Summary cards** — total counts by status tier
2. **Filter controls** — narrow the results by tier, file, URL text, or EPA scope
3. **Issues requiring attention** — red/orange callout boxes for every Dead/Suspicious URL
4. **All results table** — sortable, scrollable table of all filtered results
5. **URL Details** — collapsible per-URL panels with full technical data
6. **Export** — four download buttons

---

## 6. Understanding the Status Tiers

Every checked URL receives one of four verdicts:

### ✅ Alive

The URL is working correctly. The server responded with a success code (200–299), the page body does not contain "page not found" language, and if there were redirects, the final destination is a real page (not the site's homepage).

**Action required:** None.

---

### ⚠️ Suspicious

The URL reached a server, but something about the response suggests the content may be gone or inaccessible. A human reviewer should verify whether the link is still valid.

**Common reasons a URL is marked Suspicious:**

| Reason shown | What it means |
|---|---|
| `Body matches soft-404 pattern: "page not found"` | The server returned 200 OK, but the page text says the content is missing. The server is lying about the success. |
| `Original URL had a deep path; redirect lands at root domain. Cited content likely removed.` | The original URL pointed to a specific page (e.g. `/reports/2019/data`), but after following redirects, we ended up at the site's homepage. The specific content was removed. |
| `401 Unauthorized — page exists but requires authentication` | The page exists, but a login is required to view it. A reviewer with an account might be able to confirm it still works. |
| `403 Forbidden — page exists but access is blocked (may be bot protection)` | The server refused the request. This could be a login wall, a geographic restriction, or the site blocking automated checkers. The page may be fine for human visitors. |
| `503 Server Error after retry` | The server crashed or was overloaded when we checked. It may recover — use Re-check to verify later. |

**Action required:** Manually visit the URL in a browser and confirm whether the content is accessible. Update or remove the link if the content has moved.

---

### ❌ Dead

The URL is definitively broken. Either the server said the page does not exist, or we could not reach the server at all.

**Common reasons a URL is marked Dead:**

| Reason shown | What it means |
|---|---|
| `404 Not Found` | The server explicitly said this page does not exist. |
| `410 Gone — resource permanently removed` | The server confirmed the page existed but was deliberately deleted. |
| `DNS resolution failed — domain may not exist` | The domain name (e.g. `old-agency.gov`) no longer resolves to any server. The entire domain may be gone. |
| `SSL/TLS certificate error` | The site has an HTTPS certificate that is expired, self-signed, or doesn't match the domain. |
| `Connection refused by server` | The server is running but actively rejected the connection. |
| `Request timed out after retry` | The server did not respond within the timeout period, even after a retry. |

**Action required:** Remove or update the link. Check the Wayback Machine link (if shown) to find what the content used to say and where it may have moved.

---

### ⏭️ Skipped

The URL was not checked because it is not a standard HTTP/HTTPS web address.

**Types of skipped URLs:**

| Skip reason | Example |
|---|---|
| `mailto: link` | `mailto:contact@epa.gov` — an email address, not a web page |
| `tel: link` | `tel:+12025551234` — a phone number |
| `javascript: link` | `javascript:void(0)` — a script command, not a URL |
| `Relative URL` | `/other-page` — a path with no domain; only valid inside the original document's website |
| `Anchor-only link` | `#section-3` — jumps to a section within the same page |
| `Malformed URL` | A string that looks like a URL but cannot be parsed |

**Action required:** None for most. For relative URLs, consider whether the link should be updated to a full absolute URL.

---

## 7. How Dead and Suspicious Links Are Detected

### Check 1 — HTTP Status Code

The most straightforward check. The server's response code tells us directly:

- `200–299` → proceed to further checks (the server claims success)
- `404` → Dead (Not Found)
- `410` → Dead (Gone)
- `401` → Suspicious (requires login)
- `403` → Suspicious (access blocked)
- `5xx` → Suspicious (server error, retry once first)

### Check 2 — Soft 404 Body Scan

Some servers always return HTTP 200 even for missing pages ("soft 404s"). To catch this, the tool reads the first 5 KB of every 200 response and scans for phrases like:

- "page not found"
- "404"
- "no longer available"
- "has been removed"
- "content not found"
- "does not exist"
- "page has moved"
- "this page cannot be found"

If any of these phrases are detected in the body text, the URL is marked **Suspicious** even though the status code was 200.

### Check 3 — Redirect-to-Root (Link Rot) Detection

This is the most subtle and important check. It catches the most common real-world failure mode:

1. An agency publishes a report at `https://agency.gov/publications/2019/annual-report`
2. A few years later, the agency redesigns their website and deletes that page
3. They set up a blanket redirect so ALL old URLs point to their homepage (`https://agency.gov/`)
4. The homepage returns HTTP 200 — so a naive checker says "Alive"
5. But the actual content is gone

The tool catches this by comparing the path of the original URL to the path of the final destination after redirects:

- **Original path:** `/publications/2019/annual-report` (a real page path)
- **Final path:** `` (empty — the root homepage)

If the original URL had a meaningful path and the final destination is the root domain, the URL is marked **Suspicious** with the note "Cited content likely removed."

### Check 4 — Network-Level Failures

Before any of the above checks can run, the tool must successfully connect to the server. If the connection itself fails:

- **DNS failure** → The domain name doesn't resolve to any IP address (domain may not exist) → Dead
- **SSL error** → Certificate problem → Dead
- **Connection refused** → Server running but rejecting connections → Dead
- **Timeout** → Server never responded → Dead (after one retry)

---

## 8. Reading the Results on Screen

### Summary Cards

```
Total URLs   ✅ Alive   ⚠️ Suspicious   ❌ Dead   ⏭️ Skipped
    47           38           5              3          1
```

Read this as your quick health snapshot. In a well-maintained document, you should expect Alive to dominate and Dead/Suspicious to be low single digits.

### Filter Controls

Four filters let you narrow the view:

- **Status** — show only Dead, only Suspicious, only Alive, or any combination
- **Source file** — if you uploaded multiple documents, filter to one file
- **URL contains** — search for a specific domain or keyword within URLs
- **Scope** — "All", "EPA Internal only" (*.epa.gov domains), or "External only"

Filters update the count shown ("Showing 8 of 47 results") and apply to all three result sections below.

### Issues Requiring Attention (Red/Orange Callout Boxes)

Every Dead or Suspicious URL appears as a colored alert box without requiring any clicking:

```
❌ Dead  `404`  |  https://example.gov/old-report

Why: 404 Not Found

Archive: View last known snapshot (Mar 12, 2022)

Where in document: policy_doc.docx — Paragraph 14

Context: …consult the full guidance at https://example.gov/old-report for additional…
```

Each callout tells you:

| Field | Meaning |
|---|---|
| **Dead / Suspicious** | The verdict |
| **HTTP code** | The numeric server response (or N/A if no response) |
| **URL** | The link that failed |
| **Why** | Plain-English explanation of the failure |
| **Archive** | Wayback Machine link (Dead URLs only) — last known working copy |
| **Where in document** | Which file and which location (page, paragraph, slide) |
| **Context** | The surrounding sentence or phrase from the document |

### All Results Table

A scrollable, sortable table showing every filtered URL with the most important columns. Click any column header to sort. URLs are clickable — clicking opens the page in a new browser tab.

### URL Details (Expandable Panels)

Click any panel to expand it. The title already shows the tier, URL, and reason so you can scan without expanding:

```
❌ Dead  https://example.gov/old-report  — 404 Not Found
```

Inside the expanded panel, two columns show:

**Left column:**
- Full URL and final URL (if redirected)
- Status and HTTP code
- Why it was flagged
- Wayback Machine snapshot link and date
- Response time in milliseconds
- Whether it is an EPA internal URL
- Page title (if "Fetch page titles" was enabled)
- When the check was performed

**Right column:**
- Full redirect chain (every hop with status codes)
- Every location in every document where this URL appeared (file name, page/paragraph, link type, context snippet)

---

## 9. Reading the Exported Reports

Four download buttons appear at the bottom of the results page:

| Button | Contents | Format | When to use |
|---|---|---|---|
| **⬇️ All results (.xlsx)** | Every URL regardless of status | Excel with Summary chart + Details tab | Full audit record |
| **⬇️ All results (.csv)** | Every URL regardless of status | Plain CSV | Import into databases / other tools |
| **⬇️ Issues only (.xlsx)** | Dead and Suspicious only | Excel with Summary chart + Details tab | Share with staff who need to fix links |
| **⬇️ Issues only (.csv)** | Dead and Suspicious only | Plain CSV | Quick action list |

The **Issues only** buttons are highlighted in blue — these are the most useful for day-to-day link maintenance.

### Excel Workbook Structure

The Excel export has two tabs:

**Summary tab:**
- Report title, generation timestamp, files scanned, settings used
- Stats table: count of Dead / Suspicious / Alive / Skipped
- Bar chart visualizing the breakdown

**Details tab:**
- One row per unique URL
- Rows sorted worst-first (Dead → Suspicious → Alive → Skipped)
- Status column is color-coded (red for Dead, orange for Suspicious, green for Alive, grey for Skipped)
- Original URL, Final URL, and Wayback Snapshot are clickable hyperlinks
- First row is frozen (stays visible when scrolling)

---

## 10. What Each Report Column Means

| Column | Description | Example |
|---|---|---|
| **Status** | The verdict for this URL | `Dead` |
| **Original URL** | The URL exactly as it appeared in the document | `http://www.epa.gov/old-page` |
| **Final URL** | Where we actually ended up after all redirects (blank if no redirect) | `https://www.epa.gov/` |
| **HTTP Code** | The last HTTP response code received (blank if connection failed) | `404` |
| **Source File** | The name of the uploaded document that contained this URL | `policy_guidance.docx` |
| **Location** | Where in the document the URL was found | `Paragraph 14` / `Page 3` / `Slide 7` |
| **Context** | Up to 100 characters of surrounding text from the document | `…see the full report at https://… for details…` |
| **Response Time (ms)** | How long the server took to respond, in milliseconds | `342` |
| **Redirects** | How many redirect hops happened before reaching the final page | `2` |
| **Reason** | Plain-English explanation of why the URL was flagged (blank for Alive) | `404 Not Found` |
| **Wayback Snapshot** | Clickable link to the last archived copy on the Wayback Machine (Dead URLs only) | `View snapshot` |
| **Wayback Date** | Human-readable date of the Wayback snapshot | `Mar 12, 2022` |
| **Redirect Chain** | The full sequence of redirects: each status code and URL | `301 http://old.gov → 302 https://new.gov` |
| **EPA Internal** | Whether the URL is on an *.epa.gov domain | `Yes` / `No` |
| **Checked At** | UTC timestamp of when the URL was checked | `2024-07-15 13:45 UTC` |

---

## 11. Wayback Machine — Archived Snapshots

For every URL classified as **Dead**, the tool automatically queries the [Internet Archive Wayback Machine](https://web.archive.org) to find the most recent archived copy of that page.

If a snapshot exists, you will see:
- A "View last known snapshot (Month DD, YYYY)" link in the on-screen callout box
- A "View snapshot" hyperlink in the Wayback Snapshot column of the Excel/CSV export
- The date of the snapshot in the Wayback Date column

**How to use the snapshot:**
1. Click the Wayback link to see what the page contained when it was last archived
2. Use that content to find where the information may have moved (look for new URLs on the new site)
3. Update the document to point to the current location, or cite the archived copy directly

**If no snapshot is found:** The page may have existed only briefly, been blocked from archiving (via `robots.txt`), or never been crawled by the Internet Archive.

---

## 12. Settings Explained

### Timeout per URL (5–30 seconds, default: 10)

How long to wait for a server to respond before declaring a timeout. A URL that takes longer than this is retried once (if retry is on) and then marked Dead.

- **Increase if:** You are checking slow government servers or large file downloads
- **Decrease if:** You want faster scans and are willing to accept more timeouts

### Concurrent checks (5–50, default: 20)

How many URLs are checked simultaneously (in parallel). Think of it as "how many staff members are calling different phone numbers at the same time."

- **Increase if:** You have many URLs and a fast internet connection and want the scan to finish faster
- **Decrease if:** You are seeing many 429 (rate limit) or 403 (forbidden) responses — some servers block rapid automated requests

### Fetch page titles (default: off)

When enabled, the tool reads the `<title>` HTML tag from each successfully loaded page and shows it in the URL Details panel. This helps confirm that you are looking at the right page after redirects.

Adds a small amount of overhead per URL because it must read more of the page body.

### Retry on failure (default: on)

When enabled, the tool makes one additional attempt on:
- Timeouts
- 5xx server errors (the server crashed or is overloaded)
- 429 responses (the server is asking us to slow down)

After the retry, if the error persists, the URL is classified Dead or Suspicious as appropriate.

---

## 13. Supported File Types and Their Limitations

| File type | Extension | Embedded links extracted | Plain-text URLs extracted | Notes |
|---|---|---|---|---|
| Word document | `.docx` | ✅ From relationship table + headers/footers | ✅ From all paragraphs and table cells | Must be a modern .docx, not old .doc format |
| PDF | `.pdf` | ✅ From annotation layer | ✅ From text layer | Scanned PDFs (image-only) will show a warning — no URLs can be extracted without OCR |
| PowerPoint | `.pptx` | ✅ From run hyperlinks | ✅ From all text frames | Slide notes are not currently scanned |
| Excel | `.xlsx` | ✅ From cell hyperlinks | ✅ From cell values | Formula results are not evaluated; only typed text is scanned |
| Plain text | `.txt` | — | ✅ Line by line | — |
| HTML | `.html` / `.htm` | — | ✅ Line by line (raw source) | Full HTML parsing is not done; `href` values in `<a>` tags are found because they look like URLs |

**Maximum file size:** 50 MB per file.

---

## 14. Code Architecture — How the Modules Fit Together

```
url_checker/
│
├── app.py                          ← Streamlit web UI: all user interaction
│
├── extractors/
│   ├── base.py                     ← Data structures: UrlLocation, ExtractedUrl, CheckResult, BaseExtractor
│   ├── docx_extractor.py           ← Reads .docx files (python-docx)
│   ├── pdf_extractor.py            ← Reads .pdf files (PyMuPDF / fitz)
│   ├── pptx_extractor.py           ← Reads .pptx files (python-pptx)
│   ├── xlsx_extractor.py           ← Reads .xlsx files (openpyxl)
│   └── text_extractor.py           ← Reads .txt, .html, .htm files (built-in)
│
├── validators/
│   ├── url_checker.py              ← Async HTTP engine: group_by_url(), check_urls()
│   ├── status_classifier.py        ← Pure classification logic: classify_url_result()
│   └── wayback.py                  ← Wayback Machine API client: fetch_wayback()
│
├── exporters/
│   ├── excel_exporter.py           ← Builds .xlsx workbook with Summary + Details tabs
│   └── csv_exporter.py             ← Builds .csv file, sorted by severity
│
├── utils/
│   ├── constants.py                ← Shared settings: timeouts, patterns, colours, limits
│   └── url_utils.py                ← URL helpers: extract_plain_urls(), normalize_url(), classify_skip_reason()
│
├── tests/
│   └── test_status_classifier.py   ← 25 unit tests for the classification logic
│
└── requirements.txt                ← All Python dependencies
```

### Data flow

```
Uploaded file
    │
    ▼
Extractor (docx / pdf / pptx / xlsx / text)
    │
    ▼  List[ExtractedUrl]
    │  (url, source_file, location, context, link_type)
    │
    ▼
group_by_url()   ← deduplicates; maps canonical_url → List[UrlLocation]
    │
    ▼  Dict[str, List[UrlLocation]]
    │
    ▼
check_urls()     ← synchronous entry point; runs async engine in a thread
    │
    ├── classify_skip_reason()  → skip immediately if mailto/tel/relative/etc.
    │
    └── _do_request()           → HTTP GET with httpx.AsyncClient
            │
            ├── collect redirect_chain, status_code, final_url, body_preview
            ├── classify_url_result()  → (tier, reason)
            └── fetch_wayback()        → (snapshot_url, snapshot_date) if Dead
    │
    ▼  List[CheckResult]
    │
    ├── Streamlit UI display
    ├── export_excel() → .xlsx bytes
    └── export_csv()   → .csv bytes
```

### Key design decisions

**Why async?**  
Checking URLs is network-bound: the code spends most of its time waiting for servers to respond. Async Python lets 20 waits happen simultaneously instead of sequentially, making the scan ~20× faster than a simple for-loop.

**Why a separate thread for the async engine?**  
Streamlit runs its own internal async event loop. If we ran our async code on the same loop, they would conflict. Running our engine in a dedicated thread gives it a clean, separate event loop via `asyncio.run()`.

**Why a queue for progress updates?**  
Streamlit widgets (like progress bars) can only be updated from the session's main thread. The URL checker runs in a background thread. A `queue.Queue()` acts as a thread-safe message channel: the worker thread puts results in, the main thread takes them out and updates the UI.

**Why stream 5 KB instead of downloading the full page?**  
The `<title>` tag and soft-404 phrases always appear near the top of an HTML page. Reading just 5 KB is enough to detect both, while downloading a full large page (which could be megabytes) would be slow and wasteful.

---

## 15. Known Limitations

| Limitation | Detail |
|---|---|
| Scanned PDFs | PDFs created by scanning paper pages contain images, not text. No URLs can be extracted. The tool will display a warning. A separate OCR (optical character recognition) step is needed before upload. |
| Bot-blocking sites | Cloudflare, Akamai, and similar services may return 403 Forbidden even when a normal browser can access the page. These are marked Suspicious rather than Dead, since the page may be accessible to human visitors. |
| Login-required pages | Internal EPA intranet pages or partner portals that require authentication will return 401 or 403. These are marked Suspicious. A human reviewer must confirm whether the content is accessible. |
| Relative URLs | URLs without a domain (e.g. `/other-page`) cannot be checked because we do not know which website they belong to. They are marked Skipped. |
| Old .doc format | Only modern `.docx` files (Word 2007 and later) are supported. Older binary `.doc` files cannot be opened by python-docx. |
| JavaScript-rendered content | Some websites load their content via JavaScript after the initial page load. The tool reads the raw server response before JavaScript runs, so pages that require JavaScript to display their content may appear as soft-404s. |
| Rate limiting | Checking many URLs from the same domain quickly may trigger rate limiting (HTTP 429). The tool retries once and respects `Retry-After` headers, but persistent rate limiting will result in Suspicious verdicts. Reduce concurrent checks if this occurs. |
| No authentication | The tool cannot log into websites. It cannot check URLs behind SSO, two-factor authentication, or EPA network-only resources. |

---

## 16. Extending the Tool

### Add support for a new file format

1. Create `extractors/myformat_extractor.py` subclassing `BaseExtractor`:

```python
from extractors.base import BaseExtractor, ExtractedUrl
from utils.url_utils import extract_plain_urls, get_context

class MyFormatExtractor(BaseExtractor):
    def extract(self):
        results = []
        # open self.file_path, find URLs, build ExtractedUrl objects
        return results
```

2. Register the new extension in `app.py → _get_extractor()`:

```python
".myext": MyFormatExtractor,
```

3. Add `.myext` to `SUPPORTED_EXTENSIONS` in `utils/constants.py`.

4. Add `.myext` to the `type=` list in the sidebar file uploader in `app.py`.

### Add a new detection rule

All detection logic lives in `validators/status_classifier.py` inside the `classify_url_result()` function. Add a new `if` branch and return an appropriate `(tier, reason)` tuple.

Then add a matching test case in `tests/test_status_classifier.py`.

### Change soft-404 patterns

Edit the `SOFT_404_PATTERNS` list in `utils/constants.py`. Add any phrase (lowercase) that commonly appears on "page not found" pages for the sites you are auditing.

### Change detection thresholds or defaults

All tunable values are centralised in `utils/constants.py`:

| Constant | Default | Purpose |
|---|---|---|
| `DEFAULT_TIMEOUT` | `10` | Seconds to wait per URL |
| `DEFAULT_MAX_WORKERS` | `20` | Parallel URL checks |
| `BODY_PREVIEW_BYTES` | `5120` | Bytes read per page for soft-404 detection |
| `MAX_RETRY_AFTER_SECS` | `5` | Maximum seconds to honour a server's Retry-After header |
| `MAX_FILE_SIZE_MB` | `50` | Maximum upload size |
| `SOFT_404_PATTERNS` | (list) | Phrases that indicate a soft 404 |
