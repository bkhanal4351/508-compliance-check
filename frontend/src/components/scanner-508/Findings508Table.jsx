// Findings508Table.jsx — Displays the list of 508/WCAG accessibility findings.
//
// Features:
//   • Filter by severity (Critical / Serious / Moderate / Minor / All)
//   • Free-text search that matches against title, location, or description
//   • Expandable rows — click a row to see full details (snippet, fix suggestion)
//
// Props:
//   findings (Array) — the findings array returned by the scan API.
//     Each finding has: id, severity, title, location, description,
//     wcag_sc, sec508_ref, snippet, suggested_fix, rule, source.

import { useState } from 'react'
import StatusBadge from '../StatusBadge.jsx'   // coloured severity pill

export default function Findings508Table({ findings }) {
  // filterSev: which severity level to show — '' means show all
  const [filterSev, setFilterSev] = useState('')

  // search: free-text the user types into the search box
  const [search, setSearch] = useState('')

  // expandedId: the finding 'id' whose detail row is currently expanded.
  // Only one row can be expanded at a time (null = none expanded).
  const [expandedId, setExpandedId] = useState(null)

  // ── Filtering ─────────────────────────────────────────────────────────────
  // Apply severity filter first, then the text search.
  // Every filter step creates a new array (filter() returns a new array).
  const visible = findings
    .filter(f => !filterSev || f.severity === filterSev)
    .filter(f => {
      if (!search) return true  // no search term — include everything
      const q = search.toLowerCase()
      // Check if any of the important text fields contain the search term
      return (
        f.title.toLowerCase().includes(q) ||
        f.location.toLowerCase().includes(q) ||
        f.description.toLowerCase().includes(q)
      )
    })

  // ── Empty states ──────────────────────────────────────────────────────────
  if (!findings.length) {
    return (
      <div className="card">
        <div className="empty-state">
          ✅ No findings — this content appears to meet WCAG 2.1 AA requirements.
        </div>
      </div>
    )
  }

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <div className="card">
      {/* ── Header row: title + filter controls ── */}
      <div className="results-header">
        <h2>Findings ({visible.length} of {findings.length})</h2>
        <span className="spacer" />   {/* pushes the filter controls to the right */}
      </div>

      {/* ── Filter bar ── */}
      <div className="filter-bar">
        {/* Free-text search box */}
        <input
          type="text"
          placeholder="Search title, location, description…"
          value={search}
          onChange={e => setSearch(e.target.value)}
          aria-label="Search findings"
        />

        {/* Severity dropdown — "All" shows every finding */}
        <select
          value={filterSev}
          onChange={e => setFilterSev(e.target.value)}
          aria-label="Filter by severity"
        >
          <option value="">All severities</option>
          <option value="Critical">Critical</option>
          <option value="Serious">Serious</option>
          <option value="Moderate">Moderate</option>
          <option value="Minor">Minor</option>
        </select>
      </div>

      {/* ── Results table ── */}
      <div className="results-table-wrap">
        <table aria-label="508 findings">
          <thead>
            <tr>
              <th>Severity</th>
              <th>Title</th>
              <th>Location</th>
              <th>WCAG SC</th>
              <th>508 Ref</th>
              <th>Details</th>
            </tr>
          </thead>
          <tbody>
            {visible.length === 0 ? (
              // Show a message if the search/filter returned nothing
              <tr>
                <td colSpan={6} className="empty-state">No findings match the current filters.</td>
              </tr>
            ) : (
              // Render one row per visible finding, plus an optional expanded detail row
              visible.map(f => (
                // React.Fragment lets us return two <tr> elements for one map item
                // without adding extra DOM nodes
                <TableRow
                  key={f.id}
                  finding={f}
                  expanded={expandedId === f.id}
                  onToggle={() => setExpandedId(expandedId === f.id ? null : f.id)}
                />
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ── TableRow ──────────────────────────────────────────────────────────────────
// Renders the main data row plus (optionally) an expandable detail row below it.
// Extracted as its own component to keep the parent readable.
//
// Props:
//   finding  — one finding object
//   expanded — whether the detail row is currently open
//   onToggle — callback to open/close the detail row
function TableRow({ finding: f, expanded, onToggle }) {
  return (
    <>
      {/* ── Main data row ── */}
      <tr>
        {/* Coloured severity badge (Critical / Serious / Moderate / Minor) */}
        <td><StatusBadge value={f.severity} /></td>

        {/* Rule title — what was violated */}
        <td className="desc-cell">{f.title}</td>

        {/* Where in the page/document the issue was found */}
        <td className="location-cell">{f.location}</td>

        {/* WCAG 2.1 Success Criterion, e.g. "1.1.1" */}
        <td style={{ whiteSpace: 'nowrap' }}>{f.wcag_sc}</td>

        {/* Section 508 regulation reference */}
        <td style={{ whiteSpace: 'nowrap' }}>{f.sec508_ref}</td>

        {/* Toggle button to show/hide the detail row */}
        <td>
          <button className="expand-btn" onClick={onToggle} aria-expanded={expanded}>
            {expanded ? 'Hide ▲' : 'Details ▼'}
          </button>
        </td>
      </tr>

      {/* ── Detail row — only rendered when expanded is true ── */}
      {expanded && (
        <tr className="detail-row">
          {/* colSpan=6 makes this cell span all columns */}
          <td colSpan={6}>
            <div className="detail-block">
              {/* Description of what the rule checks and why it failed */}
              <p><strong>Rule:</strong> {f.rule}</p>
              <p><strong>Description:</strong> {f.description}</p>

              {/* HTML snippet of the failing element, if available */}
              {f.snippet && (
                <pre className="snippet-block">{f.snippet}</pre>
              )}

              {/* Suggested fix text or link */}
              {f.suggested_fix && (
                <div className="fix-block">
                  <strong>Suggested fix:</strong>&nbsp;
                  {/* If the fix looks like a URL, make it a clickable link */}
                  {f.suggested_fix.startsWith('http') ? (
                    <a href={f.suggested_fix} target="_blank" rel="noreferrer">
                      {f.suggested_fix}
                    </a>
                  ) : (
                    f.suggested_fix
                  )}
                </div>
              )}

              {/* Source: "deterministic" = rule-based check; "semantic" = AI-assisted */}
              <p style={{ color: '#888', fontSize: 11 }}>Source: {f.source}</p>
            </div>
          </td>
        </tr>
      )}
    </>
  )
}
