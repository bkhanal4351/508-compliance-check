import csv
import io

from extractors.base import CheckResult
from utils.constants import SEVERITY_ORDER


def export_csv(results: list[CheckResult]) -> bytes:
    """Return raw CSV bytes, sorted by severity."""
    sorted_results = sorted(results, key=lambda r: SEVERITY_ORDER.get(r.tier, 99))

    buf = io.StringIO()
    writer = csv.writer(buf)

    writer.writerow([
        "Status", "Original URL", "Final URL", "HTTP Code",
        "Source File", "Location", "Context", "Response Time (ms)",
        "Redirect Count", "Redirect Chain", "Reason",
        "Wayback Snapshot URL", "Wayback Snapshot Date",
        "EPA Internal", "Checked At",
    ])

    for r in sorted_results:
        primary = r.locations[0] if r.locations else None
        chain_str = " -> ".join("{} {}".format(code, url) for code, url in r.redirect_chain) if r.redirect_chain else ""
        writer.writerow([
            r.tier,
            r.url,
            r.final_url or "",
            r.status_code or "",
            primary.source_file if primary else "",
            primary.location if primary else "",
            primary.context if primary else "",
            r.response_time_ms,
            r.redirect_count,
            chain_str,
            r.reason or "",
            r.wayback_url or ("No snapshot found" if r.tier == "Dead" else ""),
            r.wayback_snapshot_date or "",
            "Yes" if r.is_epa_internal else "No",
            r.checked_at.strftime("%Y-%m-%d %H:%M UTC"),
        ])

    return buf.getvalue().encode("utf-8")
