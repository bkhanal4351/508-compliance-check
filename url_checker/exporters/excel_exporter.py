import io
from datetime import datetime

from openpyxl import Workbook
from openpyxl.chart import BarChart, Reference
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from extractors.base import CheckResult
from utils.constants import SEVERITY_ORDER, TIER_EXCEL_FILLS


def _tier_fill(tier: str) -> PatternFill:
    hex_color = TIER_EXCEL_FILLS.get(tier, "FFFFFF")
    return PatternFill(start_color=hex_color, end_color=hex_color, fill_type="solid")


def _header_style(cell, text: str) -> None:
    cell.value = text
    cell.font = Font(bold=True, color="FFFFFF")
    cell.fill = PatternFill(start_color="2E4057", end_color="2E4057", fill_type="solid")
    cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)


def export_excel(
    results: list[CheckResult],
    settings: dict,
    source_names: list[str],
) -> bytes:
    """Return Excel workbook as bytes (write to in-memory buffer)."""
    wb = Workbook()
    ws_summary = wb.active
    ws_summary.title = "Summary"
    _write_summary(ws_summary, results, settings, source_names)

    ws_details = wb.create_sheet("Details")
    _write_details(ws_details, results)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _write_summary(ws, results: list[CheckResult], settings: dict, source_names: list[str]) -> None:
    from collections import Counter
    counts = Counter(r.tier for r in results)
    tiers = ["Dead", "Suspicious", "Alive", "Skipped"]

    # Title
    ws["A1"] = "URL Check Report"
    ws["A1"].font = Font(bold=True, size=16)
    ws["A2"] = f"Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}"
    ws["A3"] = f"Files scanned: {', '.join(source_names)}"
    ws["A4"] = f"Settings — Timeout: {settings.get('timeout', 10)}s  |  Workers: {settings.get('max_workers', 20)}  |  Retry: {settings.get('retry', True)}"

    # Stats table header
    ws["A6"] = "Status"
    ws["B6"] = "Count"
    for cell in (ws["A6"], ws["B6"]):
        cell.font = Font(bold=True)
        cell.fill = PatternFill(start_color="2E4057", end_color="2E4057", fill_type="solid")
        cell.font = Font(bold=True, color="FFFFFF")

    for row_idx, tier in enumerate(tiers, 7):
        ws.cell(row=row_idx, column=1, value=tier).fill = _tier_fill(tier)
        ws.cell(row=row_idx, column=2, value=counts.get(tier, 0))

    ws.cell(row=11, column=1, value="Total").font = Font(bold=True)
    ws.cell(row=11, column=2, value=len(results)).font = Font(bold=True)

    # Bar chart
    chart = BarChart()
    chart.type = "col"
    chart.title = "URL Status Breakdown"
    chart.y_axis.title = "Count"
    chart.x_axis.title = "Status"
    chart.shape = 4

    data_ref = Reference(ws, min_col=2, min_row=6, max_row=10)
    cats_ref = Reference(ws, min_col=1, min_row=7, max_row=10)
    chart.add_data(data_ref, titles_from_data=True)
    chart.set_categories(cats_ref)
    chart.width = 15
    chart.height = 10
    ws.add_chart(chart, "D6")

    ws.column_dimensions["A"].width = 18
    ws.column_dimensions["B"].width = 10


def _write_details(ws, results: list[CheckResult]) -> None:
    headers = [
        "Status", "Original URL", "Final URL", "HTTP Code",
        "Source File", "Location", "Context", "Response Time (ms)",
        "Redirects", "Reason", "Redirect Chain", "EPA Internal", "Checked At",
    ]

    for col, header in enumerate(headers, 1):
        _header_style(ws.cell(row=1, column=col), header)

    ws.freeze_panes = "A2"

    sorted_results = sorted(results, key=lambda r: SEVERITY_ORDER.get(r.tier, 99))

    for row_idx, r in enumerate(sorted_results, 2):
        primary = r.locations[0] if r.locations else None
        chain_str = " → ".join(f"{code} {url}" for code, url in r.redirect_chain) if r.redirect_chain else ""
        all_locations = "; ".join(
            f"{loc.source_file} [{loc.location}]" for loc in r.locations
        ) if len(r.locations) > 1 else ""

        values = [
            r.tier,
            r.url,
            r.final_url or "",
            r.status_code or "",
            primary.source_file if primary else "",
            primary.location if primary else "",
            primary.context if primary else "",
            r.response_time_ms,
            r.redirect_count,
            r.reason or "",
            chain_str,
            "Yes" if r.is_epa_internal else "No",
            r.checked_at.strftime("%Y-%m-%d %H:%M UTC"),
        ]

        fill = _tier_fill(r.tier)
        for col, val in enumerate(values, 1):
            cell = ws.cell(row=row_idx, column=col, value=val)
            cell.alignment = Alignment(wrap_text=False, vertical="top")
            if col == 1:
                cell.fill = fill
            # Make URLs clickable
            if col == 2 and r.url.startswith("http"):
                cell.value = f'=HYPERLINK("{r.url}","{r.url}")'
                cell.font = Font(color="0563C1", underline="single")
            if col == 3 and r.final_url and r.final_url.startswith("http"):
                cell.value = f'=HYPERLINK("{r.final_url}","{r.final_url}")'
                cell.font = Font(color="0563C1", underline="single")

    # Auto-width (capped)
    col_widths = [12, 50, 40, 10, 20, 20, 40, 18, 10, 40, 50, 12, 20]
    for col, width in enumerate(col_widths, 1):
        ws.column_dimensions[get_column_letter(col)].width = width
