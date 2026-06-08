// Scanner508Tab.jsx — The first tab: 508 / WCAG compliance scanner.
//
// What it does end-to-end:
//   1. User chooses "URL" or "Document" mode with a radio button.
//   2. In URL mode:  user types a web address and optionally enables crawling.
//      In Document mode: user uploads a PDF, DOCX, PPTX, XLSX, or image file.
//   3. User clicks "Run Scan".
//   4. The component calls the API (scanner508.js → FastAPI backend).
//   5. While waiting, a spinner is shown.
//   6. On success, the severity summary cards appear above a filterable findings table.
//   7. "Export PDF" and "Export CSV" buttons let the user download the results.
//
// State overview (useState):
//   mode         — 'url' or 'document' — controls which input section is shown
//   urlInput     — the text the user has typed in the URL field
//   crawl        — checkbox: should we follow links and scan multiple pages?
//   maxPages     — how many pages to scan at most when crawling
//   file         — the single File object chosen for document mode
//   loading      — true while the API call is in flight (shows spinner)
//   error        — error message string, or null if no error
//   results      — the API response: { findings, summary, scanned_at, deduped_count }

import { useState } from 'react'
import { exportCsv, exportPdf, scanDocument, scanUrl } from '../../api/scanner508.js'
import FileDropZone     from '../FileDropZone.jsx'       // drag-and-drop file picker (shared)
import Findings508Table from './Findings508Table.jsx'    // the findings results table
import SummaryCards     from '../SummaryCards.jsx'       // the coloured count boxes (shared)

