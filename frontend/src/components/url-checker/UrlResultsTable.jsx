// UrlResultsTable.jsx — Displays the URL checker results in a filterable table.
//
// Each row shows one unique URL that was found in the uploaded documents.
// Rows are pre-sorted by severity (Dead first, Skipped last).
// Expandable rows show: all locations the URL appeared in, redirect chain,
// response time, and (for Dead URLs) a Wayback Machine archive link.
//
// Props:
//   results (Array) — CheckResult objects from the URL checker API.
//     Each has: url, tier, status_code, reason, final_url, redirect_count,
//     redirect_chain, response_time_ms, is_epa_internal, wayback_url,
//     wayback_snapshot_date, locations, page_title, checked_at.

import { useState } from 'react'
import StatusBadge from '../StatusBadge.jsx'

// Sort order for tiers — lower number = shown first
const TIER_ORDER = { Dead: 0, Suspicious: 1, Alive: 2, Skipped: 3 }

export default function UrlResultsTable({ results }) {
  // filterTier: '' = all, or one of Dead/Suspicious/Alive/Skipped
  const [filterTier, setFilterTier] = useState('')

  // search: text the user types to filter by URL or source file
  const [search, setSearch] = useState('')

  // expandedUrl: the URL string whose detail row is open (null = none)
  const [expandedUrl, setExpandedUrl] = useState(null)

  // ── Sort + filter ─────────────────────────────────────────────────────────
  const visible = [...results]
    // Sort by tier severity first, then alphabetically by URL
    .sort((a, b) => {
      const ta = TIER_ORDER[a.tier] ?? 99
      const tb = TIER_ORDER[b.tier] ?? 99
      if (ta !== tb) return ta - tb
      return a.url.localeCompare(b.url)
    })
    // Apply tier filter — skip if '' (show all)
    .filter(r => !filterTier || r.tier === filterTier)
    // Apply text search against URL, reason, and source file name
    .filter(r => {
      if (!search) return true
      const q = search.toLowerCase()
      return (
        r.url.toLowerCase().includes(q) ||
        (r.reason || '').toLowerCase().includes(q) ||
        r.locations.some(l => l.source_file.toLowerCase().includes(q))
      )
    })

  // ── Empty state ──────────────────────────────────────────────────────────
  if (!results.length) {
    return (
      <div className="card">
        <div className="empty-state">No URLs were found in the uploaded documents.</div>
      </div>
    )
  }

  // ── Render ───────────────────────────────────────────────────────────────
  return (
    <div className="card">
      {/* ── Header + filter bar ── */}
      <div className="results-header">
        <h2>URL Results ({visible.length} of {results.length})</h2>
      </div>

      <div className="filter-bar">
        {/* Text search */}
        <input
          type="text"
          placeholder="Search URL, reason, source file…"
          value={search}
          onChange={e => setSearch(e.target.value)}
          aria-label="Search URL results"
        />

        {/* Tier filter dropdown */}
        <select
          value={filterTier}
          onChange={e => setFilterTier(e.target.value)}
          aria-label="Filter by status"
        >
          <option value="">All statuses</option>
          <option value="Dead">Dead</option>
          <option value="Suspicious">Suspicious</option>
          <option value="Alive">Alive</option>
          <option value="Skipped">Skipped</option>
        </select>
      </div>

      {/* ── Table ── */}
      <div className="results-table-wrap">
        <table aria-label="URL check results">
          <thead>
            <tr>
              <th>Status</th>
              <th>URL</th>
              <th>HTTP Code</th>
              <th>Source File</th>
              <th>Reason</th>
              <th>Details</th>
            </tr>
          </thead>
          <tbody>
            {visible.length === 0 ? (
              <tr>
                <td colSpan={6} className="empty-state">No results match the current filters.</td>
              </tr>
            ) : (
              visible.map(r => (
                <UrlRow
                  key={r.url}
                  result={r}
                  expanded={expandedUrl === r.url}
                  onToggle={() => setExpandedUrl(expandedUrl === r.url ? null : r.url)}
                />
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ── UrlRow ────────────────────────────────────────────────────────────────────
// Renders the main data row for one URL plus an expandable detail row.
//
// Props:
//   result   — one CheckResult object
//   expanded — whether the detail panel is open
//   onToggle — callback to open/close the detail panel
function UrlRow({ result: r, expanded, onToggle }) {
  // primary = the first location this URL appeared in (used for Source File column)
  const primary = r.locations[0]

  return (
    <>
      {/* ── Main row ── */}
      <tr>
        {/* Coloured status badge: Dead (red) / Suspicious (orange) / Alive (green) / Skipped (grey) */}
        <td><StatusBadge value={r.tier} /></td>

        {/* The URL — shown as a clickable link that opens in a new tab.
            word-break: break-all prevents very long URLs from breaking the layout. */}
        <td className="url-cell">
          <a href={r.url} target="_blank" rel="noreferrer">
            {r.url.length > 80 ? r.url.slice(0, 80) + '…' : r.url}
            {/* If the URL was truncated, the full URL is in the href */}
          </a>
        </td>

        {/* HTTP status code, e.g. 200, 404 — empty if the request never completed */}
        <td style={{ textAlign: 'center' }}>{r.status_code ?? '—'}</td>

        {/* Source file name and location (e.g. "policy.docx · Page 3") */}
        <td className="location-cell">
          {primary ? (
            <>
              <div>{primary.source_file}</div>
              <div style={{ color: '#888', fontSize: 11 }}>{primary.location}</div>
            </>
          ) : '—'}
        </td>

        {/* Plain-English reason the URL was flagged (blank for Alive/Skipped) */}
        <td className="reason-cell">{r.reason || ''}</td>

        {/* Expand/collapse button */}
        <td>
          <button className="expand-btn" onClick={onToggle} aria-expanded={expanded}>
            {expanded ? 'Hide ▲' : 'Details ▼'}
          </button>
        </td>
      </tr>

      {/* ── Detail row ── */}
      {expanded && (
        <tr className="detail-row">
          <td colSpan={6}>
            <div className="detail-block">
              {/* Final URL after redirects */}
              {r.final_url && (
                <p>
                  <strong>Redirected to:</strong>&nbsp;
                  <a href={r.final_url} target="_blank" rel="noreferrer">{r.final_url}</a>
                </p>
              )}

              {/* Response time in milliseconds */}
              <p><strong>Response time:</strong> {r.response_time_ms} ms</p>

              {/* Number of redirects that happened */}
              {r.redirect_count > 0 && (
                <p><strong>Redirects:</strong> {r.redirect_count}</p>
              )}

              {/* Full redirect chain — each step listed as "status → url" */}
              {r.redirect_chain?.length > 0 && (
                <p>
                  <strong>Redirect chain:</strong>&nbsp;
                  {r.redirect_chain.map(([code, url]) => `${code} → ${url}`).join(' · ')}
                </p>
              )}

              {/* Page title (only fetched if "fetch_titles" was enabled) */}
              {r.page_title && <p><strong>Page title:</strong> {r.page_title}</p>}

              {/* EPA internal flag */}
              <p><strong>EPA internal:</strong> {r.is_epa_internal ? 'Yes' : 'No'}</p>

              {/* Wayback Machine snapshot — only shown for Dead URLs */}
              {r.tier === 'Dead' && (
                r.wayback_url ? (
                  <p>
                    <strong>Last archived:</strong>&nbsp;
                    <a href={r.wayback_url} className="wayback-link" target="_blank" rel="noreferrer">
                      {r.wayback_snapshot_date || 'View on Wayback Machine'}
                    </a>
                  </p>
                ) : (
                  <p style={{ color: '#888', fontSize: 12 }}>No Wayback Machine snapshot found.</p>
                )
              )}

              {/* Every location in every uploaded file where this URL appeared */}
              {r.locations.length > 1 && (
                <div style={{ gridColumn: '1 / -1' }}>
                  <strong>Also found in:</strong>
                  <ul style={{ marginTop: 4, paddingLeft: 18, fontSize: 12 }}>
                    {r.locations.slice(1).map((loc, i) => (
                      <li key={i}>{loc.source_file} — {loc.location}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          </td>
        </tr>
      )}
    </>
  )
}
