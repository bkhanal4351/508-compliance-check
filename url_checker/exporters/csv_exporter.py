# =============================================================================
# csv_exporter.py — Builds the downloadable CSV report.
#
# CSV (Comma-Separated Values) is the simplest export format — just a plain
# text file with rows and columns separated by commas.  It can be opened in
# Excel, Google Sheets, or any text editor.
#
# Unlike the Excel exporter, CSV has no colours, charts, or clickable links —
# but it is the most universally compatible format and is easy to import into
# other tools (databases, reporting dashboards, etc.).
#
# The function returns raw bytes so Streamlit can serve it as a download
# without writing a temporary file to disk.
# =============================================================================

import csv   # Python's built-in library for reading and writing CSV files
import io    # lets us write to memory instead of a real file on disk

from extractors.base import CheckResult
from utils.constants import SEVERITY_ORDER   # maps tier names to sort priority numbers


def export_csv(results: list) -> bytes:
    """
    Convert a list of CheckResult objects into a CSV file and return the raw bytes.

    The rows are sorted so the most severe issues appear first:
      Dead → Suspicious → Alive → Skipped
    This makes the CSV immediately actionable when opened — staff see the
    problems at the top without having to sort or filter.
    """
    # Sort the results by severity.
    # SEVERITY_ORDER is a dict like {"Dead": 0, "Suspicious": 1, "Alive": 2, "Skipped": 3}.
    # key=lambda r: SEVERITY_ORDER.get(r.tier, 99) means: look up each result's tier
    # in the dict and use that number for sorting.  99 is the fallback for any unknown
    # tiers — they sort last.
    sorted_results = sorted(results, key=lambda r: SEVERITY_ORDER.get(r.tier, 99))

    # io.StringIO() creates an in-memory text buffer — like a file, but stored in RAM.
    # csv.writer writes CSV-formatted lines into it.
    buf = io.StringIO()
    writer = csv.writer(buf)

    # Write the header row — these become the column names in Excel/Google Sheets
    writer.writerow([
        "Status",           # Alive / Suspicious / Dead / Skipped
        "Original URL",     # The URL exactly as found in the document
        "Final URL",        # Where we actually ended up after any redirects
        "HTTP Code",        # The server's response code (200, 404, etc.)
        "Source File",      # Which uploaded file contained this URL
        "Location",         # Where in that file (Page 3, Paragraph 7, etc.)
        "Context",          # ~100 chars of surrounding text for context
        "Response Time (ms)",   # How long the server took to respond
        "Redirect Count",   # How many hops happened before the final page
        "Redirect Chain",   # Full list of redirects as text (e.g. "301 http://old → 302 https://new")
        "Reason",           # Plain-English explanation for Dead/Suspicious flags
        "Wayback Snapshot URL",  # Link to last archived copy (for Dead URLs)
        "Wayback Snapshot Date", # Human-readable date of that archive snapshot
        "EPA Internal",     # "Yes" if the URL is on *.epa.gov, "No" otherwise
        "Checked At",       # UTC timestamp of when the check was performed
    ])

    # Write one data row per URL result
    for r in sorted_results:
        # r.locations is a list of every place this URL appeared in documents.
        # We use the first location for the Source File and Location columns.
        # If a URL appeared in 3 different documents, only the first appearance
        # is shown here (all appearances are visible in the Excel export).
        primary = r.locations[0] if r.locations else None

        # Build the redirect chain as a readable string.
        # r.redirect_chain is a list of (status_code, url) tuples.
        # " -> ".join(...) produces: "301 http://old.gov -> 302 https://new.gov"
        # (We use " -> " rather than " → " for broadest CSV compatibility.)
        chain_str = " -> ".join("{} {}".format(code, url) for code, url in r.redirect_chain) if r.redirect_chain else ""

        writer.writerow([
            r.tier,                                          # Status
            r.url,                                           # Original URL
            r.final_url or "",                               # Final URL (empty if no redirect)
            r.status_code or "",                             # HTTP Code (empty if connection failed)
            primary.source_file if primary else "",          # Source File
            primary.location if primary else "",             # Location in file
            primary.context if primary else "",              # Context snippet
            r.response_time_ms,                              # Response Time
            r.redirect_count,                                # Number of redirects
            chain_str,                                       # Redirect chain text
            r.reason or "",                                  # Reason for flag (empty for Alive)
            # Wayback URL: show "No snapshot found" for Dead URLs with no archive,
            # blank for Alive/Suspicious/Skipped (Wayback is only looked up for Dead)
            r.wayback_url or ("No snapshot found" if r.tier == "Dead" else ""),
            r.wayback_snapshot_date or "",                   # Archive date
            "Yes" if r.is_epa_internal else "No",           # EPA Internal
            r.checked_at.strftime("%Y-%m-%d %H:%M UTC"),   # Checked At timestamp
        ])

    # Encode the in-memory text as UTF-8 bytes.
    # "utf-8" handles all characters including accented letters and special symbols.
    # Streamlit's download_button expects bytes, not a string.
    return buf.getvalue().encode("utf-8")
