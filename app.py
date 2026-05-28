# =============================================================================
# app.py — Combined EPA 508 Compliance + URL Checker
#
# Two tools in one application, selectable via tabs:
#   Tab 1 ♿  — Section 508 / WCAG 2.1 AA accessibility scanner
#               Accepts a URL to crawl or a document upload (PDF, DOCX,
#               PPTX, XLSX, images).  Produces a severity-ranked findings
#               report with PDF and CSV export.
#
#   Tab 2 🔗  — URL Checker
#               Accepts one or more document uploads, extracts every URL
#               (embedded hyperlinks + plain-text), checks each one for
#               dead / suspicious / alive status, and exports results.
#
# Run:  streamlit run app.py
# =============================================================================

import io
import logging
import queue
import sys
import tempfile
import threading
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
import streamlit as st
from PIL import Image

# ---------------------------------------------------------------------------
# sys.path setup
# ---------------------------------------------------------------------------
# The root directory holds the 508 scanner packages (scanners/, report/, utils/).
# url_checker/ holds the URL checker packages (extractors/, validators/, etc.).
# We renamed url_checker/utils/ → url_checker/url_checker_utils/ so the two
# "utils" packages don't shadow each other in sys.path.
ROOT = Path(__file__).parent
URL_CHECKER_DIR = ROOT / "url_checker"

