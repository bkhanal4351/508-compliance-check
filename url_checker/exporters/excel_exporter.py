# =============================================================================
# excel_exporter.py — Builds the downloadable Excel (.xlsx) report.
#
# The workbook has two tabs:
#   "Summary" — a quick overview: title, timestamp, stats table, and a bar chart
#               showing how many URLs fell into each status tier.
#   "Details" — one row per checked URL, with all the technical data,
#               colour-coded by status tier, and clickable hyperlinks.
#
# The function returns the workbook as raw bytes (not a file on disk), so
# Streamlit can serve it as a download without writing temporary files.
# =============================================================================

import io                   # lets us write files to memory instead of disk
from datetime import datetime

from openpyxl import Workbook                        # creates new Excel workbooks
from openpyxl.chart import BarChart, Reference       # for the bar chart on the summary sheet
from openpyxl.styles import Alignment, Font, PatternFill   # cell formatting
from openpyxl.utils import get_column_letter         # converts column number to letter (1→"A")

from extractors.base import CheckResult
from utils.constants import SEVERITY_ORDER, TIER_EXCEL_FILLS


# -----------------------------------------------------------------------------
# _tier_fill — Helper: create a background colour for a status tier
# -----------------------------------------------------------------------------

def _tier_fill(tier: str) -> PatternFill:
    """
    Return an openpyxl PatternFill (a solid background colour) for a tier name.
    For example, "Dead" → red, "Alive" → green.
    TIER_EXCEL_FILLS is a dict in constants.py mapping tier names to hex colour strings.
    """
    hex_color = TIER_EXCEL_FILLS.get(tier, "FFFFFF")    # default: white if tier not found
    # "solid" fill type means a single flat colour — no gradients or patterns
    return PatternFill(start_color=hex_color, end_color=hex_color, fill_type="solid")


# -----------------------------------------------------------------------------
# _header_style — Helper: apply bold white text on dark blue background to a cell
# -----------------------------------------------------------------------------

def _header_style(cell, text: str) -> None:
    """
    Format a cell as a table column header: dark blue background, white bold text,
    centred both horizontally and vertically, with word-wrap enabled.
    """
    cell.value = text                                     # put the label text in the cell
    cell.font = Font(bold=True, color="FFFFFF")           # white bold text
    cell.fill = PatternFill(start_color="2E4057", end_color="2E4057", fill_type="solid")  # dark navy blue
    cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)


# -----------------------------------------------------------------------------
# export_excel — Main public function: build the workbook and return as bytes
# -----------------------------------------------------------------------------

def export_excel(
    results: list,       # List[CheckResult] — all the URL check results to export
    settings: dict,      # user's settings: timeout, max_workers, retry — shown on summary
    source_names: list,  # List[str] — filenames of the uploaded documents
) -> bytes:
    """
    Build an Excel workbook in memory and return its raw bytes.
    Streamlit uses these bytes as the data for a download button.
    """
    wb = Workbook()   # create a brand-new empty workbook

    # Every new Workbook has one default sheet called "Sheet"; rename it "Summary"
    ws_summary = wb.active
    ws_summary.title = "Summary"
    _write_summary(ws_summary, results, settings, source_names)   # fill the summary tab

    # Create a second tab called "Details" for the row-by-row breakdown
    ws_details = wb.create_sheet("Details")
    _write_details(ws_details, results)   # fill the details tab

    # Save the workbook into an in-memory buffer instead of a real file.
    # io.BytesIO() is like a RAM-based file — .save() writes bytes into it,
    # and .getvalue() reads all those bytes back out as a Python bytes object.
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()   # return the raw Excel file bytes


# -----------------------------------------------------------------------------
# _write_summary — Fill the "Summary" worksheet
# -----------------------------------------------------------------------------

