// SummaryCards.jsx — The row of coloured count boxes shown at the top of results.
//
// For 508 Scanner it shows four cards: Critical / Serious / Moderate / Minor.
// For URL Checker it shows four cards: Dead / Suspicious / Alive / Skipped.
//
// Props:
//   items (Array<{label, count, colorClass}>)
//     Each item becomes one card.  'colorClass' is one of the CSS classes
//     defined in App.css (e.g. 'sev-critical', 'tier-dead').

export default function SummaryCards({ items }) {
  return (
    // summary-row is a flex container that spaces the cards evenly
    <div className="summary-row" role="list" aria-label="Results summary">
      {items.map(({ label, count, colorClass }) => (
        // Each card is a coloured box with a big number and a label below it
        <div key={label} className={`summary-card ${colorClass}`} role="listitem">
          {/* The large number — how many findings/results in this category */}
          <div className="count">{count}</div>
          {/* The category name in small caps below the number */}
          <div className="label">{label}</div>
        </div>
      ))}
    </div>
  )
}
