import io
import logging
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(stream=sys.stderr, level=logging.INFO)

st.set_page_config(
    page_title="508 / WCAG Accessibility Scanner",
    page_icon="♿",
    layout="wide",
)

# ── helpers ───────────────────────────────────────────────────────────────────

def _groq_status() -> tuple[bool, str]:
    key = os.environ.get("GROQ_API_KEY", "")
    if key:
        return True, "✅ GROQ_API_KEY found"
    return False, "❌ GROQ_API_KEY missing — semantic checks disabled"


def _run_scan_url(url: str, max_depth: int, max_pages: int, use_semantic: bool, status_placeholder):
    from scanners.web import scan_url

    findings = []
    progress = status_placeholder.progress(0, text="Starting scan…")

    def on_progress(i, total, page_url):
        pct = int((i / max(total, 1)) * 100)
        progress.progress(pct, text=f"Scanning page {i+1}/{total}: {page_url}")

    findings = scan_url(
        url,
        max_depth=max_depth,
        max_pages=max_pages,
        progress_callback=on_progress,
        use_semantic=use_semantic,
    )
    progress.progress(100, text="Scan complete")
    return findings


def _run_scan_document(file_bytes: bytes, filename: str, use_semantic: bool, status_placeholder) -> list:
    status_placeholder.info(f"Scanning {filename}…")
    ext = Path(filename).suffix.lower()

    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        tmp.write(file_bytes)
        tmp_path = tmp.name

    try:
        if ext == ".pdf":
            from scanners.pdf import scan_pdf
            return scan_pdf(tmp_path)
        elif ext in (".docx",):
            from scanners.docx_scanner import scan_docx
            return scan_docx(tmp_path, use_semantic=use_semantic)
        elif ext in (".pptx",):
            from scanners.pptx_scanner import scan_pptx
            return scan_pptx(tmp_path, use_semantic=use_semantic)
        elif ext in (".xlsx",):
            from scanners.xlsx_scanner import scan_xlsx
            return scan_xlsx(tmp_path)
        elif ext in (".png", ".jpg", ".jpeg", ".gif", ".webp"):
            from scanners.image import scan_image
            alt_text = st.session_state.get("image_alt", "")
            return scan_image(tmp_path, provided_alt=alt_text or None)
        else:
            st.error(f"Unsupported file type: {ext}")
            return []
    finally:
        Path(tmp_path).unlink(missing_ok=True)


# ── sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.title("♿ 508 Scanner")
    st.caption("Section 508 / WCAG 2.1 AA Compliance Scanner")
    st.divider()

    groq_ok, groq_msg = _groq_status()
    st.markdown(groq_msg)
    use_semantic = groq_ok

    st.divider()
    scan_type = st.radio("Scan Type", ["URL", "Document Upload"], horizontal=True)

    if scan_type == "URL":
        url_input = st.text_input("URL to scan", placeholder="https://example.com")
        max_depth = st.slider("Max crawl depth", 0, 3, 1)
        max_pages = st.slider("Max pages", 1, 50, 25)
    else:
        uploaded_file = st.file_uploader(
            "Upload document",
            type=["pdf", "docx", "pptx", "xlsx", "png", "jpg", "jpeg"],
            help="Max 50 MB",
        )
        if uploaded_file and uploaded_file.size > 50 * 1024 * 1024:
            st.warning("File exceeds 50 MB limit.")
            uploaded_file = None

        # Show alt text field for images
        if uploaded_file and Path(uploaded_file.name).suffix.lower() in (".png", ".jpg", ".jpeg", ".gif", ".webp"):
            st.text_input("Image alt text (optional)", key="image_alt",
                          placeholder="Describe the image for the semantic check")

    st.divider()
    run_btn = st.button("▶ Run Scan", type="primary", use_container_width=True)


# ── main area ─────────────────────────────────────────────────────────────────

st.title("Section 508 / WCAG 2.1 AA Scanner")

if "report" not in st.session_state:
    st.markdown("""
    This tool scans websites and documents for accessibility issues against **Section 508** and **WCAG 2.1 AA** standards.

    **What it checks:**
    - 🌐 **Websites** — axe-core automated rules + AI semantic checks (alt text quality, link text, heading structure)
    - 📄 **PDFs** — tagged structure, language, title, form fields (+ veraPDF if installed)
    - 📝 **DOCX** — headings, images, tables, hyperlinks, lists, language
    - 📊 **PPTX** — slide titles, shape alt text, reading order, color contrast
    - 📈 **XLSX** — workbook title, sheet names, table structure, merged cells, image alt text
    - 🖼️ **Images** — alt text quality via AI semantic check

    Configure the scan in the sidebar and click **Run Scan**.
    """)

# ── scan execution ────────────────────────────────────────────────────────────

