"""
URL Checker — EPA internal tool for finding dead / suspicious links in policy documents.
Run with: streamlit run app.py

How it works end-to-end:
  1. Staff upload one or more documents (DOCX, PDF, PPTX, XLSX, TXT, HTML).
  2. The app extracts every URL from each document (embedded hyperlinks AND plain-text URLs).
  3. Each unique URL is checked — we visit it just like a browser would — and classified
     as Alive, Suspicious, Dead, or Skipped.
  4. Results are shown on screen in priority order (worst first) with explanations,
     and can be downloaded as Excel or CSV reports.
"""

import io            # in-memory file handling (used when building download bytes)
import logging       # sends diagnostic messages to the terminal for debugging
import sys           # gives access to the Python path and interpreter info
import tempfile      # creates temporary files on disk to save uploaded content
import time          # for measuring how long the scan takes
from datetime import datetime   # for human-readable timestamps
from pathlib import Path        # cross-platform file path handling
from typing import Dict, List, Optional, Tuple   # type hints for older Python compatibility

import pandas as pd       # data manipulation library — used to build the results table
import streamlit as st    # the web UI framework that powers this app

# Add the current directory to Python's module search path.
# This makes it possible to do "from extractors.docx_extractor import ..." etc.
# when the script is run from the url_checker/ directory.
sys.path.insert(0, str(Path(__file__).parent))

from extractors.base import CheckResult, ExtractedUrl
from exporters.csv_exporter import export_csv
from exporters.excel_exporter import export_excel
from url_checker_utils.constants import (
    DEFAULT_MAX_WORKERS,    # default number of parallel URL checks (20)
    DEFAULT_TIMEOUT,        # default seconds to wait per URL (10)
    SEVERITY_ORDER,         # dict: {"Dead": 0, "Suspicious": 1, "Alive": 2, "Skipped": 3}
    SUPPORTED_EXTENSIONS,   # set of file extensions the app can handle
    TIER_BADGE_COLORS,      # dict: tier name → hex colour string for badges
)

# Set up logging so any module that calls logger.info() or logger.error()
# writes to the terminal (stderr), not the web page.  This helps with debugging.
logging.basicConfig(level=logging.INFO, stream=sys.stderr)


# =============================================================================
# Page configuration — must be the FIRST Streamlit call in the script
# =============================================================================
st.set_page_config(
    page_title="EPA URL Checker",
    page_icon="🔗",     # browser tab icon
    layout="wide",      # use the full browser width instead of a narrow column
)


# =============================================================================
# Session state initialisation
# =============================================================================
# Streamlit re-runs the entire script from top to bottom every time the user
# clicks a button or changes a setting.  "Session state" is a special dictionary
# that persists between those re-runs so we don't lose the results.
#
# We initialise each key only once (with "if key not in st.session_state")
# so we don't accidentally wipe data on re-runs.

if "results" not in st.session_state:
    st.session_state.results = []       # List[CheckResult] — the URL check results
if "run_ts" not in st.session_state:
    st.session_state.run_ts = None      # UTC timestamp of the last scan run
if "elapsed" not in st.session_state:
    st.session_state.elapsed = 0.0     # how many seconds the last scan took
if "source_names" not in st.session_state:
    st.session_state.source_names = [] # list of uploaded filenames (for display)


# =============================================================================
# Helper functions
# =============================================================================

def _badge(tier):
    """
    Return an HTML snippet for a coloured badge pill showing the tier name.
    Example: _badge("Dead") → '<span style="background:#...">Dead</span>'
    We use st.markdown(..., unsafe_allow_html=True) to render it.
    """
    color = TIER_BADGE_COLORS.get(tier, "#888888")   # fall back to grey if tier unknown
    return (
        '<span style="background:{};color:#fff;padding:2px 8px;'
        'border-radius:4px;font-size:0.8em;font-weight:bold">{}</span>'
    ).format(color, tier)


