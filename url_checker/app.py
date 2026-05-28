"""
URL Checker — EPA internal tool for finding dead / suspicious links in policy documents.
Run with: streamlit run app.py
"""
import io
import logging
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
import streamlit as st

# Make sibling packages importable when launched from this directory
sys.path.insert(0, str(Path(__file__).parent))

from extractors.base import CheckResult, ExtractedUrl
from exporters.csv_exporter import export_csv
from exporters.excel_exporter import export_excel
from utils.constants import (
    DEFAULT_MAX_WORKERS,
    DEFAULT_TIMEOUT,
    SEVERITY_ORDER,
    SUPPORTED_EXTENSIONS,
    TIER_BADGE_COLORS,
)

logging.basicConfig(level=logging.INFO, stream=sys.stderr)

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="EPA URL Checker",
    page_icon="🔗",
    layout="wide",
)

# ---------------------------------------------------------------------------
# Session state init
# ---------------------------------------------------------------------------
if "results" not in st.session_state:
    st.session_state.results = []       # List[CheckResult]
if "run_ts" not in st.session_state:
    st.session_state.run_ts = None
if "elapsed" not in st.session_state:
    st.session_state.elapsed = 0.0
if "source_names" not in st.session_state:
    st.session_state.source_names = []


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _badge(tier):
    color = TIER_BADGE_COLORS.get(tier, "#888888")
    return '<span style="background:{};color:#fff;padding:2px 8px;border-radius:4px;font-size:0.8em;font-weight:bold">{}</span>'.format(color, tier)


def _get_extractor(suffix, file_path):
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


def _extract_from_uploads(uploaded_files):
    # type: (list) -> List[ExtractedUrl]
    all_extracted = []
    warnings = []

    for uf in uploaded_files:
        suffix = Path(uf.name).suffix.lower()
        if suffix not in SUPPORTED_EXTENSIONS:
            warnings.append("{}: unsupported format ({})".format(uf.name, suffix))
            continue

        size_mb = uf.size / (1024 * 1024)
        if size_mb > 50:
            warnings.append("{}: file too large ({:.1f} MB, max 50 MB)".format(uf.name, size_mb))
            continue

        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(uf.read())
            tmp_path = tmp.name

        extractor = _get_extractor(suffix, tmp_path)
        if extractor is None:
            warnings.append("{}: no extractor available".format(uf.name))
            continue

        try:
            extracted = extractor.extract()
            # Rename source to original upload filename
            for e in extracted:
                e.source_file = uf.name
            all_extracted.extend(extracted)
        except Exception as ex:
            warnings.append("{}: extraction error — {}".format(uf.name, ex))

    return all_extracted, warnings


def _results_to_df(results):
    # type: (List[CheckResult]) -> pd.DataFrame
    rows = []
    for r in results:
        primary = r.locations[0] if r.locations else None
        rows.append({
            "Status":            r.tier,
            "Original URL":      r.url,
            "Final URL":         r.final_url or "",
            "HTTP Code":         str(r.status_code) if r.status_code else "",
            "Source File":       primary.source_file if primary else "",
            "Location":          primary.location if primary else "",
            "Context":           primary.context if primary else "",
            "Response (ms)":     r.response_time_ms,
            "Reason":            r.reason or "",
            "EPA Internal":      "Yes" if r.is_epa_internal else "No",
        })
    df = pd.DataFrame(rows)
    if not df.empty:
        df["_sort"] = df["Status"].map(lambda t: SEVERITY_ORDER.get(t, 99))
        df = df.sort_values("_sort").drop(columns=["_sort"]).reset_index(drop=True)
    return df


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.title("🔗 URL Checker")
    st.caption("EPA OFOM/OBP internal tool")
    st.divider()

    uploaded_files = st.file_uploader(
        "Upload documents",
        type=["docx", "pdf", "pptx", "xlsx", "txt", "html"],
        accept_multiple_files=True,
        help="Supported: .docx, .pdf, .pptx, .xlsx, .txt, .html  |  Max 50 MB each",
    )

    st.divider()
    st.subheader("Settings")
    timeout = st.slider("Timeout per URL (s)", 5, 30, DEFAULT_TIMEOUT)
    max_workers = st.slider("Concurrent checks", 5, 50, DEFAULT_MAX_WORKERS)
    fetch_titles = st.toggle("Fetch page titles", value=False,
                             help="Reads page <title> tag — slightly slower")
    retry = st.toggle("Retry on failure", value=True,
                      help="Retry once on timeout / 5xx / 429")

    st.divider()
    run_btn = st.button("▶  Run Check", type="primary", use_container_width=True,
                        disabled=not uploaded_files)

    if st.session_state.results:
        recheck_btn = st.button("↺  Re-check Dead & Suspicious", use_container_width=True)
    else:
        recheck_btn = False


# ---------------------------------------------------------------------------
# Main area — pre-scan instructions
# ---------------------------------------------------------------------------
st.title("EPA URL Checker")

