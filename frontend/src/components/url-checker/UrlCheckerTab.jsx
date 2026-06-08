// UrlCheckerTab.jsx — The second tab: URL dead-link / live-link checker.
//
// What it does end-to-end:
//   1. User uploads one or more documents (DOCX, PDF, PPTX, XLSX, TXT, HTML).
//   2. User optionally adjusts timeout, concurrency, and other settings.
//   3. User clicks "Check URLs".
//   4. Backend extracts every URL from the documents, deduplicates them,
//      then visits each URL asynchronously (like a browser) and classifies it:
//        Dead       — 404, DNS failure, timeout, etc.
//        Suspicious — soft 404, silent redirect, rate-limited
//        Alive      — HTTP 200 or clean redirect to a live page
//        Skipped    — mailto:, tel:, relative URL, etc. (not checkable)
//   5. Results appear in a filterable table sorted worst-first.
//   6. Dead URLs show a Wayback Machine archive link if one exists.
//   7. Export as Excel or CSV.
//
// State:
//   files       — selected File objects
//   settings    — checker configuration (timeout, maxWorkers, etc.)
//   loading     — spinner flag
//   error       — error message or null
//   results     — { results: CheckResult[], summary, warnings }
//   filterTier  — which tier to show in the table ('' = all)
//   search      — free-text search string

import { useState } from 'react'
import { checkUrls, exportCsv, exportExcel } from '../../api/urlChecker.js'
import FileDropZone  from '../FileDropZone.jsx'
import SummaryCards  from '../SummaryCards.jsx'
import UrlResultsTable from './UrlResultsTable.jsx'

