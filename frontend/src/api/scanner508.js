// scanner508.js — API functions for the 508 / WCAG compliance scanner.
//
// Each function here corresponds to one backend endpoint in
// backend/routers/scanner_508.py.
//
// How the proxy works:
//   During development, Vite intercepts any fetch() call to "/api/*" and
//   forwards it to http://localhost:8000 (configured in vite.config.js).
//   This means the frontend never needs to hard-code the backend address.

// ── Scan a live web URL ───────────────────────────────────────────────────────
// Sends the URL to the backend, which launches a headless browser (Playwright),
// injects the axe-core accessibility engine, and collects all violations.
//
// @param {string}  url       — The page address to check, e.g. "https://epa.gov/page"
// @param {boolean} crawl     — If true, follow links and scan multiple pages
// @param {number}  maxDepth  — How many link-levels deep to follow (1 = direct links only)
// @param {number}  maxPages  — Maximum pages to scan in one run
// @returns {Promise<{findings, summary, scanned_at, deduped_count}>}
export async function scanUrl(url, crawl = false, maxDepth = 1, maxPages = 25) {
  // fetch() is the browser's built-in HTTP client.
  // We POST because we are sending data (the URL + options) to the server.
  const res = await fetch('/api/scan/url', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },  // tell the server we're sending JSON
    body: JSON.stringify({ url, crawl, max_depth: maxDepth, max_pages: maxPages }),
  })

  if (!res.ok) {
    // res.ok is false when the server replied with a 4xx or 5xx status code.
    // We try to parse the error message the server put in the response body.
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || 'Scan failed')
  }

  return res.json()  // parse the JSON response body and return it as a plain object
}

// ── Scan an uploaded document ─────────────────────────────────────────────────
// Uploads a file to the backend using multipart/form-data (the same format used
// by a standard HTML <input type="file"> form).  The backend writes it to a temp
// file, picks the right scanner (pikepdf, python-docx, etc.), and returns findings.
//
// @param {File} file — A browser File object from a file picker or drag-and-drop
// @returns {Promise<{findings, summary, scanned_at, deduped_count}>}
export async function scanDocument(file) {
  // FormData builds the multipart/form-data payload.
  // 'file' is the field name — must match what FastAPI's endpoint declares: File(...).
  const fd = new FormData()
  fd.append('file', file)

  const res = await fetch('/api/scan/document', { method: 'POST', body: fd })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || 'Scan failed')
  }
  return res.json()
}

// ── Export findings as a PDF report ──────────────────────────────────────────
// Sends the findings back to the server, which uses fpdf2 to build a formatted
// PDF with severity cards, a findings table, and detail blocks.
// The PDF bytes stream back and we programmatically "click" a download link
// so the browser saves the file — without leaving the page.
//
// @param {Array}  findings   — The findings array from a previous scan response
// @param {Object} summary    — { Critical, Serious, Moderate, Minor, total }
// @param {string} scanTarget — URL or filename that was scanned (for the PDF header)
// @param {string} scannedAt  — ISO timestamp from the scan response
export async function exportPdf(findings, summary, scanTarget, scannedAt) {
  const res = await fetch('/api/scan/export/pdf', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ findings, summary, scan_target: scanTarget, scanned_at: scannedAt }),
  })
  if (!res.ok) throw new Error('PDF export failed')

  // res.blob() gives us the raw PDF bytes as a Blob (a binary data container).
  const blob = await res.blob()

  // URL.createObjectURL(blob) makes a temporary in-browser URL pointing to those bytes.
  // We attach it to a hidden <a> tag and simulate a click — this triggers the
  // "Save file" dialog without navigating away from the React app.
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = '508_report.pdf'
  a.click()
  URL.revokeObjectURL(url)  // free the temporary URL from browser memory
}

// ── Export findings as CSV ────────────────────────────────────────────────────
// Same download pattern as exportPdf but the server returns plain CSV text.
//
// @param {Array}  findings, summary, scanTarget, scannedAt — same as exportPdf
export async function exportCsv(findings, summary, scanTarget, scannedAt) {
  const res = await fetch('/api/scan/export/csv', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ findings, summary, scan_target: scanTarget, scanned_at: scannedAt }),
  })
  if (!res.ok) throw new Error('CSV export failed')

  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = '508_findings.csv'
  a.click()
  URL.revokeObjectURL(url)
}