def _get_extractor(suffix, file_path):
    """
    Return the right extractor object for a given file extension.
    For example, ".docx" → DocxExtractor(file_path).
    Returns None if the extension has no matching extractor.
    We import the extractor classes here (lazily) rather than at the top of the
    file so the app loads even if one of the underlying libraries is missing.
    """
    from extractors.docx_extractor import DocxExtractor
    from extractors.pdf_extractor import PdfExtractor
    from extractors.pptx_extractor import PptxExtractor
    from extractors.text_extractor import TextExtractor
    from extractors.xlsx_extractor import XlsxExtractor

    # Map file extension → extractor class
    mapping = {
        ".docx": DocxExtractor,
        ".pdf":  PdfExtractor,
        ".pptx": PptxExtractor,
        ".xlsx": XlsxExtractor,
        ".txt":  TextExtractor,
        ".html": TextExtractor,   # HTML files use the same line-by-line scanner
        ".htm":  TextExtractor,
    }
    cls = mapping.get(suffix)
    return cls(file_path) if cls else None   # instantiate the class with the file path


def _extract_from_uploads(uploaded_files):
    # type: (list) -> Tuple[List[ExtractedUrl], List[str]]
    """
    Loop over every uploaded file, save it to a temporary location on disk
    (so the extractor can open it normally), run the appropriate extractor,
    and collect all the found URLs into one big list.

    Returns (all_extracted, warnings):
      all_extracted — every ExtractedUrl found across all files
      warnings      — any non-fatal problems (unsupported format, file too big, etc.)
    """
    all_extracted = []   # will grow as we process each file
    warnings = []        # human-readable warning strings shown in the UI

    for uf in uploaded_files:
        # uf is a Streamlit UploadedFile object
        suffix = Path(uf.name).suffix.lower()   # e.g. ".docx", ".PDF" → ".pdf"

        # Reject unsupported file types immediately
        if suffix not in SUPPORTED_EXTENSIONS:
            warnings.append("{}: unsupported format ({})".format(uf.name, suffix))
            continue

        # Reject files larger than 50 MB to prevent memory problems
        size_mb = uf.size / (1024 * 1024)   # convert bytes to megabytes
        if size_mb > 50:
            warnings.append("{}: file too large ({:.1f} MB, max 50 MB)".format(uf.name, size_mb))
            continue

        # Save the uploaded file to a temporary file on disk.
        # The extractor libraries (python-docx, PyMuPDF, etc.) need a real file path,
        # not an in-memory bytes object, so we must write it to disk first.
        # "suffix=suffix" preserves the extension so the extractor knows the file type.
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(uf.read())    # write the uploaded bytes to the temp file
            tmp_path = tmp.name     # save the temp file's path for the extractor

        extractor = _get_extractor(suffix, tmp_path)
        if extractor is None:
            warnings.append("{}: no extractor available".format(uf.name))
            continue

        try:
            extracted = extractor.extract()   # run the extractor — returns List[ExtractedUrl]

            # The extractor uses the temp file path as source_file, but we want to
            # show the user the original upload filename.  Override it here.
            for e in extracted:
                e.source_file = uf.name

            all_extracted.extend(extracted)   # add this file's URLs to the master list
        except Exception as ex:
            warnings.append("{}: extraction error — {}".format(uf.name, ex))

    return all_extracted, warnings


def _results_to_df(results):
    # type: (List[CheckResult]) -> pd.DataFrame
    """
    Convert a list of CheckResult objects into a pandas DataFrame for display
    in the results table.  Only the most important columns are included here
    (the full data is available in the Excel/CSV exports).
    """
    rows = []
    for r in results:
        # Use the first location for the Source File and Location columns
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
        # Add a hidden sort key column, sort by it, then remove it
        # so the visible table shows Dead rows first, then Suspicious, etc.
        df["_sort"] = df["Status"].map(lambda t: SEVERITY_ORDER.get(t, 99))
        df = df.sort_values("_sort").drop(columns=["_sort"]).reset_index(drop=True)

    return df