def _write_summary(ws, results: list, settings: dict, source_names: list) -> None:
    """
    Write a human-friendly overview to the Summary sheet:
      - Title and metadata (timestamp, files scanned, settings)
      - A small stats table (Dead / Suspicious / Alive / Skipped counts)
      - A bar chart visualising those counts
    """
    from collections import Counter   # counts occurrences; lazy import to keep top-level clean

    # Count how many results belong to each tier
    # e.g. Counter({"Alive": 42, "Dead": 5, "Suspicious": 3, "Skipped": 10})
    counts = Counter(r.tier for r in results)
    tiers = ["Dead", "Suspicious", "Alive", "Skipped"]   # display order (worst first)

    # ---- Header block (rows 1–4) ----
    ws["A1"] = "URL Check Report"
    ws["A1"].font = Font(bold=True, size=16)   # large title text

    # strftime formats the current UTC time as "2024-07-15 13:45 UTC"
    ws["A2"] = "Generated: {}".format(datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"))
    ws["A3"] = "Files scanned: {}".format(", ".join(source_names))
    ws["A4"] = "Settings — Timeout: {}s  |  Workers: {}  |  Retry: {}".format(
        settings.get("timeout", 10),
        settings.get("max_workers", 20),
        settings.get("retry", True),
    )

    # ---- Stats table header (row 6) ----
    ws["A6"] = "Status"
    ws["B6"] = "Count"
    # Apply dark header styling to both header cells
    for cell in (ws["A6"], ws["B6"]):
        cell.font = Font(bold=True)
        cell.fill = PatternFill(start_color="2E4057", end_color="2E4057", fill_type="solid")
        cell.font = Font(bold=True, color="FFFFFF")   # override to add white text

    # ---- Stats table rows (rows 7–10, one per tier) ----
    # enumerate(tiers, 7) gives row indices 7, 8, 9, 10
    for row_idx, tier in enumerate(tiers, 7):
        # Column A: the tier name, coloured to match its status (e.g. red for Dead)
        ws.cell(row=row_idx, column=1, value=tier).fill = _tier_fill(tier)
        # Column B: the count (0 if no URLs had that tier)
        ws.cell(row=row_idx, column=2, value=counts.get(tier, 0))

    # ---- Totals row (row 11) ----
    ws.cell(row=11, column=1, value="Total").font = Font(bold=True)
    ws.cell(row=11, column=2, value=len(results)).font = Font(bold=True)

    # ---- Bar chart ----
    chart = BarChart()
    chart.type = "col"   # "col" = vertical bars (as opposed to horizontal "bar")
    chart.title = "URL Status Breakdown"
    chart.y_axis.title = "Count"
    chart.x_axis.title = "Status"
    chart.shape = 4      # bar shape: rounded rectangle

    # Reference(ws, ...) tells the chart where to read data from.
    # Data is in column B (col=2), rows 6–10 (header + 4 data rows).
    data_ref = Reference(ws, min_col=2, min_row=6, max_row=10)
    # Categories (X-axis labels) are in column A, rows 7–10 (the tier names).
    cats_ref = Reference(ws, min_col=1, min_row=7, max_row=10)
    chart.add_data(data_ref, titles_from_data=True)   # row 6 is the series title
    chart.set_categories(cats_ref)
    chart.width = 15    # centimetres wide
    chart.height = 10   # centimetres tall
    ws.add_chart(chart, "D6")   # place the chart with its top-left corner at cell D6

    # Set column widths so nothing is clipped
    ws.column_dimensions["A"].width = 18
    ws.column_dimensions["B"].width = 10


# -----------------------------------------------------------------------------
# _write_details — Fill the "Details" worksheet
# -----------------------------------------------------------------------------

def _write_details(ws, results: list) -> None:
    """
    Write one row per URL to the Details sheet.
    Columns are colour-coded by tier, and URL cells are formatted as clickable links.
    Results are sorted worst-first (Dead before Suspicious before Alive before Skipped).
    """
    # Define all column headings in left-to-right order
    headers = [
        "Status", "Original URL", "Final URL", "HTTP Code",
        "Source File", "Location", "Context", "Response Time (ms)",
        "Redirects", "Reason", "Wayback Snapshot", "Wayback Date", "Redirect Chain",
        "EPA Internal", "Checked At",
    ]

    # Write header row (row 1) and apply dark header styling to each cell
    for col, header in enumerate(headers, 1):   # enumerate starts column count at 1
        _header_style(ws.cell(row=1, column=col), header)

    # freeze_panes="A2" locks row 1 (the header) so it stays visible when scrolling down
    ws.freeze_panes = "A2"

    # Sort results by severity: Dead (0) → Suspicious (1) → Alive (2) → Skipped (3)
    sorted_results = sorted(results, key=lambda r: SEVERITY_ORDER.get(r.tier, 99))

    # Write one row per URL result, starting at row 2 (row 1 is the header)
    for row_idx, r in enumerate(sorted_results, 2):
        # Use the first location if this URL appeared in multiple places
        primary = r.locations[0] if r.locations else None

        # Build the redirect chain as a readable string:
        # [(301, "http://old.gov"), (302, "https://new.gov")] →
        # "301 http://old.gov → 302 https://new.gov"
        chain_str = " → ".join("{} {}".format(code, url) for code, url in r.redirect_chain) if r.redirect_chain else ""

        # If the URL appeared in multiple files, list all of them (not used in cells here
        # but available for future expansion)
        all_locations = "; ".join(
            "{} [{}]".format(loc.source_file, loc.location) for loc in r.locations
        ) if len(r.locations) > 1 else ""

        # Build the list of cell values in the same order as the headers list
        values = [
            r.tier,                                 # col 1:  Status
            r.url,                                  # col 2:  Original URL (made clickable below)
            r.final_url or "",                      # col 3:  Final URL (made clickable below)
            r.status_code or "",                    # col 4:  HTTP Code
            primary.source_file if primary else "", # col 5:  Source File
            primary.location if primary else "",    # col 6:  Location (e.g. "Page 3")
            primary.context if primary else "",     # col 7:  Context snippet
            r.response_time_ms,                     # col 8:  Response Time
            r.redirect_count,                       # col 9:  Number of redirects
            r.reason or "",                         # col 10: Why it was flagged
            r.wayback_url or ("No snapshot found" if r.tier == "Dead" else ""),  # col 11: Wayback link
            r.wayback_snapshot_date or "",          # col 12: Wayback date
            chain_str,                              # col 13: Full redirect chain text
            "Yes" if r.is_epa_internal else "No",  # col 14: EPA Internal?
            r.checked_at.strftime("%Y-%m-%d %H:%M UTC"),  # col 15: When checked
        ]

        # Get the background fill colour for this tier (e.g. red for Dead)
        fill = _tier_fill(r.tier)

        # Write each value into the row and apply formatting
        for col, val in enumerate(values, 1):
            cell = ws.cell(row=row_idx, column=col, value=val)
            cell.alignment = Alignment(wrap_text=False, vertical="top")

            # Only the Status column (col 1) gets the tier background colour
            if col == 1:
                cell.fill = fill

            # Column 2: Original URL — make it a clickable hyperlink in Excel.
            # Excel's HYPERLINK() formula syntax: =HYPERLINK("url","display text")
            if col == 2 and r.url.startswith("http"):
                cell.value = '=HYPERLINK("{}","{}")'.format(r.url, r.url)
                cell.font = Font(color="0563C1", underline="single")   # blue underline

            # Column 3: Final URL (destination after redirects) — also clickable
            if col == 3 and r.final_url and r.final_url.startswith("http"):
                cell.value = '=HYPERLINK("{}","{}")'.format(r.final_url, r.final_url)
                cell.font = Font(color="0563C1", underline="single")

            # Column 11: Wayback snapshot URL — clickable with friendly label
            if col == 11 and r.wayback_url:
                label = "View snapshot"
                cell.value = '=HYPERLINK("{}","{}")'.format(r.wayback_url, label)
                cell.font = Font(color="0563C1", underline="single")

    # Set each column's width (in character units) so content is readable without manual resizing.
    # The list order matches the headers list: Status, Original URL, Final URL, etc.
    col_widths = [12, 50, 40, 10, 20, 20, 40, 18, 10, 40, 40, 16, 50, 12, 20]
    for col, width in enumerate(col_widths, 1):
        ws.column_dimensions[get_column_letter(col)].width = width