if not uploaded_files and not st.session_state.results:
    st.info(
        "**Upload one or more documents** (DOCX, PDF, PPTX, XLSX, TXT, HTML) in the sidebar "
        "to check every URL inside.\n\n"
        "The tool extracts both embedded hyperlinks and plain-text URLs, then checks each one "
        "for dead links, redirect-to-homepage link rot, and soft 404s — flagging the results "
        "by severity so action items appear first."
    )
    st.stop()


# ---------------------------------------------------------------------------
# Run scan
# ---------------------------------------------------------------------------
def _do_run(files, recheck_only=None):
    from validators.url_checker import check_urls, group_by_url

    t0 = time.monotonic()

    # Phase 1 — Extract
    if recheck_only is None:
        with st.status("Phase 1/2 — Extracting URLs from documents…", expanded=True) as status:
            extracted, warnings = _extract_from_uploads(files)
            if warnings:
                for w in warnings:
                    st.warning(w)

            # Filter out sentinel scanned-PDF entries
            scanned_warnings = [e for e in extracted if e.url == "__SCANNED_PDF_WARNING__"]
            extracted = [e for e in extracted if e.url != "__SCANNED_PDF_WARNING__"]

            for sw in scanned_warnings:
                st.warning("⚠️ **{}**: {}".format(sw.source_file, sw.context))

            if not extracted:
                status.update(label="No URLs found in the uploaded files.", state="error")
                st.session_state.results = []
                return

            url_groups = group_by_url(extracted)
            st.write("Found **{}** unique URL(s) across **{}** file(s).".format(
                len(url_groups), len(files)
            ))
            status.update(label="Extraction complete.", state="complete")
    else:
        # Re-check only failed URLs, keeping existing locations
        url_groups = {r.url: r.locations for r in recheck_only}

    # Phase 2 — Check
    # Progress updates come from a worker thread; use a queue so only the
    # main (Streamlit session) thread writes to UI widgets.
    import queue
    import threading

    total = len(url_groups)
    progress_bar = st.progress(0)
    status_text = st.empty()

    progress_q = queue.Queue()
    result_holder = []
    error_holder = []

    def _worker():
        try:
            def on_progress(url, result):
                progress_q.put((url, result))   # thread-safe, no Streamlit calls

            res = check_urls(
                url_groups,
                timeout=timeout,
                max_workers=max_workers,
                fetch_titles=fetch_titles,
                retry=retry,
                on_progress=on_progress,
            )
            result_holder.extend(res)
        except Exception as exc:
            error_holder.append(exc)
        finally:
            progress_q.put(None)  # sentinel

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()

    # Drain the queue on the main thread so Streamlit widgets stay in context
    count = 0
    while True:
        item = progress_q.get()
        if item is None:
            break
        url_done, _ = item
        count += 1
        progress_bar.progress(min(count / total, 1.0))
        status_text.caption("Checking ({}/{}) {}".format(count, total, url_done[:80]))

    thread.join()

    progress_bar.empty()
    status_text.empty()

    if error_holder:
        st.error("Check failed: {}".format(error_holder[0]))
        return

    results = result_holder

    if recheck_only is not None:
        # Merge re-check results into existing results list
        updated = {r.url: r for r in results}
        merged = []
        for existing in st.session_state.results:
            merged.append(updated.get(existing.url, existing))
        st.session_state.results = merged
    else:
        st.session_state.results = results
        st.session_state.source_names = [f.name for f in files]

    st.session_state.run_ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    st.session_state.elapsed = round(time.monotonic() - t0, 1)


if run_btn and uploaded_files:
    _do_run(uploaded_files)

if recheck_btn and st.session_state.results:
    failed = [r for r in st.session_state.results if r.tier in ("Dead", "Suspicious")]
    if failed:
        _do_run(uploaded_files or [], recheck_only=failed)
    else:
        st.info("No Dead or Suspicious URLs to re-check.")


# ---------------------------------------------------------------------------
# Results display
# ---------------------------------------------------------------------------
results = st.session_state.results
if not results:
    st.stop()

# -- Summary cards --
from collections import Counter
counts = Counter(r.tier for r in results)
total_urls = len(results)

st.divider()
col_title, col_ts = st.columns([3, 1])
with col_title:
    st.subheader("Results — {}".format(", ".join(st.session_state.source_names)))
with col_ts:
    st.caption("Checked: {}  |  {:.1f}s".format(
        st.session_state.run_ts or "", st.session_state.elapsed
    ))

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

# -- Friendly empty states --
if counts.get("Dead", 0) == 0 and counts.get("Suspicious", 0) == 0:
    st.success("All checked URLs appear to be alive. No dead or suspicious links found.")