# =============================================================================
# Sidebar — file upload, settings, and action buttons
# =============================================================================
# "with st.sidebar:" groups all these elements into the left panel
with st.sidebar:
    st.title("🔗 URL Checker")
    st.caption("EPA OFOM/OBP internal tool")
    st.divider()   # horizontal rule

    # File uploader widget — allows selecting multiple files at once
    # type=[...] restricts the file picker to the listed extensions
    uploaded_files = st.file_uploader(
        "Upload documents",
        type=["docx", "pdf", "pptx", "xlsx", "txt", "html"],
        accept_multiple_files=True,
        help="Supported: .docx, .pdf, .pptx, .xlsx, .txt, .html  |  Max 50 MB each",
    )

    st.divider()
    st.subheader("Settings")

    # Sliders let users tune the checker without editing code.
    # st.slider(label, min, max, default)
    timeout = st.slider("Timeout per URL (s)", 5, 30, DEFAULT_TIMEOUT)
    max_workers = st.slider("Concurrent checks", 5, 50, DEFAULT_MAX_WORKERS)

    # Toggles (on/off switches) for optional features
    fetch_titles = st.toggle(
        "Fetch page titles", value=False,
        help="Reads page <title> tag — slightly slower",
    )
    retry = st.toggle(
        "Retry on failure", value=True,
        help="Retry once on timeout / 5xx / 429",
    )

    st.divider()

    # Primary "Run" button — disabled if no files are uploaded yet
    run_btn = st.button(
        "▶  Run Check",
        type="primary",
        use_container_width=True,   # stretch button to full sidebar width
        disabled=not uploaded_files,
    )

    # "Re-check" button — only shown when we already have results to re-check
    if st.session_state.results:
        recheck_btn = st.button("↺  Re-check Dead & Suspicious", use_container_width=True)
    else:
        recheck_btn = False   # treat as "not clicked" when there are no results yet


# =============================================================================
# Main area — instructions shown before any files are uploaded
# =============================================================================
st.title("EPA URL Checker")

# If no files are uploaded AND no previous results exist, show a welcome screen
if not uploaded_files and not st.session_state.results:
    st.info(
        "**Upload one or more documents** (DOCX, PDF, PPTX, XLSX, TXT, HTML) in the sidebar "
        "to check every URL inside.\n\n"
        "The tool extracts both embedded hyperlinks and plain-text URLs, then checks each one "
        "for dead links, redirect-to-homepage link rot, and soft 404s — flagging the results "
        "by severity so action items appear first."
    )
    st.stop()   # halt the script here — nothing else to show yet


# =============================================================================
# Core scan function
# =============================================================================

