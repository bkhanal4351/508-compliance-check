# url_checker.py — FastAPI routes for the URL dead-link checker.
#
# This file defines three HTTP endpoints:
#
#   POST /api/urlcheck/check         — Accepts one or more uploaded documents,
#                                      extracts all URLs from them, checks each
#                                      URL asynchronously, and returns results.
#
#   POST /api/urlcheck/export/csv    — Accepts a results list, generates a CSV,
#                                      and returns it as a file download.
#
#   POST /api/urlcheck/export/excel  — Same but returns a .xlsx Excel file.
#
# The extraction + checking logic lives in url_checker/ at the project root.
# That directory was added to sys.path in backend/main.py, so imports like
# "from extractors.base import ..." resolve correctly here.

import asyncio
import importlib     # lets us import a module by name as a string (used for extractor lookup)
import os
import tempfile
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import Response

# ── url_checker domain imports ────────────────────────────────────────────────
# These modules live in url_checker/ (added to sys.path in main.py).
from exporters.csv_exporter   import export_csv     # builds a CSV from CheckResult list
from exporters.excel_exporter import export_excel   # builds an Excel file from CheckResult list
from url_checker_utils.constants import SUPPORTED_EXTENSIONS  # set of allowed file extensions
from validators.url_checker   import check_urls, group_by_url # the async HTTP checking engine

router = APIRouter()

# ── Extractor map ─────────────────────────────────────────────────────────────
# Maps each supported file extension to the dotted import path of its extractor class.
# We use a string + importlib so we don't have to import all six extractor classes
# at module load time (keeps startup fast and avoids loading heavy libraries eagerly).
_EXTRACTOR_MAP = {
    ".docx": "extractors.docx_extractor.DocxExtractor",
    ".pdf":  "extractors.pdf_extractor.PdfExtractor",
    ".pptx": "extractors.pptx_extractor.PptxExtractor",
    ".xlsx": "extractors.xlsx_extractor.XlsxExtractor",
    ".txt":  "extractors.text_extractor.TextExtractor",
    ".html": "extractors.text_extractor.TextExtractor",  # HTML uses the text extractor
    ".htm":  "extractors.text_extractor.TextExtractor",
}


def _get_extractor(suffix: str, file_path: str):
    """
    Given a file extension and file path, return an instantiated extractor object.

    Example: _get_extractor(".docx", "/tmp/abc.docx")
      → imports extractors.docx_extractor
      → instantiates DocxExtractor("/tmp/abc.docx")
      → returns that object

    Returns None if no extractor exists for the extension.
    """
    spec = _EXTRACTOR_MAP.get(suffix)    # e.g. "extractors.docx_extractor.DocxExtractor"
    if not spec:
        return None

    # Split "extractors.docx_extractor.DocxExtractor" into module path + class name
    module_path, cls_name = spec.rsplit(".", 1)   # → ("extractors.docx_extractor", "DocxExtractor")

    mod = importlib.import_module(module_path)   # equivalent to: import extractors.docx_extractor
    cls = getattr(mod, cls_name)                 # get the class object from the module
    return cls(file_path)                        # instantiate the extractor with the file path


# ── Route: check URLs in uploaded documents ───────────────────────────────────