# -- Filters --
st.divider()
with st.expander("🔍 Filter results", expanded=True):
    f1, f2, f3, f4 = st.columns(4)
    with f1:
        filter_tiers = st.multiselect(
            "Status", ["Dead", "Suspicious", "Alive", "Skipped"],
            default=["Dead", "Suspicious", "Alive", "Skipped"],
        )
    with f2:
        all_sources = sorted({loc.source_file for r in results for loc in r.locations})
        filter_sources = st.multiselect("Source file", all_sources, default=all_sources)
    with f3:
        filter_text = st.text_input("URL contains", "")
    with f4:
        epa_filter = st.radio("Scope", ["All", "EPA Internal only", "External only"], horizontal=True)

# Apply filters
filtered = results
if filter_tiers:
    filtered = [r for r in filtered if r.tier in filter_tiers]
if filter_sources:
    filtered = [r for r in filtered if any(loc.source_file in filter_sources for loc in r.locations)]
if filter_text:
    filtered = [r for r in filtered if filter_text.lower() in r.url.lower()]
if epa_filter == "EPA Internal only":
    filtered = [r for r in filtered if r.is_epa_internal]
elif epa_filter == "External only":
    filtered = [r for r in filtered if not r.is_epa_internal]

# Sort by severity
filtered = sorted(filtered, key=lambda r: SEVERITY_ORDER.get(r.tier, 99))

st.caption("Showing **{}** of {} results".format(len(filtered), total_urls))

# -- Inline issues: Dead and Suspicious shown as coloured callouts, no clicking needed --
action_items = [r for r in filtered if r.tier in ("Dead", "Suspicious")]
if action_items:
    st.divider()
    st.subheader("Issues requiring attention")
    for r in action_items:
        primary = r.locations[0] if r.locations else None
        loc_str = "{} — {}".format(primary.source_file, primary.location) if primary else "Unknown location"
        context_str = primary.context if primary and primary.context else ""
        wayback_line = ""
        if r.wayback_url:
            wayback_line = "\n\n**Archive:** [View last known snapshot ({})]({})".format(
                r.wayback_snapshot_date or "date unknown", r.wayback_url
            )
        elif r.tier == "Dead":
            wayback_line = "\n\n**Archive:** No snapshot found in Wayback Machine"
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
            ctx="\n\n**Context:** …{}…".format(context_str) if context_str else "",
        )
        if r.tier == "Dead":
            st.error(msg)
        else:
            st.warning(msg)

# -- Full results table --
st.divider()
st.subheader("All results")
if filtered:
    df = _results_to_df(filtered)
    st.dataframe(
        df,
        use_container_width=True,
        height=min(400, 55 + len(df) * 35),
        column_config={
            "Original URL": st.column_config.LinkColumn("Original URL"),
            "Final URL":    st.column_config.LinkColumn("Final URL"),
            "Response (ms)": st.column_config.NumberColumn("Response (ms)", format="%.0f"),
        },
    )

# -- Per-row detail expanders (reason in title, no click needed to see it) --
st.divider()
st.subheader("URL Details")
if not filtered:
    st.info("No results match the current filters.")
else:
    ICONS = {"Dead": "❌", "Suspicious": "⚠️", "Alive": "✅", "Skipped": "⏭️"}
    for r in filtered:
        primary = r.locations[0] if r.locations else None
        icon = ICONS.get(r.tier, "")
        reason_snippet = " — {}".format(r.reason[:60]) if r.reason else ""
        label = "{} {} {}{}".format(icon, r.tier, r.url[:70], reason_snippet)
        with st.expander(label):
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
                if r.redirect_chain:
                    st.markdown("**Redirect chain ({} hop{}):**".format(
                        r.redirect_count, "s" if r.redirect_count != 1 else ""
                    ))
                    for code, hop_url in r.redirect_chain:
                        st.markdown("- `{}` → {}".format(code, hop_url))
                else:
                    st.markdown("**Redirect chain:** none")

                if r.locations:
                    st.markdown("**Found in {} location(s):**".format(len(r.locations)))
                    for loc in r.locations:
                        st.markdown("- **{}** — {} ({})".format(
                            loc.source_file, loc.location, loc.link_type
                        ))
                        if loc.context:
                            st.caption("Context: …{}…".format(loc.context))

# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------
st.divider()
st.subheader("Export")

ts_str = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
base_name = (st.session_state.source_names[0].rsplit(".", 1)[0]
             if st.session_state.source_names else "results")
filename_base = "url_check_{}_{}".format(base_name, ts_str)

issues_only = [r for r in results if r.tier in ("Dead", "Suspicious")]

ex1, ex2, ex3, ex4 = st.columns(4)

with ex1:
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
    csv_bytes = export_csv(results)
    st.download_button(
        "⬇️ All results (.csv)",
        data=csv_bytes,
        file_name="{}.csv".format(filename_base),
        mime="text/csv",
        use_container_width=True,
    )

with ex3:
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
            type="primary",
        )
    else:
        st.button("⬇️ Issues only (.xlsx)", disabled=True, use_container_width=True)

with ex4:
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