def _do_run(files, recheck_only=None):
    """
    Orchestrate the full scan pipeline:
      Phase 1 — Extract all URLs from the uploaded documents.
      Phase 2 — Check each unique URL and report results.

    If recheck_only is a list of CheckResult objects, only those URLs are
    re-checked (skipping extraction); the new results are merged back into
    the existing session state.

    Parameters:
      files        — the Streamlit UploadedFile objects from the sidebar
      recheck_only — None for a full scan, or List[CheckResult] for a targeted re-check
    """
    # Import here (not at the top) to avoid circular imports and speed up startup
    from validators.url_checker import check_urls, group_by_url

    t0 = time.monotonic()   # record start time for elapsed calculation

    # ----------------------------------------------------------------
    # PHASE 1: Extract URLs from documents
    # ----------------------------------------------------------------
    if recheck_only is None:
        # Show a status panel in the UI while extraction runs
        with st.status("Phase 1/2 — Extracting URLs from documents…", expanded=True) as status:
            extracted, warnings = _extract_from_uploads(files)

            # Show any non-fatal warnings (bad file types, too large, etc.)
            if warnings:
                for w in warnings:
                    st.warning(w)

            # Separate the special scanned-PDF sentinel from real URLs
            scanned_warnings = [e for e in extracted if e.url == "__SCANNED_PDF_WARNING__"]
            extracted = [e for e in extracted if e.url != "__SCANNED_PDF_WARNING__"]

            # Show a warning for each scanned (image-only) PDF that was uploaded
            for sw in scanned_warnings:
                st.warning("⚠️ **{}**: {}".format(sw.source_file, sw.context))

            # If no URLs were found at all, abort the scan
            if not extracted:
                status.update(label="No URLs found in the uploaded files.", state="error")
                st.session_state.results = []
                return

            # group_by_url deduplicates URLs so each unique one is checked only once
            url_groups = group_by_url(extracted)
            st.write("Found **{}** unique URL(s) across **{}** file(s).".format(
                len(url_groups), len(files)
            ))
            status.update(label="Extraction complete.", state="complete")

    else:
        # Re-check mode: build url_groups directly from the failed results list
        # so we skip the extraction phase entirely.
        # {url: locations} is all check_urls() needs to know which URLs to visit.
        url_groups = {r.url: r.locations for r in recheck_only}

    # ----------------------------------------------------------------
    # PHASE 2: Check each URL and show a progress bar
    # ----------------------------------------------------------------
    # Streamlit widgets (like progress bars) can ONLY be updated from the
    # main thread that is running the Streamlit session.  The URL checker
    # runs in a worker thread (to keep the async engine separate).
    # We use a queue.Queue() as a thread-safe message channel:
    #   - Worker thread puts (url, result) tuples into the queue.
    #   - Main thread drains the queue and updates the progress bar.
    import queue
    import threading

    total = len(url_groups)
    progress_bar = st.progress(0)    # progress bar starts at 0%
    status_text = st.empty()         # a placeholder for the "Checking (5/20) https://..." line

    progress_q = queue.Queue()   # the thread-safe message channel
    result_holder = []           # worker thread will append results here
    error_holder = []            # worker thread will append exceptions here (if any)

    def _worker():
        """
        This function runs in a separate background thread.
        It calls the async URL checker, which internally uses asyncio to
        check many URLs simultaneously.  When each URL finishes, it puts
        a notification into the queue so the main thread can update the UI.
        """
        try:
            def on_progress(url, result):
                # This callback is called by the async engine after each URL finishes.
                # We put the result into the queue instead of updating Streamlit directly,
                # because Streamlit widget updates must happen on the session's main thread.
                progress_q.put((url, result))

            res = check_urls(
                url_groups,
                timeout=timeout,
                max_workers=max_workers,
                fetch_titles=fetch_titles,
                retry=retry,
                on_progress=on_progress,   # called once per completed URL
            )
            result_holder.extend(res)   # save results for the main thread to use
        except Exception as exc:
            error_holder.append(exc)    # save the exception for error display
        finally:
            progress_q.put(None)        # None is the sentinel — "I'm done, wake up"

    # Start the worker in a background thread (daemon=True means it won't prevent
    # the process from exiting even if it's still running)
    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()

    # Main thread loop: drain the queue and update the UI until the sentinel arrives
    count = 0
    while True:
        item = progress_q.get()   # blocks here (waits) until a message is available
        if item is None:          # sentinel received → worker is done
            break
        url_done, _ = item        # unpack (url, result) — we only need the URL for display
        count += 1
        # Update the progress bar: min(..., 1.0) prevents it from going over 100%
        progress_bar.progress(min(count / total, 1.0))
        # Show which URL was just checked and how far along we are
        status_text.caption("Checking ({}/{}) {}".format(count, total, url_done[:80]))

    thread.join()   # wait for the worker thread to fully finish (should already be done)

    # Clean up the progress UI elements so they don't clutter the results area
    progress_bar.empty()
    status_text.empty()

    # If the worker crashed, show the error and exit
    if error_holder:
        st.error("Check failed: {}".format(error_holder[0]))
        return

    results = result_holder   # the full list of CheckResult objects

    # ----------------------------------------------------------------
    # Save results to session state
    # ----------------------------------------------------------------
    if recheck_only is not None:
        # Re-check mode: merge the fresh results back into the existing list.
        # We build a dict keyed by URL for fast lookup, then replace each
        # old result with the new one (or keep the old if it wasn't re-checked).
        updated = {r.url: r for r in results}
        merged = []
        for existing in st.session_state.results:
            merged.append(updated.get(existing.url, existing))
        st.session_state.results = merged
    else:
        # Full scan: replace everything
        st.session_state.results = results
        # Record which files were scanned for display in the results header
        st.session_state.source_names = [f.name for f in files]

    # Record when the scan finished and how long it took
    st.session_state.run_ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    st.session_state.elapsed = round(time.monotonic() - t0, 1)