if run_btn:
    findings = []
    scan_target = ""
    status = st.status("Running scan…", expanded=True)

    with status:
        try:
            if scan_type == "URL":
                if not url_input or not url_input.startswith("http"):
                    st.error("Please enter a valid URL starting with http:// or https://")
                    st.stop()
                scan_target = url_input
                findings = _run_scan_url(url_input, max_depth, max_pages, use_semantic, st)

            else:
                if not uploaded_file:
                    st.error("Please upload a file.")
                    st.stop()
                scan_target = uploaded_file.name
                file_bytes = uploaded_file.read()
                findings = _run_scan_document(file_bytes, uploaded_file.name, use_semantic, st)

        except Exception as e:
            st.error(f"Scan failed: {e}")
            logging.exception("Scan error")
            st.stop()

        status.update(label="Scan complete ✅", state="complete")

    from report.builder import build_report
    report = build_report(findings, scan_target, scan_type.lower().replace(" ", "_"))
    st.session_state["report"] = report
    st.session_state["scan_target"] = scan_target

# ── results display ───────────────────────────────────────────────────────────

if "report" in st.session_state:
    report = st.session_state["report"]
    summary = report["summary"]
    all_findings = report["findings"]

    # Summary cards
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("🔴 Critical", summary["Critical"])
    col2.metric("🟠 Serious",  summary["Serious"])
    col3.metric("🔵 Moderate", summary["Moderate"])
    col4.metric("🟢 Minor",    summary["Minor"])

    if report["deduped_count"] > 0:
        st.caption(f"{report['deduped_count']} duplicate finding(s) collapsed.")

    st.divider()

    # Filter controls
    fc1, fc2, fc3 = st.columns([2, 2, 3])
    with fc1:
        sev_filter = st.multiselect(
            "Severity",
            ["Critical", "Serious", "Moderate", "Minor"],
            default=["Critical", "Serious", "Moderate", "Minor"],
        )
    with fc2:
        src_filter = st.multiselect(
            "Source",
            ["deterministic", "semantic"],
            default=["deterministic", "semantic"],
        )
    with fc3:
        search_text = st.text_input("Search findings", placeholder="rule, title, location…")

    # Filter findings
    filtered = [
        f for f in all_findings
        if f.severity.value in sev_filter
        and f.source in src_filter
        and (
            not search_text
            or search_text.lower() in f.title.lower()
            or search_text.lower() in f.rule.lower()
            or search_text.lower() in f.location.lower()
        )
    ]

    st.caption(f"Showing {len(filtered)} of {summary['total']} findings")

    if filtered:
        # Findings table
        import pandas as pd
        df = pd.DataFrame([{
            "Severity":  f.severity.value,
            "Title":     f.title,
            "Location":  f.location,
            "WCAG SC":   f.wcag_sc,
            "508 Ref":   f.sec508_ref,
            "Source":    f.source,
            "Rule":      f.rule,
        } for f in filtered])
        st.dataframe(df, use_container_width=True, hide_index=True)

        # Expanders per finding
        st.subheader("Finding Details")
        for f in filtered:
            sev_emoji = {"Critical": "🔴", "Serious": "🟠", "Moderate": "🔵", "Minor": "🟢"}.get(f.severity.value, "⚪")
            label = f"{sev_emoji} [{f.severity.value}] {f.title} — {f.location}"
            with st.expander(label):
                st.markdown(f"**Rule:** `{f.rule}`  |  **WCAG:** {f.wcag_sc}  |  **508:** {f.sec508_ref}")
                st.markdown(f"**Source:** {f.source}" + (" *(needs human review)*" if f.needs_human_review else ""))
                st.markdown(f"**Description:** {f.description}")
                if f.snippet:
                    st.code(f.snippet, language="html")
                if f.suggested_fix:
                    st.success(f"**Suggested fix:** {f.suggested_fix}")
    else:
        st.info("No findings match the current filters.")

    # Download buttons
    st.divider()
    dl1, dl2 = st.columns(2)

    with dl1:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp_pdf:
            tmp_pdf_path = tmp_pdf.name
        try:
            from report.pdf_export import export_pdf
            export_pdf(report, tmp_pdf_path)
            with open(tmp_pdf_path, "rb") as f:
                pdf_bytes = f.read()
            st.download_button(
                "⬇ Download PDF Report",
                data=pdf_bytes,
                file_name="508_scan_report.pdf",
                mime="application/pdf",
                use_container_width=True,
            )
        except Exception as e:
            st.warning(f"PDF export failed: {e}. Check WeasyPrint installation.")
        finally:
            Path(tmp_pdf_path).unlink(missing_ok=True)

    with dl2:
        from report.pdf_export import export_csv
        csv_str = export_csv(report)
        st.download_button(
            "⬇ Download CSV",
            data=csv_str,
            file_name="508_scan_findings.csv",
            mime="text/csv",
            use_container_width=True,
        )