export default function UrlCheckerTab() {
  // ── State ────────────────────────────────────────────────────────────────
  const [files, setFiles] = useState([])

  // Settings object — grouped so we can spread it into the API call easily
  const [settings, setSettings] = useState({
    timeout: 10,         // seconds to wait before marking a URL as timed out
    maxWorkers: 20,      // how many URLs to check in parallel at once
    fetchTitles: false,  // whether to also grab the <title> of each page
    retry: true,         // whether to retry once on server errors (5xx / 429)
  })

  const [loading, setLoading]   = useState(false)
  const [error, setError]       = useState(null)
  const [results, setResults]   = useState(null)   // full API response
  const [exporting, setExporting] = useState(false)

  // ── Helpers ──────────────────────────────────────────────────────────────
  // Update one key inside the settings object without replacing the whole thing.
  // e.g. updateSetting('timeout', 15) → settings becomes { ...settings, timeout: 15 }
  function updateSetting(key, value) {
    setSettings(prev => ({ ...prev, [key]: value }))
  }

  // ── Run check ────────────────────────────────────────────────────────────
  async function handleCheck(e) {
    e.preventDefault()
    if (!files.length) { setError('Please upload at least one file'); return }

    setError(null)
    setResults(null)
    setLoading(true)

    try {
      // checkUrls is defined in urlChecker.js — it sends all files to the backend
      const data = await checkUrls(files, {
        timeout:     settings.timeout,
        maxWorkers:  settings.maxWorkers,
        fetchTitles: settings.fetchTitles,
        retry:       settings.retry,
      })
      setResults(data)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  // ── Exports ──────────────────────────────────────────────────────────────
  async function handleExportCsv() {
    if (!results) return
    setExporting(true)
    try { await exportCsv(results.results) }
    catch { setError('CSV export failed') }
    finally { setExporting(false) }
  }

  async function handleExportExcel() {
    if (!results) return
    setExporting(true)
    try { await exportExcel(results.results) }
    catch { setError('Excel export failed') }
    finally { setExporting(false) }
  }

  // ── Summary cards data ───────────────────────────────────────────────────
  const summaryItems = results ? [
    { label: 'Dead',       count: results.summary.Dead,       colorClass: 'tier-dead'       },
    { label: 'Suspicious', count: results.summary.Suspicious, colorClass: 'tier-suspicious' },
    { label: 'Alive',      count: results.summary.Alive,      colorClass: 'tier-alive'      },
    { label: 'Skipped',    count: results.summary.Skipped,    colorClass: 'tier-skipped'    },
  ] : []

  // ── Render ───────────────────────────────────────────────────────────────
  return (
    <div>
      {/* ── Input card ── */}
      <div className="card">
        <h2>Upload Documents</h2>
        <form onSubmit={handleCheck}>
          {/* File drop zone — accepts all supported document types */}
          <FileDropZone
            files={files}
            onChange={setFiles}
            accept=".docx,.pdf,.pptx,.xlsx,.txt,.html,.htm"
            multiple={true}
            label="Drop documents here or click to browse"
            hint="Accepts DOCX, PDF, PPTX, XLSX, TXT, HTML — up to 50 MB each"
          />

          {/* ── Advanced settings ── */}
          <details style={{ marginTop: 14 }}>
            <summary style={{ cursor: 'pointer', fontSize: 13, color: '#1b3a6b', fontWeight: 600 }}>
              Advanced settings
            </summary>
            <div className="settings-row" style={{ marginTop: 10 }}>
              {/* Timeout: max seconds to wait for each URL */}
              <div className="form-group" style={{ flexDirection: 'row', alignItems: 'center', gap: 8, minWidth: 'unset' }}>
                <label htmlFor="timeout" style={{ textTransform: 'none', fontSize: 13, whiteSpace: 'nowrap' }}>
                  Timeout (s)
                </label>
                <input
                  id="timeout"
                  type="number"
                  min={1}
                  max={60}
                  value={settings.timeout}
                  onChange={e => updateSetting('timeout', Number(e.target.value))}
                  style={{ width: 70 }}
                />
              </div>

              {/* Max workers: how many parallel checks */}
              <div className="form-group" style={{ flexDirection: 'row', alignItems: 'center', gap: 8, minWidth: 'unset' }}>
                <label htmlFor="max-workers" style={{ textTransform: 'none', fontSize: 13, whiteSpace: 'nowrap' }}>
                  Parallel checks
                </label>
                <input
                  id="max-workers"
                  type="number"
                  min={1}
                  max={50}
                  value={settings.maxWorkers}
                  onChange={e => updateSetting('maxWorkers', Number(e.target.value))}
                  style={{ width: 70 }}
                />
              </div>

              {/* Fetch titles: load the <title> tag of each page */}
              <label style={{ fontSize: 13 }}>
                <input
                  type="checkbox"
                  checked={settings.fetchTitles}
                  onChange={e => updateSetting('fetchTitles', e.target.checked)}
                  style={{ marginRight: 6 }}
                />
                Fetch page titles
              </label>

              {/* Retry: whether to retry on server errors */}
              <label style={{ fontSize: 13 }}>
                <input
                  type="checkbox"
                  checked={settings.retry}
                  onChange={e => updateSetting('retry', e.target.checked)}
                  style={{ marginRight: 6 }}
                />
                Retry on server error
              </label>
            </div>
          </details>

          {/* Submit button */}
          <div style={{ marginTop: 14 }}>
            <button
              type="submit"
              className="btn btn-primary"
              disabled={loading || !files.length}
            >
              {loading ? 'Checking URLs…' : 'Check URLs'}
            </button>
          </div>
        </form>
      </div>

      {/* ── Error alert ── */}
      {error && (
        <div className="alert alert-error" role="alert">{error}</div>
      )}

      {/* ── Warnings from backend (e.g. unsupported file) ── */}
      {results?.warnings?.length > 0 && (
        <div className="alert alert-warning">
          <strong>Warnings:</strong>
          <ul style={{ marginTop: 4, paddingLeft: 18 }}>
            {results.warnings.map((w, i) => <li key={i}>{w}</li>)}
          </ul>
        </div>
      )}

      {/* ── Loading spinner ── */}
      {loading && (
        <div className="loading-overlay">
          <div className="spinner" aria-hidden="true" />
          <p>Checking URLs… this may take a moment depending on how many are found.</p>
        </div>
      )}

      {/* ── Results ── */}
      {results && !loading && (
        <div>
          {/* Coloured count boxes: Dead / Suspicious / Alive / Skipped */}
          <SummaryCards items={summaryItems} />

          {/* Export buttons */}
          {results.results.length > 0 && (
            <div className="export-row" style={{ marginBottom: 16 }}>
              <button
                className="btn btn-secondary"
                onClick={handleExportExcel}
                disabled={exporting}
              >
                {exporting ? '…' : '⬇ Export Excel'}
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

          {/* The main results table */}
          <UrlResultsTable results={results.results} />
        </div>
      )}
    </div>
  )
}
