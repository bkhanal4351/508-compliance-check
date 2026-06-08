# scanner_508.py — FastAPI routes for 508 / WCAG accessibility scanning.
#
# This file defines four HTTP endpoints:
#
#   POST /api/scan/url         — Scans a live web page (or whole site) using
#                                Playwright + axe-core.  Returns a list of findings.
#
#   POST /api/scan/document    — Accepts an uploaded file (PDF, DOCX, PPTX, XLSX,
#                                or image), runs the appropriate scanner, and
#                                returns findings in the same format as /url.
#
#   POST /api/scan/export/pdf  — Accepts findings JSON, generates a formatted PDF
#                                report, and streams the bytes back for download.
#
#   POST /api/scan/export/csv  — Same but returns a CSV text file.
#
# The actual scanning logic lives in scanners/ and report/ at the project root.
# This file is just the "glue" that connects HTTP requests to those modules.

import asyncio       # Python's async library — used to run sync scanner code in threads
import os            # used to delete temporary files after we're done with them
import tempfile      # creates temporary files on disk for uploaded documents
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

# ── Import the domain modules at the project root ─────────────────────────────
# These are the same Python modules the old Streamlit app used.
# We reuse them here so no scanning logic needs to be rewritten.
from report.builder import build_report        # deduplicates + sorts findings into a report dict
from report.pdf_export import export_csv, export_pdf  # generate PDF / CSV output files
from scanners.base import Finding              # the Pydantic model that describes one accessibility issue
from scanners.docx_scanner import scan_docx   # scans .docx files for 508 issues
from scanners.image import scan_image         # scans image files for missing alt text etc.
from scanners.pdf import scan_pdf             # scans .pdf files using pikepdf
from scanners.pptx_scanner import scan_pptx  # scans .pptx files
from scanners.web import scan_url             # scans web pages with Playwright + axe-core
from scanners.xlsx_scanner import scan_xlsx   # scans .xlsx files

# APIRouter is like a mini-app — it groups related routes together.
# In main.py, this router is mounted with prefix "/api/scan",
# so a route defined as "/url" here becomes "/api/scan/url".
router = APIRouter()

# Maps file extensions to the right scanner function.
# When a file is uploaded, we look up its extension here to pick the scanner.
_DOC_SCANNERS = {
    ".pdf":  scan_pdf,
    ".docx": scan_docx,
    ".pptx": scan_pptx,
    ".xlsx": scan_xlsx,
}

# Image extensions — all use the same scan_image function
_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff", ".webp"}


# ── Request / Response models ──────────────────────────────────────────────────
# Pydantic models describe the shape of data coming in (request bodies) and
# going out (responses).  FastAPI uses them to automatically parse JSON and
# validate that required fields are present.

class UrlScanRequest(BaseModel):
    """JSON body for POST /api/scan/url"""
    url: str                # The web address to scan, e.g. "https://epa.gov/page"
    crawl: bool = False     # If True, follow links and scan multiple pages
    max_depth: int = 1      # How many link-levels deep to crawl (1 = just direct links)
    max_pages: int = 25     # Hard cap on pages scanned in one run


class ExportRequest(BaseModel):
    """JSON body for POST /api/scan/export/pdf and /csv"""
    findings: List[dict]           # The findings array from a previous scan response
    summary: Optional[dict] = None # The summary dict { Critical, Serious, ... }
    scan_target: Optional[str] = "" # The URL or filename that was scanned
    scanned_at: Optional[str] = ""  # ISO timestamp from the original scan
    deduped_count: Optional[int] = 0  # How many duplicates were collapsed


# ── Route: scan a URL ─────────────────────────────────────────────────────────

@router.post("/url")
async def scan_url_endpoint(request: UrlScanRequest):
    """
    Scans a live web page for Section 508 / WCAG 2.1 AA issues.

    Steps:
      1. Receives the URL and crawl settings from the React frontend.
      2. Calls scan_url() (from scanners/web.py) inside a thread so the
         synchronous Playwright browser code doesn't block the async server.
      3. Passes all findings through build_report() to deduplicate and sort.
      4. Returns findings + summary JSON to the frontend.
    """
    try:
        # asyncio.to_thread() runs a synchronous function in a background thread.
        # This prevents Playwright (which is sync) from blocking FastAPI's event loop
        # while pages are loading.  Other requests can still be handled in the meantime.
        findings: list[Finding] = await asyncio.to_thread(
            scan_url,
            request.url,
            max_depth=request.max_depth if request.crawl else 0,  # 0 = single page only
            max_pages=request.max_pages,
        )

        # build_report() deduplicates (same rule + same location = one finding)
        # and sorts by severity (Critical first), then location alphabetically.
        report = build_report(findings, scan_target=request.url, scan_type="web")

        # Convert Finding Pydantic objects to plain dicts for JSON serialisation.
        # The helper _finding_dict() ensures enum values are converted to strings.
        return {
            "findings":      [_finding_dict(f) for f in report["findings"]],
            "summary":       report["summary"],
            "scanned_at":    report["scanned_at"],
            "deduped_count": report["deduped_count"],
        }
    except Exception as exc:
        # HTTPException sends an error response with a specific status code.
        # The React frontend checks res.ok and reads the 'detail' field on failure.
        raise HTTPException(status_code=500, detail=str(exc))