@router.post("/check")
async def check_urls_endpoint(
    files: list[UploadFile] = File(...),   # one or more uploaded files (multipart)
    timeout: float   = Form(10.0),        # seconds to wait per URL
    max_workers: int = Form(20),          # how many URLs to check in parallel
    fetch_titles: bool = Form(False),     # whether to also fetch <title> tags
    retry: bool      = Form(True),        # retry once on 5xx / 429 errors
):
    """
    End-to-end URL checking pipeline:
      1. Save each uploaded file to a temp file on disk.
      2. Pick the right extractor and run it → produces ExtractedUrl objects.
      3. group_by_url() deduplicates so each unique URL is only checked once.
      4. check_urls() visits every URL asynchronously (like a browser) and
         classifies each as Alive / Suspicious / Dead / Skipped.
      5. Return the results + summary + any warnings.
    """
    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded")

    all_extracted = []   # will accumulate ExtractedUrl objects from all documents
    warnings = []        # non-fatal messages (unsupported format, file too big, etc.)
    tmp_paths = []       # track temp file paths so we can delete them in finally

    # ── Step 1 + 2: save each file and extract its URLs ──────────────────────
    for uf in files:
        suffix = Path(uf.filename).suffix.lower()   # e.g. ".docx"

        # Reject unsupported file types
        if suffix not in SUPPORTED_EXTENSIONS:
            warnings.append(f"{uf.filename}: unsupported format ({suffix})")
            continue

        # Read the uploaded bytes (UploadFile is an async stream)
        content = await uf.read()

        # Reject files over 50 MB to prevent out-of-memory errors
        size_mb = len(content) / (1024 * 1024)
        if size_mb > 50:
            warnings.append(f"{uf.filename}: file too large ({size_mb:.1f} MB, max 50 MB)")
            continue

        # Write to a temp file (extractor libraries need a real path, not bytes)
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(content)
            tmp_path = tmp.name
        tmp_paths.append(tmp_path)

        extractor = _get_extractor(suffix, tmp_path)
        if extractor is None:
            warnings.append(f"{uf.filename}: no extractor available")
            continue

        try:
            extracted = extractor.extract()   # returns List[ExtractedUrl]

            # Replace the temp path in source_file with the original upload name,
            # so results show "policy.docx" not "/tmp/tmpXYZ.docx"
            for e in extracted:
                e.source_file = uf.filename

            all_extracted.extend(extracted)   # add to master list
        except Exception as exc:
            warnings.append(f"{uf.filename}: extraction error — {exc}")

    # ── Clean up temp files ──────────────────────────────────────────────────
    for p in tmp_paths:
        try:
            os.unlink(p)
        except OSError:
            pass

    # ── Early return if nothing was extracted ────────────────────────────────
    if not all_extracted:
        return {"results": [], "summary": _empty_summary(), "warnings": warnings}

    # ── Step 3: deduplicate ──────────────────────────────────────────────────
    # group_by_url() produces { canonical_url: [list of UrlLocation objects] }
    # so each URL is checked only once, even if it appears in multiple documents.
    url_groups = group_by_url(all_extracted)

    # ── Step 4: check all URLs ───────────────────────────────────────────────
    # check_urls() is synchronous internally (it uses its own thread for async).
    # We run it in a thread here to avoid blocking FastAPI's event loop.
    try:
        results = await asyncio.to_thread(
            check_urls,
            url_groups,
            timeout=timeout,
            max_workers=max_workers,
            fetch_titles=fetch_titles,
            retry=retry,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    # ── Step 5: build and return response ────────────────────────────────────
    summary = _build_summary(results)
    return {
        "results":  [_result_to_dict(r) for r in results],  # serialise CheckResult objects
        "summary":  summary,
        "warnings": warnings,
    }


# ── Route: export URL results as CSV ─────────────────────────────────────────

@router.post("/export/csv")
async def export_csv_endpoint(request: dict):
    """
    Accepts a { results: [...] } JSON body, reconstructs CheckResult objects,
    and returns a CSV file download.
    """
    results_data = request.get("results", [])
    results = _dicts_to_results(results_data)   # deserialise plain dicts → CheckResult objects

    # export_csv() is synchronous — run it in a background thread
    csv_bytes = await asyncio.to_thread(export_csv, results)

    return Response(
        content=csv_bytes,   # export_csv already returns bytes
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=url_check_results.csv"},
    )


# ── Route: export URL results as Excel ───────────────────────────────────────

@router.post("/export/excel")
async def export_excel_endpoint(request: dict):
    """
    Same as the CSV endpoint but produces a .xlsx Excel file with formatted columns.
    """
    results_data = request.get("results", [])
    results = _dicts_to_results(results_data)

    excel_bytes = await asyncio.to_thread(export_excel, results)

    return Response(
        content=excel_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=url_check_results.xlsx"},
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _empty_summary() -> dict:
    """Returns a zero-count summary dict when no URLs were found."""
    return {"Dead": 0, "Suspicious": 0, "Alive": 0, "Skipped": 0, "total": 0}


def _build_summary(results) -> dict:
    """
    Counts how many results fall into each tier (Dead / Suspicious / Alive / Skipped).
    Also includes a 'total' count.
    """
    s = _empty_summary()
    for r in results:
        if r.tier in s:
            s[r.tier] += 1     # increment the counter for this tier
        s["total"] += 1        # always increment total
    return s


def _result_to_dict(r) -> dict:
    """
    Converts a CheckResult dataclass to a plain dict that JSON can serialise.
    datetime objects must be converted to ISO strings; everything else serialises as-is.
    """
    return {
        "url":                   r.url,
        "final_url":             r.final_url,
        "status_code":           r.status_code,
        "tier":                  r.tier,
        "redirect_count":        r.redirect_count,
        "redirect_chain":        r.redirect_chain,    # list of [status_code, url] pairs
        "response_time_ms":      r.response_time_ms,
        "error_type":            r.error_type,
        "reason":                r.reason,
        "page_title":            r.page_title,
        "is_epa_internal":       r.is_epa_internal,
        "wayback_url":           r.wayback_url,
        "wayback_snapshot_date": r.wayback_snapshot_date,
        "checked_at":            r.checked_at.isoformat() if r.checked_at else None,
        "locations": [
            {
                "source_file": loc.source_file,
                "location":    loc.location,
                "context":     loc.context,
                "link_type":   loc.link_type,
            }
            for loc in r.locations    # list of every place this URL appeared in documents
        ],
    }


def _dicts_to_results(data: list):
    """
    Converts a list of plain dicts (from a JSON request body) back into
    CheckResult dataclass instances so the exporter functions work with them.

    This is the reverse operation of _result_to_dict().
    """
    from extractors.base import CheckResult, UrlLocation
    from datetime import datetime

    results = []
    for d in data:
        # Reconstruct each UrlLocation from its dict representation
        locs = [
            UrlLocation(
                source_file=loc.get("source_file", ""),
                location=   loc.get("location", ""),
                context=    loc.get("context", ""),
                link_type=  loc.get("link_type", ""),
            )
            for loc in d.get("locations", [])
        ]

        # Parse the ISO timestamp string back to a datetime object
        checked_at_raw = d.get("checked_at")
        checked_at = datetime.fromisoformat(checked_at_raw) if checked_at_raw else datetime.utcnow()

        results.append(CheckResult(
            url=               d["url"],
            final_url=         d.get("final_url"),
            status_code=       d.get("status_code"),
            tier=              d.get("tier", "Dead"),
            redirect_count=    d.get("redirect_count", 0),
            redirect_chain=    d.get("redirect_chain", []),
            response_time_ms=  d.get("response_time_ms", 0.0),
            error_type=        d.get("error_type"),
            reason=            d.get("reason"),
            page_title=        d.get("page_title"),
            is_epa_internal=   d.get("is_epa_internal", False),
            wayback_url=       d.get("wayback_url"),
            wayback_snapshot_date=d.get("wayback_snapshot_date"),
            locations=         locs,
            checked_at=        checked_at,
        ))

    return results
