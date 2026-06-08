import logging
import re
import uuid
from pathlib import Path
from typing import Optional

from docx import Document
from docx.oxml.ns import qn

from scanners.base import Finding, Severity
from utils.wcag_refs import get_refs

logger = logging.getLogger(__name__)

_GENERIC_LINK_TEXTS = {"click here", "here", "read more", "link", "more", "learn more", "details"}
_FAKE_HEADING_MIN_FONT_PT = 14


def _f(rule: str, title: str, description: str, location: str,
       snippet: str = None, fix: str = None, semantic: bool = False) -> Finding:
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
        source="semantic" if semantic else "deterministic",
        needs_human_review=semantic,
    )


def _check_headings(doc: Document) -> list[Finding]:
    findings = []
    heading_styles = [p for p in doc.paragraphs if p.style and p.style.name and p.style.name.startswith("Heading")]

    if not heading_styles:
        findings.append(_f(
            "docx-no-heading",
            "Document has no heading styles",
            "No paragraphs use Heading styles. Screen readers rely on heading structure to navigate documents.",
            "Document",
            fix="Apply Heading 1, Heading 2, etc. styles to section titles instead of manually bolding text.",
        ))
        return findings

    # Check for skipped levels
    levels = []
    for p in heading_styles:
        m = re.search(r"Heading (\d+)", p.style.name)
        if m:
            levels.append((int(m.group(1)), p.text.strip()))

    if levels and levels[0][0] != 1:
        findings.append(_f(
            "docx-heading-skipped",
            "Document does not start with Heading 1",
            f"First heading is H{levels[0][0]} ('{levels[0][1]}'). Documents should begin with an H1.",
            f"First heading: '{levels[0][1]}'",
            fix="Change the first section heading style to Heading 1.",
        ))

    for i in range(1, len(levels)):
        prev_level, _ = levels[i - 1]
        curr_level, curr_text = levels[i]
        if curr_level > prev_level + 1:
            findings.append(_f(
                "docx-heading-skipped",
                f"Heading level skipped: H{prev_level} → H{curr_level}",
                f"Heading '{curr_text}' jumps from H{prev_level} to H{curr_level}. Screen readers announce skipped levels, confusing navigation.",
                f"Heading: '{curr_text}'",
                fix=f"Change heading '{curr_text}' from H{curr_level} to H{prev_level + 1}.",
            ))

    return findings


def _check_fake_headings(doc: Document) -> list[Finding]:
    findings = []
    heading_style_names = {p.style.name for p in doc.paragraphs if p.style and p.style.name and p.style.name.startswith("Heading")}
    for i, para in enumerate(doc.paragraphs):
        style_name = (para.style.name or "") if para.style else ""
        if style_name.startswith("Heading"):
            continue
        text = para.text.strip()
        if not text:
            continue
        # Detect bold+large text that looks like a heading
        for run in para.runs:
            size_pt = run.font.size.pt if run.font.size else None
            bold = run.font.bold or (para.style and "Bold" in (para.style.name or ""))
            if bold and size_pt and size_pt >= _FAKE_HEADING_MIN_FONT_PT:
                findings.append(_f(
                    "docx-fake-heading",
                    "Visually styled heading not using Heading style",
                    f"Paragraph '{text[:60]}' appears to be a heading (bold, {size_pt}pt) but uses style '{style_name or 'Normal'}'. Screen readers won't recognize it as a heading.",
                    f"Paragraph {i+1}: '{text[:60]}'",
                    fix=f"Apply a Heading style to '{text[:60]}' instead of manually applying bold/large font.",
                ))
                break
    return findings


def _check_images(doc: Document) -> list[Finding]:
    findings = []
    drawing_xpath = f".//{qn('w:drawing')}"
    docPr_tag = "{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}docPr"

    for i, para in enumerate(doc.paragraphs):
        for drawing in para._element.findall(drawing_xpath):
            # Look for wp:docPr which holds the description/alt text
            doc_pr = None
            for elem in drawing.iter():
                if elem.tag.endswith("}docPr") or elem.tag == docPr_tag:
                    doc_pr = elem
                    break

            if doc_pr is None:
                findings.append(_f(
                    "docx-image-alt-missing",
                    "Image missing alt text (no docPr)",
                    "An inline or floating image has no docPr element, so it has no accessible name or alt text.",
                    f"Paragraph {i+1}",
                    fix="Right-click the image → Edit Alt Text → enter a description.",
                ))
                continue

            descr = doc_pr.get("descr", "").strip()
            name = doc_pr.get("name", f"Image {i+1}")
            if not descr:
                findings.append(_f(
                    "docx-image-alt-missing",
                    "Image missing alt text",
                    f"Image '{name}' has an empty description (alt text). Screen readers will announce it as unlabeled.",
                    f"Paragraph {i+1}: image '{name}'",
                    snippet=f'<docPr name="{name}" descr="">',
                    fix="Right-click the image → Edit Alt Text → enter a meaningful description.",
                ))

    return findings


