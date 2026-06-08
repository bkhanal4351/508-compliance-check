// urlChecker.js — API functions for the URL dead-link / live-link checker.
//
// Each function here corresponds to one backend endpoint in
// backend/routers/url_checker.py.
//
// The proxy setup in vite.config.js forwards all "/api/*" requests to the
// FastAPI backend at http://localhost:8000 during development.

// ── Check URLs in uploaded documents ─────────────────────────────────────────
// Sends one or more documents to the backend along with checker settings.
// The backend will:
//   1. Extract every URL from each document (hyperlinks + plain text)
//   2. Deduplicate so each unique URL is only checked once
//   3. Visit each URL asynchronously and classify it as:
//        Dead       — 404, DNS failure, timeout, connection refused
//        Suspicious — soft 404, silent redirect, rate-limited
//        Alive      — HTTP 200 or clean redirect to a live page
//        Skipped    — mailto:, tel:, relative URL (not checkable)
//   4. Return results + summary + any per-file warnings
//
// @param {FileList|File[]} files     — Documents to extract URLs from
// @param {object} opts               — Checker settings
// @param {number} opts.timeout       — Seconds to wait per URL before marking it dead (default 10)
// @param {number} opts.maxWorkers    — How many URLs to check in parallel at once (default 20)
// @param {boolean} opts.fetchTitles  — Whether to also read the <title> tag of each page
// @param {boolean} opts.retry        — Whether to retry once on 5xx / 429 server errors
// @returns {Promise<{results: CheckResult[], summary, warnings}>}
export async function checkUrls(files, {
  timeout = 10,
  maxWorkers = 20,
  fetchTitles = false,
  retry = true,
} = {}) {
  // FormData is the multipart/form-data format — the same encoding a browser
  // uses when you submit an HTML <form enctype="multipart/form-data">.
  const fd = new FormData()

  // Append each file under the same field name "files".
  // FastAPI's endpoint declares it as list[UploadFile], so multiple files
  // with the same field name are collected into a list automatically.
  for (const f of files) {
    fd.append('files', f)
  }

  // Non-file settings are appended as plain string values (FastAPI reads them via Form()).
  fd.append('timeout',      String(timeout))
  fd.append('max_workers',  String(maxWorkers))
  fd.append('fetch_titles', String(fetchTitles))
  fd.append('retry',        String(retry))

  const res = await fetch('/api/urlcheck/check', { method: 'POST', body: fd })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || 'URL check failed')
  }
  return res.json()  // returns { results, summary, warnings }
}

// ── Export URL results as CSV ─────────────────────────────────────────────────
// Sends the results list to the backend, which formats them as a sorted CSV
// (Dead first, Skipped last) and streams the bytes back for download.
//
// @param {Array} results — The results array from a previous checkUrls() response
export async function exportCsv(results) {
  const res = await fetch('/api/urlcheck/export/csv', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ results }),  // send the results array as JSON
  })
  if (!res.ok) throw new Error('CSV export failed')

  // Create an in-memory URL from the bytes the server sent back,
  // attach it to a hidden <a> element, and simulate a click to save the file.
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = 'url_check_results.csv'
  a.click()
  URL.revokeObjectURL(url)  // free the temporary URL from browser memory
}

// ── Export URL results as Excel (.xlsx) ───────────────────────────────────────
// Same download pattern as exportCsv.  The server returns a binary .xlsx file
// with formatted columns, colour-coded status cells, and clickable hyperlinks.
//
// @param {Array} results — The results array from a previous checkUrls() response
export async function exportExcel(results) {
  const res = await fetch('/api/urlcheck/export/excel', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ results }),
  })
  if (!res.ok) throw new Error('Excel export failed')

  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = 'url_check_results.xlsx'
  a.click()
  URL.revokeObjectURL(url)
}