# ── Route: scan an uploaded document ─────────────────────────────────────────

@router.post("/document")
async def scan_document(file: UploadFile = File(...)):
    """
    Receives an uploaded document, saves it to a temporary file,
    picks the right scanner based on the file extension, runs the scan,
    and returns findings.

    UploadFile is a FastAPI type that represents a multipart/form-data file upload.
    File(...) means the 'file' field is required (no default).
    """
    # Determine the file extension (lowercase) to pick the right scanner
    suffix = Path(file.filename).suffix.lower()

    if suffix not in _DOC_SCANNERS and suffix not in _IMAGE_EXTS:
        # Return HTTP 400 Bad Request if the file type isn't supported
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {suffix}")

    # Read the file bytes from the multipart stream into memory
    content = await file.read()

    # Write those bytes to a temporary file on disk.
    # The scanner libraries (pikepdf, python-docx, etc.) need a real file path,
    # not in-memory bytes, so we must save it to disk first.
    # delete=False means the OS won't auto-delete it — we do that ourselves in 'finally'.
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(content)
        tmp_path = tmp.name   # e.g. "/tmp/tmpXYZ123.pdf"

    try:
        # Run the appropriate scanner in a background thread (same reason as scan_url above)
        if suffix in _DOC_SCANNERS:
            findings: list[Finding] = await asyncio.to_thread(_DOC_SCANNERS[suffix], tmp_path)
        else:
            findings = await asyncio.to_thread(scan_image, tmp_path)

        report = build_report(findings, scan_target=file.filename, scan_type="document")
        return {
            "findings":      [_finding_dict(f) for f in report["findings"]],
            "summary":       report["summary"],
            "scanned_at":    report["scanned_at"],
            "deduped_count": report["deduped_count"],
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        # Always delete the temp file, even if an exception was raised.
        # Without this, temp files accumulate and eventually fill the disk.
        os.unlink(tmp_path)


# ── Route: export findings as PDF ─────────────────────────────────────────────

@router.post("/export/pdf")
async def export_pdf_endpoint(request: ExportRequest):
    """
    Generates a formatted PDF report from a findings list and streams it back.

    Steps:
      1. Reconstruct Finding objects from the raw dicts in the request body.
      2. Call export_pdf() (from report/pdf_export.py) which uses fpdf2 to
         build a multi-page PDF with severity cards and a findings table.
      3. export_pdf() requires a file path, so we write to a temp file,
         then read the bytes back and delete the temp file.
      4. Return the bytes with application/pdf headers so the browser downloads it.
    """
    # Reconstruct Finding Pydantic models from the raw dicts sent by the frontend
    findings = [Finding(**f) for f in request.findings]

    # Assemble the report dict that export_pdf() expects
    report = {
        "findings":      findings,
        "summary":       request.summary or {},
        "scan_target":   request.scan_target or "",
        "scanned_at":    request.scanned_at or "",
        "deduped_count": request.deduped_count or 0,
    }

    # Create a temp file to receive the PDF output (export_pdf writes to a path)
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        # Generate the PDF in a background thread (fpdf2 is synchronous)
        await asyncio.to_thread(export_pdf, report, tmp_path)

        # Read the generated PDF bytes into memory so we can return them
        pdf_bytes = Path(tmp_path).read_bytes()
    finally:
        os.unlink(tmp_path)   # clean up the temp file

    # Response() sends raw bytes with custom Content-Type.
    # Content-Disposition: attachment causes the browser to save it as a file
    # instead of trying to display it inline.
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=508_report.pdf"},
    )


# ── Route: export findings as CSV ─────────────────────────────────────────────

@router.post("/export/csv")
async def export_csv_endpoint(request: ExportRequest):
    """
    Generates a CSV of all findings and returns it as a text/csv download.

    export_csv() returns a Python string (CSV text).  We encode it as UTF-8 bytes
    before sending — that's what HTTP expects.
    """
    findings = [Finding(**f) for f in request.findings]
    report = {
        "findings":      findings,
        "summary":       request.summary or {},
        "scan_target":   request.scan_target or "",
        "scanned_at":    request.scanned_at or "",
        "deduped_count": request.deduped_count or 0,
    }

    # export_csv() returns a CSV string — run it in a thread even though it's fast,
    # to keep the async event loop fully non-blocking.
    csv_text: str = await asyncio.to_thread(export_csv, report)

    return Response(
        content=csv_text.encode("utf-8"),   # encode string → bytes
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=508_findings.csv"},
    )


# ── Helper ────────────────────────────────────────────────────────────────────

def _finding_dict(f: Finding) -> dict:
    """
    Converts a Finding Pydantic model to a plain Python dict.

    The 'severity' field is a Severity enum value (e.g. Severity.CRITICAL).
    JSON cannot represent Python enums, so we convert it to the string value
    (e.g. "Critical") before serialising.
    """
    d = f.model_dump()   # Pydantic's built-in method to convert model → dict
    d["severity"] = d["severity"].value if hasattr(d["severity"], "value") else d["severity"]
    return d
