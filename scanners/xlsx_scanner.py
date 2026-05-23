import logging
import uuid
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile

import openpyxl

from scanners.base import Finding, Severity
from utils.wcag_refs import get_refs

logger = logging.getLogger(__name__)

_DEFAULT_SHEET_NAMES = {"sheet1", "sheet2", "sheet3", "sheet4", "sheet5"}


def _f(rule: str, title: str, description: str, location: str,
       snippet: str = None, fix: str = None) -> Finding:
    wcag_sc, sec508_ref, severity = get_refs(rule)
    return Finding(
        id=str(uuid.uuid4())[:8],
        rule=rule,
        wcag_sc=wcag_sc,
        sec508_ref=sec508_ref,
        severity=severity,
        title=title,
        description=description,
        location=location,
        snippet=snippet,
        suggested_fix=fix,
        source="deterministic",
    )


def _check_workbook_title(wb: openpyxl.Workbook, file_path: str) -> list[Finding]:
    findings = []
    props = wb.properties
    if not props or not props.title or str(props.title).strip() == "":
        findings.append(_f(
            "xlsx-no-title",
            "Workbook title not set",
            "The workbook has no title in its document properties. A descriptive title helps users identify the file.",
            "Workbook properties",
            fix="In Excel: File → Info → Properties → Title. Set a meaningful title.",
        ))
    return findings


def _check_sheet_names(wb: openpyxl.Workbook) -> list[Finding]:
    findings = []
    for ws in wb.worksheets:
        if ws.title.lower() in _DEFAULT_SHEET_NAMES:
            findings.append(_f(
                "xlsx-default-sheet-name",
                f"Default sheet name '{ws.title}' is not descriptive",
                f"Sheet '{ws.title}' uses a default name. Descriptive sheet names help users and assistive tech navigate the workbook.",
                f"Sheet: '{ws.title}'",
                fix=f"Rename sheet '{ws.title}' to something that describes its contents.",
            ))
    return findings


def _check_table_structure(wb: openpyxl.Workbook) -> list[Finding]:
    findings = []
    for ws in wb.worksheets:
        if not ws.tables:
            # Check if there's data that looks tabular but not formatted as a Table
            max_row = ws.max_row or 0
            max_col = ws.max_column or 0
            if max_row >= 3 and max_col >= 2:
                findings.append(_f(
                    "xlsx-no-table-structure",
                    f"Sheet '{ws.title}' has data but no defined Excel Table",
                    f"Sheet '{ws.title}' contains data ({max_row} rows × {max_col} cols) but no Excel Table object. Without a Table, screen readers cannot identify column headers.",
                    f"Sheet: '{ws.title}'",
                    fix="Select the data range → Insert → Table (check 'My table has headers'). This creates a structured Table object.",
                ))
        else:
            for tbl in ws.tables.values():
                if not tbl.headerRowCount or tbl.headerRowCount == 0:
                    findings.append(_f(
                        "xlsx-no-table-structure",
                        f"Table '{tbl.name}' has no header row",
                        f"Excel Table '{tbl.name}' on sheet '{ws.title}' has headerRowCount=0. Screen readers use the header row to identify column names.",
                        f"Sheet: '{ws.title}', Table: '{tbl.name}'",
                        fix=f"Ensure the Table '{tbl.name}' has 'Header Row' checked in Table Design.",
                    ))
    return findings


def _check_merged_cells(wb: openpyxl.Workbook) -> list[Finding]:
    findings = []
    for ws in wb.worksheets:
        data_ranges = set()
        for tbl in ws.tables.values():
            data_ranges.add(tbl.ref)

        for merged_range in ws.merged_cells.ranges:
            # Flag merges that are inside a table data range
            merged_str = str(merged_range)
            findings.append(_f(
                "xlsx-merged-cells",
                f"Merged cells in sheet '{ws.title}'",
                f"Merged cell range {merged_str} in sheet '{ws.title}' can break screen reader table navigation. Assistive tech may mis-read the row/column span.",
                f"Sheet: '{ws.title}', Range: {merged_str}",
                fix=f"Unmerge cells in {merged_str}. Use centered alignment instead of merging, or restructure the data.",
            ))
    return findings


def _check_image_alt_text(file_path: str, wb: openpyxl.Workbook) -> list[Finding]:
    """Check alt text on images/charts by inspecting the xlsx XML directly."""
    findings = []
    try:
        with ZipFile(file_path) as z:
            for name in z.namelist():
                if not (name.startswith("xl/drawings/") and name.endswith(".xml")):
                    continue
                sheet_name = "Unknown"
                # Try to map drawing to sheet name
                try:
                    drawing_idx = name.split("drawing")[-1].replace(".xml", "")
                    ws_list = wb.worksheets
                    idx = int(drawing_idx) - 1
                    if 0 <= idx < len(ws_list):
                        sheet_name = ws_list[idx].title
                except Exception:
                    pass

                try:
                    xml_content = z.read(name)
                    root = ET.fromstring(xml_content)
                    ns = {
                        "xdr": "http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing",
                        "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
                    }
                    for cnv_pr in root.iter("{http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing}cNvPr"):
                        descr = cnv_pr.get("descr", "").strip()
                        name_attr = cnv_pr.get("name", "image")
                        if not descr:
                            findings.append(_f(
                                "xlsx-image-alt-missing",
                                f"Image '{name_attr}' missing alt text",
                                f"Image or chart '{name_attr}' on sheet '{sheet_name}' has no alt text. Screen readers cannot convey its content.",
                                f"Sheet: '{sheet_name}', Object: '{name_attr}'",
                                fix="Right-click the image/chart → Edit Alt Text → enter a meaningful description.",
                            ))
                except Exception as e:
                    logger.debug("Drawing XML parse error in %s: %s", name, e)
    except Exception as e:
        logger.warning("Could not inspect XLSX drawing XML: %s", e)
    return findings


def scan_xlsx(file_path: str) -> list[Finding]:
    findings: list[Finding] = []
    try:
        wb = openpyxl.load_workbook(file_path, data_only=True)
    except Exception as e:
        logger.error("Could not open XLSX %s: %s", file_path, e)
        return findings

    findings.extend(_check_workbook_title(wb, file_path))
    findings.extend(_check_sheet_names(wb))
    findings.extend(_check_table_structure(wb))
    findings.extend(_check_merged_cells(wb))
    findings.extend(_check_image_alt_text(file_path, wb))

    return findings