export default function Scanner508Tab() {
  // ── Local state ──────────────────────────────────────────────────────────────
  const [mode, setMode]         = useState('url')   // 'url' or 'document'
  const [urlInput, setUrlInput] = useState('')       // what the user typed
  const [crawl, setCrawl]       = useState(false)    // crawl checkbox value
  const [maxPages, setMaxPages] = useState(25)       // max pages to crawl
  const [files, setFiles]       = useState([])       // selected document file(s)
  const [loading, setLoading]   = useState(false)    // spinner visibility
  const [error, setError]       = useState(null)     // error message or null
  const [results, setResults]   = useState(null)     // API response or null
  const [exporting, setExporting] = useState(false)  // export in-flight flag

  // ── Run scan ─────────────────────────────────────────────────────────────────
  // This function is called when the user clicks the "Run Scan" button.
  async function handleScan(e) {
    e.preventDefault()     // stop the <form> from doing a full-page browser reload
    setError(null)         // clear any previous error message
    setResults(null)       // clear any previous results
    setLoading(true)       // show the spinner

    try {
      let data
      if (mode === 'url') {
        // Validate: URL must not be empty
        if (!urlInput.trim()) throw new Error('Please enter a URL')
        // Call the URL scan API function in scanner508.js
        data = await scanUrl(urlInput.trim(), crawl, 1, maxPages)
      } else {
        // Validate: a file must be chosen
        if (!files.length) throw new Error('Please select a file')
        // Call the document scan API function with the first (only) file
        data = await scanDocument(files[0])
      }
      setResults(data)    // store the API response — this triggers the results section to appear
    } catch (err) {
      // If anything goes wrong (network error, server error, validation), show the message
      setError(err.message)
    } finally {
      setLoading(false)   // always hide the spinner when done (success or failure)
    }
  }

  // ── PDF export ───────────────────────────────────────────────────────────────
  async function handleExportPdf() {
    if (!results) return
    setExporting(true)
    try {
      await exportPdf(results.findings, results.summary, results.scan_target || urlInput, results.scanned_at)
    } catch {
      setError('PDF export failed')
    } finally {
      setExporting(false)
    }
  }

  // ── CSV export ───────────────────────────────────────────────────────────────
  async function handleExportCsv() {
    if (!results) return
    setExporting(true)
    try {
      await exportCsv(results.findings, results.summary, results.scan_target || urlInput, results.scanned_at)
    } catch {
      setError('CSV export failed')
    } finally {
      setExporting(false)
    }
  }

  // ── Severity summary items ───────────────────────────────────────────────────
  // Build the array that SummaryCards expects when results are available
  const summaryItems = results ? [
    { label: 'Critical', count: results.summary.Critical, colorClass: 'sev-critical' },
    { label: 'Serious',  count: results.summary.Serious,  colorClass: 'sev-serious'  },
    { label: 'Moderate', count: results.summary.Moderate, colorClass: 'sev-moderate' },
    { label: 'Minor',    count: results.summary.Minor,    colorClass: 'sev-minor'    },
  ] : []

  // ── Render ───────────────────────────────────────────────────────────────────
  return (
    <div>
      {/* ── Input card ── */}
      <div className="card">
        <h2>Scan Target</h2>

        {/* Mode switcher: URL or Document */}
        <div className="radio-group" style={{ marginBottom: 16 }}>
          <label>
            <input
              type="radio"
              name="mode"
              value="url"
              checked={mode === 'url'}
              onChange={() => setMode('url')}
            />
            Web URL
          </label>
          <label>
            <input
              type="radio"
              name="mode"
              value="document"
              checked={mode === 'document'}
              onChange={() => setMode('document')}
            />
            Upload Document
          </label>
        </div>

        {/* ── URL mode inputs ── */}
        {mode === 'url' && (
          <form onSubmit={handleScan}>
            <div className="form-row" style={{ marginBottom: 12 }}>
              {/* URL text input */}
              <div className="form-group" style={{ flex: 3 }}>
                <label htmlFor="url-input">Page URL</label>
                <input
                  id="url-input"
                  type="url"
                  placeholder="https://example.gov/page"
                  value={urlInput}
                  onChange={e => setUrlInput(e.target.value)}
                  required
                />
              </div>

              {/* Scan button */}
              <button type="submit" className="btn btn-primary" disabled={loading}>
                {loading ? 'Scanning…' : 'Run Scan'}
              </button>
            </div>

            {/* Crawl settings — shown as a secondary row */}
            <div className="settings-row">
              <label>
                <input
                  type="checkbox"
                  checked={crawl}
                  onChange={e => setCrawl(e.target.checked)}
                />
                Crawl linked pages
              </label>
              {crawl && (
                <div className="form-group" style={{ flexDirection: 'row', alignItems: 'center', gap: 8, minWidth: 'unset' }}>
                  <label htmlFor="max-pages" style={{ whiteSpace: 'nowrap', textTransform: 'none', fontSize: 13 }}>
                    Max pages
                  </label>
                  <input
                    id="max-pages"
                    type="number"
                    min={1}
                    max={100}
                    value={maxPages}
                    onChange={e => setMaxPages(Number(e.target.value))}
                    style={{ width: 72 }}
                  />
                </div>
              )}
            </div>
          </form>
        )}

        {/* ── Document mode inputs ── */}
        {mode === 'document' && (
          <form onSubmit={handleScan}>
            <FileDropZone
              files={files}
              onChange={setFiles}
              accept=".pdf,.docx,.pptx,.xlsx,.png,.jpg,.jpeg,.gif,.bmp,.tiff,.webp"
              multiple={false}   // one file at a time for 508 scanning
              label="Drop a document here or click to browse"
              hint="Accepts PDF, DOCX, PPTX, XLSX, or image files"
            />
            <div style={{ marginTop: 14 }}>
              <button type="submit" className="btn btn-primary" disabled={loading || !files.length}>
                {loading ? 'Scanning…' : 'Run Scan'}
              </button>
            </div>
          </form>
        )}
      </div>

      {/* ── Error alert ── */}
      {error && (
        <div className="alert alert-error" role="alert">
          {error}
        </div>
      )}

      {/* ── Loading spinner ── */}
      {loading && (
        <div className="loading-overlay">
          <div className="spinner" aria-hidden="true" />
          <p>Running accessibility scan… this may take a moment.</p>
        </div>
      )}

      {/* ── Results section — only shown after a successful scan ── */}
      {results && !loading && (
        <div>
          {/* Summary cards: four coloured boxes showing counts by severity */}
          <SummaryCards items={summaryItems} />

          {/* Info line: timestamp + deduplication note */}
          <div className="alert alert-info" style={{ marginBottom: 14 }}>
            Scanned at {new Date(results.scanned_at).toLocaleString()}.
            &nbsp;{results.summary.total} finding{results.summary.total !== 1 ? 's' : ''}
            {results.deduped_count > 0 && ` (${results.deduped_count} duplicate${results.deduped_count !== 1 ? 's' : ''} collapsed)`}.
          </div>

          {/* Export buttons */}
          {results.findings.length > 0 && (
            <div className="export-row" style={{ marginBottom: 16 }}>
              <button
                className="btn btn-secondary"
                onClick={handleExportPdf}
                disabled={exporting}
              >
                {exporting ? '…' : '⬇ Export PDF Report'}
              </button>
              <button
                className="btn btn-secondary"
                onClick={handleExportCsv}
                disabled={exporting}
              >
                {exporting ? '…' : '⬇ Export CSV'}
              </button>
            </div>
          )}

          {/* The main findings table — passes all data down to Findings508Table */}
          <Findings508Table findings={results.findings} />
        </div>
      )}
    </div>
  )
}
