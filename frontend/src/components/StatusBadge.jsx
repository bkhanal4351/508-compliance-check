// StatusBadge.jsx — A small coloured pill/label that shows a severity or tier.
//
// In 508 scanning, severity is: Critical | Serious | Moderate | Minor
// In URL checking, tier is:     Dead | Suspicious | Alive | Skipped
//
// The badge is nothing more than a <span> with a CSS class that sets its colour.
// Both use cases share this component because the visual pattern is identical.
//
// Props:
//   value (string) — the text to display inside the badge (e.g. "Critical", "Dead")

// Maps each possible value to a CSS class defined in App.css.
// The class sets the background color of the badge.
const CLASS_MAP = {
  // 508 severity levels
  Critical:   'sev-critical',
  Serious:    'sev-serious',
  Moderate:   'sev-moderate',
  Minor:      'sev-minor',

  // URL checker tiers
  Dead:       'tier-dead',
  Suspicious: 'tier-suspicious',
  Alive:      'tier-alive',
  Skipped:    'tier-skipped',
}

export default function StatusBadge({ value }) {
  // Look up the CSS class for this value, fall back to empty string if unknown
  const cls = CLASS_MAP[value] || ''

  // The "badge" class provides the shape (rounded corners, padding, white text).
  // The second class sets the background colour.
  return (
    <span className={`badge ${cls}`}>
      {value}   {/* The text shown inside the badge */}
    </span>
  )
}