for p in (str(ROOT), str(URL_CHECKER_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

# ---------------------------------------------------------------------------
# URL checker imports (resolved via URL_CHECKER_DIR in sys.path)
# ---------------------------------------------------------------------------
from extractors.base import CheckResult as UrlCheckResult, ExtractedUrl
from exporters.csv_exporter import export_csv as _export_url_csv
from exporters.excel_exporter import export_excel as _export_url_excel
from url_checker_utils.constants import (
    DEFAULT_MAX_WORKERS,
    DEFAULT_TIMEOUT,
    SEVERITY_ORDER,
    SUPPORTED_EXTENSIONS,
    TIER_BADGE_COLORS,
)
from url_checker_utils.url_utils import extract_plain_urls, get_context, normalize_url

logging.basicConfig(level=logging.INFO, stream=sys.stderr)

# ---------------------------------------------------------------------------
# Page config — must be the first Streamlit call
# ---------------------------------------------------------------------------
_epa_icon = Image.open(ROOT / "assets" / "epa_logo.png")

st.set_page_config(
    page_title="EPA 508 & URL Checker",
    page_icon=_epa_icon,
    layout="wide",
)

# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------
_STATE_DEFAULTS = {
    # 508 scanner
    "report_508":    None,
    # URL checker
    "url_results":   [],
    "url_run_ts":    None,
    "url_elapsed":   0.0,
    "url_source_names": [],
}
for _k, _v in _STATE_DEFAULTS.items():
    if _k not in st.session_state:
        st.session_state[_k] = _v

# ---------------------------------------------------------------------------
# Custom CSS
# ---------------------------------------------------------------------------
st.markdown("""
<style>
/* Vertically centre the logo with the title text */
[data-testid="stHorizontalBlock"] [data-testid="stImage"] {
    display: flex;
    align-items: center;
    height: 100%;
    padding-top: 8px;
}

/* Larger, bolder tab labels */
.stTabs [data-baseweb="tab"] p,
.stTabs [data-baseweb="tab"] span,
.stTabs [data-baseweb="tab"] div,
.stTabs button[role="tab"] p,
.stTabs button[role="tab"] {
    font-size: 1.6rem !important;
    font-weight: 800 !important;
    letter-spacing: 0.02em !important;
}
.stTabs [data-baseweb="tab"] {
    padding: 14px 36px !important;
}
.stTabs [data-baseweb="tab"][aria-selected="true"] p,
.stTabs [data-baseweb="tab"][aria-selected="true"] {
    color: #1a6b3c !important;
}
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Shared page header + tabs
# ---------------------------------------------------------------------------
_hdr_img, _hdr_txt = st.columns([1, 11])
with _hdr_img:
    st.image(str(ROOT / "assets" / "epa_logo.png"), width=68)
with _hdr_txt:
    st.title("EPA Compliance Tools")
    st.caption("Section 508 / WCAG accessibility scanning · Dead-link verification")

st.markdown("<div style='margin-bottom:28px'></div>", unsafe_allow_html=True)

tab_508, tab_url = st.tabs(["📋  508 Compliance Scanner", "🔗  URL Checker"])


# =============================================================================
# ██████████████████████████  TAB 1 — 508 SCANNER  ███████████████████████████
# =============================================================================

with tab_508:

    # Two-column layout: narrow controls on the left, results on the right
    ctrl_col, results_col = st.columns([1, 3], gap="large")

    # ── Controls ─────────────────────────────────────────────────────────────
    with ctrl_col:
        st.subheader("Scan settings")

        scan_type = st.radio(
            "Input type",
            ["URL", "Document Upload"],
            horizontal=True,
            key="scan_type_508",
        )

        if scan_type == "URL":
            url_input_508 = st.text_input(
                "URL to scan", placeholder="https://example.gov", key="url_508"
            )
            max_depth = st.slider("Crawl depth", 0, 3, 1, key="depth_508")
            max_pages = st.slider("Max pages", 1, 50, 25, key="pages_508")
            uploaded_file_508 = None

        else:
            url_input_508 = ""
            max_depth = 1
            max_pages = 25
            uploaded_file_508 = st.file_uploader(
                "Upload document",
                type=["pdf", "docx", "pptx", "xlsx", "png", "jpg", "jpeg"],
                key="uploader_508",
                help="Max 50 MB",
            )
            if uploaded_file_508 and uploaded_file_508.size > 50 * 1024 * 1024:
                st.warning("File exceeds 50 MB limit.")
                uploaded_file_508 = None
            if uploaded_file_508 and Path(uploaded_file_508.name).suffix.lower() in (
                ".png", ".jpg", ".jpeg", ".gif", ".webp"
            ):
                st.text_input(
                    "Image alt text (optional)",
                    key="image_alt_508",
                    placeholder="Describe the image",
                )

        st.divider()
        run_btn_508 = st.button(
            "▶ Run Scan",
            type="primary",
            use_container_width=True,
            key="run_btn_508",
            disabled=(
                (scan_type == "URL" and not url_input_508)
                or (scan_type == "Document Upload" and not uploaded_file_508)
            ),
        )

    # ── Results ──────────────────────────────────────────────────────────────
    with results_col:

        # Welcome message shown before any scan
        if st.session_state["report_508"] is None and not run_btn_508:
            st.markdown("""
This tool scans websites and documents for accessibility issues against
**Section 508** and **WCAG 2.1 AA** standards.

**What it checks:**
- 🌐 **Websites** — axe-core automated rules (alt text, contrast, labels, headings, links, ARIA)
- 📄 **PDFs** — tagged structure, language, title, form fields
- 📝 **DOCX** — headings, images, tables, hyperlinks, lists, language
- 📊 **PPTX** — slide titles, shape alt text, reading order, color contrast
- 📈 **XLSX** — workbook title, sheet names, table structure, merged cells, image alt text
- 🖼️ **Images** — alt text presence and quality check

Configure the scan in the **left panel** and click **▶ Run Scan**.
            """)

        # ── Execute scan ──────────────────────────────────────────────────
        if run_btn_508:
            findings_508 = []
            scan_target_508 = ""

            with st.status("Running 508 scan…", expanded=True) as _status_508:
                try:
                    if scan_type == "URL":
                        if not url_input_508 or not url_input_508.startswith("http"):
                            st.error("Please enter a valid URL starting with http:// or https://")
                        else:
                            from scanners.web import scan_url as _scan_url_508

                            _prog = st.progress(0, text="Starting scan…")

                            def _on_prog_508(i, total, page_url):
                                pct = int((i / max(total, 1)) * 100)
                                _prog.progress(
                                    pct,
                                    text="Scanning page {}/{}: {}".format(i + 1, total, page_url),
                                )

                            scan_target_508 = url_input_508
                            findings_508 = _scan_url_508(
                                url_input_508,
                                max_depth=max_depth,
                                max_pages=max_pages,
                                progress_callback=_on_prog_508,
                            )
                            _prog.progress(100, text="Scan complete")

                    else:
                        if not uploaded_file_508:
                            st.error("Please upload a file.")
                        else:
                            scan_target_508 = uploaded_file_508.name
                            st.info("Scanning {}…".format(uploaded_file_508.name))
                            ext = Path(uploaded_file_508.name).suffix.lower()

                            with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as _tmp:
                                _tmp.write(uploaded_file_508.read())
                                _tmp_path = _tmp.name

                            try:
                                if ext == ".pdf":
                                    from scanners.pdf import scan_pdf
                                    findings_508 = scan_pdf(_tmp_path)
                                elif ext == ".docx":
                                    from scanners.docx_scanner import scan_docx
                                    findings_508 = scan_docx(_tmp_path)
                                elif ext == ".pptx":
                                    from scanners.pptx_scanner import scan_pptx
                                    findings_508 = scan_pptx(_tmp_path)
                                elif ext == ".xlsx":
                                    from scanners.xlsx_scanner import scan_xlsx
                                    findings_508 = scan_xlsx(_tmp_path)
                                elif ext in (".png", ".jpg", ".jpeg", ".gif", ".webp"):
                                    from scanners.image import scan_image
                                    _alt = st.session_state.get("image_alt_508", "")
                                    findings_508 = scan_image(_tmp_path, provided_alt=_alt or None)
                                else:
                                    st.error("Unsupported file type: {}".format(ext))
                            finally:
                                Path(_tmp_path).unlink(missing_ok=True)

                except Exception as _e:
                    st.error("Scan failed: {}".format(_e))
                    logging.exception("508 scan error")

                _status_508.update(label="Scan complete ✅", state="complete")

            if scan_target_508:
                from report.builder import build_report as _build_508
                st.session_state["report_508"] = _build_508(
                    findings_508,
                    scan_target_508,
                    scan_type.lower().replace(" ", "_"),
                )

        # ── Display results ───────────────────────────────────────────────
        if st.session_state["report_508"] is not None:
            _report = st.session_state["report_508"]
            _summary = _report["summary"]
            _all_findings = _report["findings"]

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("🔴 Critical", _summary["Critical"])
            c2.metric("🟠 Serious",  _summary["Serious"])
            c3.metric("🔵 Moderate", _summary["Moderate"])
            c4.metric("🟢 Minor",    _summary["Minor"])

            if _report["deduped_count"] > 0:
                st.caption("{} duplicate finding(s) collapsed.".format(_report["deduped_count"]))

            st.divider()

            _fc1, _fc2 = st.columns([2, 3])
            with _fc1:
                _sev_filter = st.multiselect(
                    "Severity",
                    ["Critical", "Serious", "Moderate", "Minor"],
                    default=["Critical", "Serious", "Moderate", "Minor"],
                    key="sev_filter_508",
                )
            with _fc2:
                _search = st.text_input(
                    "Search findings", placeholder="rule, title, location…", key="search_508"
                )

            _filtered = [
                f for f in _all_findings
                if f.severity.value in _sev_filter
                and (
                    not _search
                    or _search.lower() in f.title.lower()
                    or _search.lower() in f.rule.lower()
                    or _search.lower() in f.location.lower()
                )
            ]

            st.caption("Showing {} of {} findings".format(len(_filtered), _summary["total"]))

            if _filtered:
                _df = pd.DataFrame([{
                    "Severity": f.severity.value,
                    "Title":    f.title,
                    "Location": f.location,
                    "WCAG SC":  f.wcag_sc,
                    "508 Ref":  f.sec508_ref,
                    "Rule":     f.rule,
                } for f in _filtered])
                st.dataframe(_df, use_container_width=True, hide_index=True)

                st.subheader("Finding Details")
                _sev_icons = {
                    "Critical": "🔴", "Serious": "🟠", "Moderate": "🔵", "Minor": "🟢"
                }
                for f in _filtered:
                    _icon = _sev_icons.get(f.severity.value, "⚪")
                    with st.expander(
                        "{} [{}] {} — {}".format(_icon, f.severity.value, f.title, f.location)
                    ):
                        st.markdown(
                            "**Rule:** `{}`  |  **WCAG:** {}  |  **508:** {}".format(
                                f.rule, f.wcag_sc, f.sec508_ref
                            )
                        )
                        st.markdown("**Description:** {}".format(f.description))
                        if f.snippet:
                            st.code(f.snippet, language="html")
                        if f.suggested_fix:
                            st.success("**Suggested fix:** {}".format(f.suggested_fix))
            else:
                st.info("No findings match the current filters.")

            st.divider()
            _dl1, _dl2 = st.columns(2)

            with _dl1:
                with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as _tp:
                    _tp_path = _tp.name
                try:
                    from report.pdf_export import export_pdf as _export_pdf_508
                    _export_pdf_508(_report, _tp_path)
                    with open(_tp_path, "rb") as _f:
                        _pdf_bytes = _f.read()
                    st.download_button(
                        "⬇ Download PDF Report",
                        data=_pdf_bytes,
                        file_name="508_scan_report.pdf",
                        mime="application/pdf",
                        use_container_width=True,
                        key="dl_pdf_508",
                    )
                except Exception as _e:
                    st.warning("PDF export failed: {}".format(_e))
                finally:
                    Path(_tp_path).unlink(missing_ok=True)

            with _dl2:
                from report.pdf_export import export_csv as _export_csv_508
                st.download_button(
                    "⬇ Download CSV",
                    data=_export_csv_508(_report),
                    file_name="508_scan_findings.csv",
                    mime="text/csv",
                    use_container_width=True,
                    key="dl_csv_508",
                )


# =============================================================================
# ████████████████████████  TAB 2 — URL CHECKER  █████████████████████████████
# =============================================================================

# ── Helper functions (URL checker) ───────────────────────────────────────────

def _url_badge(tier):
    """Coloured inline HTML badge for a status tier."""
    color = TIER_BADGE_COLORS.get(tier, "#888888")
    return (
        '<span style="background:{};color:#fff;padding:2px 8px;'
        'border-radius:4px;font-size:0.8em;font-weight:bold">{}</span>'
    ).format(color, tier)


def _get_url_extractor(suffix, file_path):
    """Return the correct extractor instance for a file extension."""
    from extractors.docx_extractor import DocxExtractor
    from extractors.pdf_extractor import PdfExtractor
    from extractors.pptx_extractor import PptxExtractor
    from extractors.text_extractor import TextExtractor
    from extractors.xlsx_extractor import XlsxExtractor

    mapping = {
        ".docx": DocxExtractor,
        ".pdf":  PdfExtractor,
        ".pptx": PptxExtractor,
        ".xlsx": XlsxExtractor,
        ".txt":  TextExtractor,
        ".html": TextExtractor,
        ".htm":  TextExtractor,
    }
    cls = mapping.get(suffix)
    return cls(file_path) if cls else None


def _extract_urls_from_uploads(uploaded_files):
    """
    Save each uploaded file to disk, run the extractor, and collect all URLs.
    Returns (list_of_ExtractedUrl, list_of_warning_strings).
    """
    all_extracted = []
    warnings = []

    for uf in uploaded_files:
        suffix = Path(uf.name).suffix.lower()
        if suffix not in SUPPORTED_EXTENSIONS:
            warnings.append("{}: unsupported format ({})".format(uf.name, suffix))
            continue

        size_mb = uf.size / (1024 * 1024)
        if size_mb > 50:
            warnings.append("{}: too large ({:.1f} MB, max 50 MB)".format(uf.name, size_mb))
            continue

        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(uf.read())
            tmp_path = tmp.name

        extractor = _get_url_extractor(suffix, tmp_path)
        if extractor is None:
            warnings.append("{}: no extractor available".format(uf.name))
            continue

        try:
            extracted = extractor.extract()
            for e in extracted:
                e.source_file = uf.name
            all_extracted.extend(extracted)
        except Exception as ex:
            warnings.append("{}: extraction error — {}".format(uf.name, ex))

    return all_extracted, warnings


def _url_results_to_df(results):
    """Convert CheckResult list to a pandas DataFrame for the results table."""
    rows = []
    for r in results:
        primary = r.locations[0] if r.locations else None
        rows.append({
            "Status":        r.tier,
            "Original URL":  r.url,
            "Final URL":     r.final_url or "",
            "HTTP Code":     str(r.status_code) if r.status_code else "",
            "Source File":   primary.source_file if primary else "",
            "Location":      primary.location if primary else "",
            "Context":       primary.context if primary else "",
            "Response (ms)": r.response_time_ms,
            "Reason":        r.reason or "",
            "EPA Internal":  "Yes" if r.is_epa_internal else "No",
        })
    df = pd.DataFrame(rows)
    if not df.empty:
        df["_sort"] = df["Status"].map(lambda t: SEVERITY_ORDER.get(t, 99))
        df = df.sort_values("_sort").drop(columns=["_sort"]).reset_index(drop=True)
    return df


def _do_url_run(files, timeout, max_workers, fetch_titles, retry, recheck_only=None):
    """
    Run the full URL check pipeline (extract → deduplicate → check → save results).
    If recheck_only is a list of UrlCheckResult, skips extraction and re-checks
    only those URLs, merging back into existing session state.
    """
    from validators.url_checker import check_urls, group_by_url

    t0 = time.monotonic()

    # Phase 1 — Extract
    if recheck_only is None:
        with st.status("Phase 1/2 — Extracting URLs…", expanded=True) as _ext_status:
            extracted, warnings = _extract_urls_from_uploads(files)
            for w in warnings:
                st.warning(w)

            scanned_warnings = [e for e in extracted if e.url == "__SCANNED_PDF_WARNING__"]
            extracted = [e for e in extracted if e.url != "__SCANNED_PDF_WARNING__"]
            for sw in scanned_warnings:
                st.warning("⚠️ **{}**: {}".format(sw.source_file, sw.context))

            if not extracted:
                _ext_status.update(label="No URLs found in the uploaded files.", state="error")
                st.session_state["url_results"] = []
                return

            url_groups = group_by_url(extracted)
            st.write("Found **{}** unique URL(s) across **{}** file(s).".format(
                len(url_groups), len(files)
            ))
            _ext_status.update(label="Extraction complete.", state="complete")
    else:
        url_groups = {r.url: r.locations for r in recheck_only}

    # Phase 2 — Check (worker thread + queue for Streamlit-safe progress updates)
    total = len(url_groups)
    _prog_bar = st.progress(0)
    _status_txt = st.empty()

    _q = queue.Queue()
    _result_holder = []
    _error_holder = []

    def _worker():
        try:
            def _on_progress(url, result):
                _q.put((url, result))

            res = check_urls(
                url_groups,
                timeout=timeout,
                max_workers=max_workers,
                fetch_titles=fetch_titles,
                retry=retry,
                on_progress=_on_progress,
            )
            _result_holder.extend(res)
        except Exception as exc:
            _error_holder.append(exc)
        finally:
            _q.put(None)  # sentinel — signals completion

    _thread = threading.Thread(target=_worker, daemon=True)
    _thread.start()

    _count = 0
    while True:
        _item = _q.get()
        if _item is None:
            break
        _url_done, _ = _item
        _count += 1
        _prog_bar.progress(min(_count / total, 1.0))
        _status_txt.caption("Checking ({}/{}) {}".format(_count, total, _url_done[:80]))

    _thread.join()
    _prog_bar.empty()
    _status_txt.empty()

    if _error_holder:
        st.error("Check failed: {}".format(_error_holder[0]))
        return

    if recheck_only is not None:
        _updated = {r.url: r for r in _result_holder}
        st.session_state["url_results"] = [
            _updated.get(existing.url, existing)
            for existing in st.session_state["url_results"]
        ]
    else:
        st.session_state["url_results"] = _result_holder
        st.session_state["url_source_names"] = [f.name for f in files]

    st.session_state["url_run_ts"] = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    st.session_state["url_elapsed"] = round(time.monotonic() - t0, 1)


# ── Tab 2 UI ─────────────────────────────────────────────────────────────────

with tab_url:

    _url_ctrl, _url_results = st.columns([1, 3], gap="large")

    # ── Controls ─────────────────────────────────────────────────────────────
    with _url_ctrl:
        st.subheader("Settings")

        url_uploaded_files = st.file_uploader(
            "Upload documents",
            type=["docx", "pdf", "pptx", "xlsx", "txt", "html"],
            accept_multiple_files=True,
            key="uploader_url",
            help="Supported: .docx .pdf .pptx .xlsx .txt .html  |  Max 50 MB each",
        )

        st.divider()
        _url_timeout     = st.slider("Timeout per URL (s)", 5, 30, DEFAULT_TIMEOUT, key="url_timeout")
        _url_workers     = st.slider("Concurrent checks",   5, 50, DEFAULT_MAX_WORKERS, key="url_workers")
        _url_titles      = st.toggle("Fetch page titles",  value=False, key="url_titles",
                                     help="Reads <title> tag — slightly slower")
        _url_retry       = st.toggle("Retry on failure",   value=True,  key="url_retry",
                                     help="Retry once on timeout / 5xx / 429")

        st.divider()
        _run_url_btn = st.button(
            "▶  Run Check",
            type="primary",
            use_container_width=True,
            key="run_url_btn",
            disabled=not url_uploaded_files,
        )

        _recheck_url_btn = False
        if st.session_state["url_results"]:
            _recheck_url_btn = st.button(
                "↺  Re-check Dead & Suspicious",
                use_container_width=True,
                key="recheck_url_btn",
            )

    # ── Results ──────────────────────────────────────────────────────────────
    with _url_results:

        # Welcome message
        if not url_uploaded_files and not st.session_state["url_results"]:
            st.markdown("""
This tool extracts every URL from uploaded documents and checks each one for
dead links, redirect-based link rot, and soft 404s — giving a prioritized
report so action items appear first.

**Supported file types:** DOCX · PDF · PPTX · XLSX · TXT · HTML

**What it catches:**
- ❌ **Dead** — 404, 410, DNS failure, SSL error, timeout
- ⚠️ **Suspicious** — silent redirect to homepage, soft 404, 401/403, server error
- ✅ **Alive** — page is reachable and content looks valid
- ⏭️ **Skipped** — mailto:, tel:, relative URLs, anchors

Upload documents in the **left panel** and click **▶ Run Check**.
            """)

        # Trigger scans
        if _run_url_btn and url_uploaded_files:
            _do_url_run(
                url_uploaded_files,
                _url_timeout, _url_workers, _url_titles, _url_retry,
            )

        if _recheck_url_btn and st.session_state["url_results"]:
            _failed_urls = [
                r for r in st.session_state["url_results"]
                if r.tier in ("Dead", "Suspicious")
            ]
            if _failed_urls:
                _do_url_run(
                    url_uploaded_files or [],
                    _url_timeout, _url_workers, _url_titles, _url_retry,
                    recheck_only=_failed_urls,
                )
            else:
                st.info("No Dead or Suspicious URLs to re-check.")

        # ── Results display ───────────────────────────────────────────────
        _url_res = st.session_state["url_results"]
        if _url_res:
            _url_counts = Counter(r.tier for r in _url_res)
            _url_total  = len(_url_res)

            # Header row
            _rh1, _rh2 = st.columns([3, 1])
            with _rh1:
                st.subheader("Results — {}".format(
                    ", ".join(st.session_state["url_source_names"])
                ))
            with _rh2:
                st.caption("Checked: {}  |  {:.1f}s".format(
                    st.session_state["url_run_ts"] or "",
                    st.session_state["url_elapsed"],
                ))

            # Summary metrics
            _m1, _m2, _m3, _m4, _m5 = st.columns(5)
            _m1.metric("Total URLs",     _url_total)
            _m2.metric("✅ Alive",       _url_counts.get("Alive", 0))
            _m3.metric("⚠️ Suspicious",  _url_counts.get("Suspicious", 0))
            _m4.metric("❌ Dead",        _url_counts.get("Dead", 0))
            _m5.metric("⏭️ Skipped",     _url_counts.get("Skipped", 0))

            if _url_counts.get("Dead", 0) == 0 and _url_counts.get("Suspicious", 0) == 0:
                st.success("All checked URLs appear to be alive. No issues found.")

            # Filters
            st.divider()
            with st.expander("🔍 Filter results", expanded=True):
                _rf1, _rf2, _rf3, _rf4 = st.columns(4)
                with _rf1:
                    _f_tiers = st.multiselect(
                        "Status",
                        ["Dead", "Suspicious", "Alive", "Skipped"],
                        default=["Dead", "Suspicious", "Alive", "Skipped"],
                        key="url_filter_tiers",
                    )
                with _rf2:
                    _all_src = sorted({
                        loc.source_file for r in _url_res for loc in r.locations
                    })
                    _f_src = st.multiselect(
                        "Source file", _all_src, default=_all_src, key="url_filter_src"
                    )
                with _rf3:
                    _f_text = st.text_input("URL contains", "", key="url_filter_text")
                with _rf4:
                    _f_epa = st.radio(
                        "Scope",
                        ["All", "EPA Internal only", "External only"],
                        horizontal=True,
                        key="url_filter_epa",
                    )

            # Apply filters
            _filtered_url = _url_res
            if _f_tiers:
                _filtered_url = [r for r in _filtered_url if r.tier in _f_tiers]
            if _f_src:
                _filtered_url = [r for r in _filtered_url
                                  if any(loc.source_file in _f_src for loc in r.locations)]
            if _f_text:
                _filtered_url = [r for r in _filtered_url
                                  if _f_text.lower() in r.url.lower()]
            if _f_epa == "EPA Internal only":
                _filtered_url = [r for r in _filtered_url if r.is_epa_internal]
            elif _f_epa == "External only":
                _filtered_url = [r for r in _filtered_url if not r.is_epa_internal]

            _filtered_url = sorted(
                _filtered_url, key=lambda r: SEVERITY_ORDER.get(r.tier, 99)
            )
            st.caption("Showing **{}** of {} results".format(len(_filtered_url), _url_total))

            # Issues callout boxes (always visible — no clicking required)
            _action_items = [r for r in _filtered_url if r.tier in ("Dead", "Suspicious")]
            if _action_items:
                st.divider()
                st.subheader("Issues requiring attention")
                for r in _action_items:
                    _pri = r.locations[0] if r.locations else None
                    _loc_str = "{} — {}".format(_pri.source_file, _pri.location) if _pri else "Unknown"
                    _ctx_str = _pri.context if _pri and _pri.context else ""

                    _wb_line = ""
                    if r.wayback_url:
                        _wb_line = "\n\n**Archive:** [View last known snapshot ({})]({})".format(
                            r.wayback_snapshot_date or "date unknown", r.wayback_url
                        )
                    elif r.tier == "Dead":
                        _wb_line = "\n\n**Archive:** No snapshot found in Wayback Machine"

                    _msg = (
                        "**{tier}** `{code}` &nbsp;|&nbsp; {url}\n\n"
                        "**Why:** {reason}"
                        "{wayback}\n\n"
                        "**Where:** {loc}{ctx}"
                    ).format(
                        tier=r.tier,
                        code=r.status_code or "N/A",
                        url=r.url,
                        reason=r.reason or "Unknown",
                        wayback=_wb_line,
                        loc=_loc_str,
                        ctx="\n\n**Context:** …{}…".format(_ctx_str) if _ctx_str else "",
                    )
                    if r.tier == "Dead":
                        st.error(_msg)
                    else:
                        st.warning(_msg)

            # Full results table
            st.divider()
            st.subheader("All results")
            if _filtered_url:
                _url_df = _url_results_to_df(_filtered_url)
                st.dataframe(
                    _url_df,
                    use_container_width=True,
                    height=min(400, 55 + len(_url_df) * 35),
                    column_config={
                        "Original URL": st.column_config.LinkColumn("Original URL"),
                        "Final URL":    st.column_config.LinkColumn("Final URL"),
                        "Response (ms)": st.column_config.NumberColumn("Response (ms)", format="%.0f"),
                    },
                )

            # Per-URL expandable detail panels
            st.divider()
            st.subheader("URL Details")
            _URL_ICONS = {"Dead": "❌", "Suspicious": "⚠️", "Alive": "✅", "Skipped": "⏭️"}
            for r in _filtered_url:
                _pri = r.locations[0] if r.locations else None
                _icon = _URL_ICONS.get(r.tier, "")
                _rsn = " — {}".format(r.reason[:60]) if r.reason else ""
                with st.expander("{} {} {}{}".format(_icon, r.tier, r.url[:70], _rsn)):
                    _d1, _d2 = st.columns(2)
                    with _d1:
                        st.markdown("**URL:** {}".format(r.url))
                        if r.final_url:
                            st.markdown("**Final URL:** {}".format(r.final_url))
                        st.markdown("**Status:** {} (HTTP {})".format(
                            r.tier, r.status_code or "N/A"
                        ))
                        if r.reason:
                            st.markdown("**Why flagged:** {}".format(r.reason))
                        if r.wayback_url:
                            st.markdown("**Wayback Machine:** [Last snapshot — {}]({})".format(
                                r.wayback_snapshot_date or "date unknown", r.wayback_url
                            ))
                        elif r.tier == "Dead":
                            st.markdown("**Wayback Machine:** No archived snapshot found")
                        st.markdown("**Response time:** {:.0f} ms".format(r.response_time_ms))
                        st.markdown("**EPA Internal:** {}".format(
                            "Yes" if r.is_epa_internal else "No"
                        ))
                        if r.page_title:
                            st.markdown("**Page title:** {}".format(r.page_title))
                        if r.checked_at:
                            st.markdown("**Checked at:** {}".format(
                                r.checked_at.strftime("%Y-%m-%d %H:%M UTC")
                            ))
                    with _d2:
                        if r.redirect_chain:
                            st.markdown("**Redirect chain ({} hop{}):**".format(
                                r.redirect_count, "s" if r.redirect_count != 1 else ""
                            ))
                            for _code, _hop in r.redirect_chain:
                                st.markdown("- `{}` → {}".format(_code, _hop))
                        else:
                            st.markdown("**Redirect chain:** none")
                        if r.locations:
                            st.markdown("**Found in {} location(s):**".format(len(r.locations)))
                            for _loc in r.locations:
                                st.markdown("- **{}** — {} ({})".format(
                                    _loc.source_file, _loc.location, _loc.link_type
                                ))
                                if _loc.context:
                                    st.caption("Context: …{}…".format(_loc.context))

            # Export
            st.divider()
            st.subheader("Export")

            _ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            _base = (
                st.session_state["url_source_names"][0].rsplit(".", 1)[0]
                if st.session_state["url_source_names"] else "results"
            )
            _fname = "url_check_{}_{}".format(_base, _ts)
            _issues_only = [r for r in _url_res if r.tier in ("Dead", "Suspicious")]
            _export_settings = {
                "timeout": _url_timeout,
                "max_workers": _url_workers,
                "retry": _url_retry,
            }

            _ex1, _ex2, _ex3, _ex4 = st.columns(4)

            with _ex1:
                st.download_button(
                    "⬇️ All results (.xlsx)",
                    data=_export_url_excel(
                        _url_res, _export_settings,
                        st.session_state["url_source_names"],
                    ),
                    file_name="{}.xlsx".format(_fname),
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                    key="dl_url_all_xlsx",
                )
            with _ex2:
                st.download_button(
                    "⬇️ All results (.csv)",
                    data=_export_url_csv(_url_res),
                    file_name="{}.csv".format(_fname),
                    mime="text/csv",
                    use_container_width=True,
                    key="dl_url_all_csv",
                )
            with _ex3:
                if _issues_only:
                    st.download_button(
                        "⬇️ Issues only (.xlsx)",
                        data=_export_url_excel(
                            _issues_only, _export_settings,
                            st.session_state["url_source_names"],
                        ),
                        file_name="{}_issues.xlsx".format(_fname),
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True,
                        type="primary",
                        key="dl_url_issues_xlsx",
                    )
                else:
                    st.button(
                        "⬇️ Issues only (.xlsx)", disabled=True,
                        use_container_width=True, key="dl_url_issues_xlsx_dis",
                    )
            with _ex4:
                if _issues_only:
                    st.download_button(
                        "⬇️ Issues only (.csv)",
                        data=_export_url_csv(_issues_only),
                        file_name="{}_issues.csv".format(_fname),
                        mime="text/csv",
                        use_container_width=True,
                        type="primary",
                        key="dl_url_issues_csv",
                    )
                else:
                    st.button(
                        "⬇️ Issues only (.csv)", disabled=True,
                        use_container_width=True, key="dl_url_issues_csv_dis",
                    )