def _check_tables(doc: Document) -> list[Finding]:
    findings = []
    for t_idx, table in enumerate(doc.tables):
        if not table.rows:
            continue
        first_row = table.rows[0]
        has_header = False
        for cell in first_row.cells:
            for para in cell.paragraphs:
                tr_pr = first_row._tr.find(qn("w:trPr"))
                if tr_pr is not None and tr_pr.find(qn("w:tblHeader")) is not None:
                    has_header = True
                    break
            if has_header:
                break

        if not has_header:
            preview = " | ".join(c.text.strip()[:20] for c in first_row.cells[:3])
            findings.append(_f(
                "docx-table-no-header",
                "Table first row not marked as header",
                f"Table {t_idx+1} first row is not marked as a header row. Screen readers won't associate headers with data cells.",
                f"Table {t_idx+1}, Row 1: '{preview}'",
                fix="Select the first row → Table Design → check 'Header Row', or in Table Properties → Row → 'Repeat as header row at top of each page'.",
            ))
    return findings


def _check_links(doc: Document) -> list[Finding]:
    findings = []
    for rel in doc.part.rels.values():
        if "hyperlink" in rel.reltype:
            try:
                target = rel._target
            except Exception:
                target = ""
    # Traverse runs for hyperlinks via XML
    for i, para in enumerate(doc.paragraphs):
        for hyperlink in para._element.findall(f".//{qn('w:hyperlink')}"):
            text = "".join(r.text or "" for r in hyperlink.findall(f".//{qn('w:t')}")).strip()
            if text.lower() in _GENERIC_LINK_TEXTS or not text:
                href = ""
                r_id = hyperlink.get(f"{{{qn('r:id').split('}')[0][1:]}}}id") or hyperlink.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id", "")
                try:
                    if r_id:
                        href = doc.part.rels[r_id]._target or ""
                except Exception:
                    pass
                findings.append(_f(
                    "docx-link-text-generic",
                    "Generic hyperlink text",
                    f"Hyperlink text '{text}' is not descriptive. Screen reader users navigating links won't understand the destination.",
                    f"Paragraph {i+1}: '{text}'",
                    snippet=f'<a href="{href}">{text}</a>',
                    fix=f"Replace '{text}' with descriptive text that explains where the link goes.",
                ))
    return findings


def _check_language(doc: Document) -> list[Finding]:
    findings = []
    try:
        settings = doc.settings.element
        lang_elem = settings.find(f".//{qn('w:lang')}")
        if lang_elem is None:
            findings.append(_f(
                "docx-no-language",
                "Document language not set",
                "No language is defined in document settings. Screen readers need language to apply correct pronunciation.",
                "Document settings",
                fix="Go to File → Options → Language and set the document editing/display language.",
            ))
    except Exception:
        pass
    return findings


def _check_fake_lists(doc: Document) -> list[Finding]:
    findings = []
    _bullet_pattern = re.compile(r"^[•‣◦⁃∙\-\*]\s+")
    _number_pattern = re.compile(r"^\d+[.)]\s+")
    for i, para in enumerate(doc.paragraphs):
        text = para.text.strip()
        if not text:
            continue
        style_name = (para.style.name or "") if para.style else ""
        if "List" in style_name:
            continue
        if _bullet_pattern.match(text) or _number_pattern.match(text):
            findings.append(_f(
                "docx-fake-list",
                "Manual list formatting instead of list style",
                f"Paragraph {i+1} appears to be a list item ('{text[:40]}') but uses manual bullet/number characters instead of a List style.",
                f"Paragraph {i+1}: '{text[:60]}'",
                fix="Use Format → Bullets or Numbering (or List Bullet/List Number style) instead of typing bullet characters manually.",
            ))
    return findings


def scan_docx(file_path: str) -> list[Finding]:
    findings: list[Finding] = []
    try:
        doc = Document(file_path)
    except Exception as e:
        logger.error("Could not open DOCX %s: %s", file_path, e)
        return findings

    findings.extend(_check_headings(doc))
    findings.extend(_check_fake_headings(doc))
    findings.extend(_check_images(doc))
    findings.extend(_check_tables(doc))
    findings.extend(_check_links(doc))
    findings.extend(_check_language(doc))
    findings.extend(_check_fake_lists(doc))

    return findings