# ---- Trigger the scan ----

# Run a full scan when the "Run Check" button is clicked
if run_btn and uploaded_files:
    _do_run(uploaded_files)

# Run a targeted re-check when the "Re-check Dead & Suspicious" button is clicked
if recheck_btn and st.session_state.results:
    failed = [r for r in st.session_state.results if r.tier in ("Dead", "Suspicious")]
    if failed:
        _do_run(uploaded_files or [], recheck_only=failed)
    else:
        st.info("No Dead or Suspicious URLs to re-check.")


# =============================================================================
# Results display — only shown after a scan has run
# =============================================================================
results = st.session_state.results
if not results:
    st.stop()   # nothing to show yet — stop rendering here

# ---- Summary metric cards ----
# Counter counts how many results have each tier value
from collections import Counter
counts = Counter(r.tier for r in results)
total_urls = len(results)

st.divider()
# Two-column layout: filename on the left, timestamp on the right
col_title, col_ts = st.columns([3, 1])
with col_title:
    # Show which files were scanned
    st.subheader("Results — {}".format(", ".join(st.session_state.source_names)))
with col_ts:
    # Show when the scan ran and how long it took
    st.caption("Checked: {}  |  {:.1f}s".format(
        st.session_state.run_ts or "", st.session_state.elapsed
    ))

# Five metric boxes in a row — one per count
c1, c2, c3, c4, c5 = st.columns(5)
with c1:
    st.metric("Total URLs", total_urls)
with c2:
    st.metric("✅ Alive", counts.get("Alive", 0))
with c3:
    st.metric("⚠️ Suspicious", counts.get("Suspicious", 0))
with c4:
    st.metric("❌ Dead", counts.get("Dead", 0))
with c5:
    st.metric("⏭️ Skipped", counts.get("Skipped", 0))

# Friendly success message when there are no problems
if counts.get("Dead", 0) == 0 and counts.get("Suspicious", 0) == 0:
    st.success("All checked URLs appear to be alive. No dead or suspicious links found.")


# ---- Filter controls ----
st.divider()
with st.expander("🔍 Filter results", expanded=True):
    # Four filter controls laid out in columns
    f1, f2, f3, f4 = st.columns(4)

    with f1:
        # Multi-select: user picks which status tiers to show
        filter_tiers = st.multiselect(
            "Status", ["Dead", "Suspicious", "Alive", "Skipped"],
            default=["Dead", "Suspicious", "Alive", "Skipped"],  # show all by default
        )
    with f2:
        # Multi-select: filter by which source file(s) to include
        # Collect all unique source filenames from all result locations
        all_sources = sorted({loc.source_file for r in results for loc in r.locations})
        filter_sources = st.multiselect("Source file", all_sources, default=all_sources)
    with f3:
        # Text box: filter by substring match on the URL
        filter_text = st.text_input("URL contains", "")
    with f4:
        # Radio buttons: show all, only EPA internal, or only external URLs
        epa_filter = st.radio("Scope", ["All", "EPA Internal only", "External only"], horizontal=True)

# Apply each active filter in sequence
filtered = results

if filter_tiers:
    # Keep only results whose tier is in the selected list
    filtered = [r for r in filtered if r.tier in filter_tiers]

if filter_sources:
    # Keep only results that appear in at least one of the selected source files
    filtered = [r for r in filtered if any(loc.source_file in filter_sources for loc in r.locations)]

if filter_text:
    # Keep only results whose URL contains the search string (case-insensitive)
    filtered = [r for r in filtered if filter_text.lower() in r.url.lower()]

if epa_filter == "EPA Internal only":
    filtered = [r for r in filtered if r.is_epa_internal]
elif epa_filter == "External only":
    filtered = [r for r in filtered if not r.is_epa_internal]

# Sort the filtered results by severity so Dead appears before Suspicious etc.
filtered = sorted(filtered, key=lambda r: SEVERITY_ORDER.get(r.tier, 99))

# Show a count of how many rows are visible after filtering
st.caption("Showing **{}** of {} results".format(len(filtered), total_urls))


# ---- Inline issue callouts ----
# Dead and Suspicious URLs are shown as coloured alert boxes WITHOUT requiring
# the user to click anything.  This ensures the "why" is always visible.
action_items = [r for r in filtered if r.tier in ("Dead", "Suspicious")]
if action_items:
    st.divider()
    st.subheader("Issues requiring attention")

    for r in action_items:
        primary = r.locations[0] if r.locations else None
        # e.g. "policy_doc.docx — Page 3"
        loc_str = "{} — {}".format(primary.source_file, primary.location) if primary else "Unknown location"
        context_str = primary.context if primary and primary.context else ""

        # Build the Wayback Machine line:
        # If a snapshot exists → clickable link with the date
        # If no snapshot and the URL is Dead → note that no archive was found
        wayback_line = ""
        if r.wayback_url:
            wayback_line = "\n\n**Archive:** [View last known snapshot ({})]({})".format(
                r.wayback_snapshot_date or "date unknown", r.wayback_url
            )
        elif r.tier == "Dead":
            wayback_line = "\n\n**Archive:** No snapshot found in Wayback Machine"

        # Build the full message body using .format() (Python 3.6 compatible)
        msg = (
            "**{tier}** `{code}` &nbsp;|&nbsp; {url}\n\n"
            "**Why:** {reason}"
            "{wayback}\n\n"
            "**Where in document:** {loc}{ctx}"
        ).format(
            tier=r.tier,
            code=r.status_code or "N/A",
            url=r.url,
            reason=r.reason or "Unknown",
            wayback=wayback_line,
            loc=loc_str,
            # Append the context snippet if available, with ellipsis on each side
            ctx="\n\n**Context:** …{}…".format(context_str) if context_str else "",
        )

        # st.error() renders a red box (for Dead); st.warning() renders an orange box (for Suspicious)
        if r.tier == "Dead":
            st.error(msg)
        else:
            st.warning(msg)


# ---- Full results table ----
# A sortable, scrollable table showing all filtered results
st.divider()
st.subheader("All results")
if filtered:
    df = _results_to_df(filtered)
    st.dataframe(
        df,
        use_container_width=True,   # stretch table to fill the page width
        # Cap height at 400 px; grow dynamically for small result sets
        height=min(400, 55 + len(df) * 35),
        column_config={
            # LinkColumn turns URL strings into clickable hyperlinks in the table
            "Original URL": st.column_config.LinkColumn("Original URL"),
            "Final URL":    st.column_config.LinkColumn("Final URL"),
            # NumberColumn with format="%.0f" shows integers (no decimal places)
            "Response (ms)": st.column_config.NumberColumn("Response (ms)", format="%.0f"),
        },
    )


# ---- Per-URL detail expanders ----
# Each URL gets its own collapsible section.  The expander TITLE includes the
# reason text so staff can scan through them without expanding each one.
st.divider()
st.subheader("URL Details")

if not filtered:
    st.info("No results match the current filters.")
else:
    ICONS = {"Dead": "❌", "Suspicious": "⚠️", "Alive": "✅", "Skipped": "⏭️"}

    for r in filtered:
        primary = r.locations[0] if r.locations else None
        icon = ICONS.get(r.tier, "")
        # Include the first 60 chars of the reason in the title so staff can see
        # why a URL was flagged without opening the expander
        reason_snippet = " — {}".format(r.reason[:60]) if r.reason else ""
        label = "{} {} {}{}".format(icon, r.tier, r.url[:70], reason_snippet)

        with st.expander(label):
            # Two-column layout: left = URL facts, right = redirects & locations
            d1, d2 = st.columns(2)

            with d1:
                st.markdown("**URL:** {}".format(r.url))
                if r.final_url:
                    st.markdown("**Final URL:** {}".format(r.final_url))
                st.markdown("**Status:** {} (HTTP {})".format(r.tier, r.status_code or "N/A"))
                if r.reason:
                    st.markdown("**Why flagged:** {}".format(r.reason))
                if r.wayback_url:
                    st.markdown("**Wayback Machine:** [Last snapshot — {}]({})".format(
                        r.wayback_snapshot_date or "date unknown", r.wayback_url
                    ))
                elif r.tier == "Dead":
                    st.markdown("**Wayback Machine:** No archived snapshot found")
                st.markdown("**Response time:** {:.0f} ms".format(r.response_time_ms))
                st.markdown("**EPA Internal:** {}".format("Yes" if r.is_epa_internal else "No"))
                if r.page_title:
                    st.markdown("**Page title:** {}".format(r.page_title))
                if r.checked_at:
                    st.markdown("**Checked at:** {}".format(r.checked_at.strftime("%Y-%m-%d %H:%M UTC")))

            with d2:
                # Show the full redirect chain if any redirects happened
                if r.redirect_chain:
                    st.markdown("**Redirect chain ({} hop{}):**".format(
                        r.redirect_count, "s" if r.redirect_count != 1 else ""
                    ))
                    for code, hop_url in r.redirect_chain:
                        st.markdown("- `{}` → {}".format(code, hop_url))
                else:
                    st.markdown("**Redirect chain:** none")

                # List every place in every document where this URL was found
                if r.locations:
                    st.markdown("**Found in {} location(s):**".format(len(r.locations)))
                    for loc in r.locations:
                        st.markdown("- **{}** — {} ({})".format(
                            loc.source_file, loc.location, loc.link_type
                        ))
                        if loc.context:
                            st.caption("Context: …{}…".format(loc.context))


# =============================================================================
# Export section — download buttons for reports
# =============================================================================
st.divider()
st.subheader("Export")

# Build a filename base from the current time and the first uploaded file's name.
# e.g. "url_check_policy_doc_20240715_134512"
ts_str = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
base_name = (
    st.session_state.source_names[0].rsplit(".", 1)[0]  # remove the extension
    if st.session_state.source_names
    else "results"
)
filename_base = "url_check_{}_{}".format(base_name, ts_str)

# Separate Dead/Suspicious results for the "issues only" exports
issues_only = [r for r in results if r.tier in ("Dead", "Suspicious")]

# Four export buttons in a row
ex1, ex2, ex3, ex4 = st.columns(4)

with ex1:
    # All results as Excel — includes Summary sheet with chart and Details sheet
    excel_bytes = export_excel(
        results,
        settings={"timeout": timeout, "max_workers": max_workers, "retry": retry},
        source_names=st.session_state.source_names,
    )
    st.download_button(
        "⬇️ All results (.xlsx)",
        data=excel_bytes,
        file_name="{}.xlsx".format(filename_base),
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )

with ex2:
    # All results as CSV — simple format, works with any spreadsheet app
    csv_bytes = export_csv(results)
    st.download_button(
        "⬇️ All results (.csv)",
        data=csv_bytes,
        file_name="{}.csv".format(filename_base),
        mime="text/csv",
        use_container_width=True,
    )

with ex3:
    # Issues-only Excel (Dead + Suspicious) — highlighted as primary action button
    if issues_only:
        excel_issues = export_excel(
            issues_only,
            settings={"timeout": timeout, "max_workers": max_workers, "retry": retry},
            source_names=st.session_state.source_names,
        )
        st.download_button(
            "⬇️ Issues only (.xlsx)",
            data=excel_issues,
            file_name="{}_issues.xlsx".format(filename_base),
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
            type="primary",   # shows as a filled blue button to draw attention
        )
    else:
        # Greyed-out placeholder when there are no issues to export
        st.button("⬇️ Issues only (.xlsx)", disabled=True, use_container_width=True)

with ex4:
    # Issues-only CSV (Dead + Suspicious) — also highlighted as primary
    if issues_only:
        csv_issues = export_csv(issues_only)
        st.download_button(
            "⬇️ Issues only (.csv)",
            data=csv_issues,
            file_name="{}_issues.csv".format(filename_base),
            mime="text/csv",
            use_container_width=True,
            type="primary",
        )
    else:
        st.button("⬇️ Issues only (.csv)", disabled=True, use_container_width=True)
