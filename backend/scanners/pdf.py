import json
import logging
import os
import subprocess
import uuid
from pathlib import Path
from typing import Optional

import pikepdf

from scanners.base import Finding, Severity
from utils.wcag_refs import get_refs

logger = logging.getLogger(__name__)

VERAPDF_PATH = os.environ.get("VERAPDF_PATH", "verapdf")


def _verapdf_available() -> bool:
    try:
        subprocess.run([VERAPDF_PATH, "--version"], capture_output=True, timeout=10)
        return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _run_verapdf(file_path: str) -> list[Finding]:
    findings = []
    try:
        result = subprocess.run(
            [VERAPDF_PATH, "--format", "json", "--profile", "ua1", file_path],
            capture_output=True,
            text=True,
            timeout=120,
        )
        raw = result.stdout.strip()
        if not raw:
            return findings
        data = json.loads(raw)
    except subprocess.TimeoutExpired:
        logger.error("veraPDF timed out on %s", file_path)
        return findings
    except (json.JSONDecodeError, Exception) as e:
        logger.error("veraPDF parse error: %s", e)
        return findings

    try:
        jobs = data.get("report", {}).get("jobs", [])
        for job in jobs:
            validation = job.get("validationResult", {})
            for rule_result in validation.get("ruleSets", [{}])[0].get("rules", []):
                if rule_result.get("status") == "FAILED":
                    clause = rule_result.get("clause", "unknown")
                    test_number = rule_result.get("testNumber", "")
                    errors = rule_result.get("errors", [])
                    for err in errors[:5]:  # cap per-rule errors to avoid explosion
                        rule_id = f"verapdf-{clause}-{test_number}".lower().replace(".", "-")
                        wcag_sc, sec508_ref, sev = get_refs(rule_id)
                        findings.append(Finding(
                            id=str(uuid.uuid4())[:8],
                            rule=rule_id,
                            wcag_sc=wcag_sc if wcag_sc != "Unknown" else "1.3.1",
                            sec508_ref=sec508_ref if sec508_ref != "Unknown" else "E205.4",
                            severity=sev,
                            title=f"PDF/UA rule {clause}.{test_number} failed",
                            description=err.get("message", rule_result.get("description", "PDF/UA validation failure")),
                            location=err.get("context", "Document level"),
                            source="deterministic",
                        ))
    except Exception as e:
        logger.error("veraPDF result parse error: %s", e)

    return findings


def _pikepdf_checks(file_path: str) -> list[Finding]:
    findings = []
    try:
        pdf = pikepdf.open(file_path)
    except Exception as e:
        logger.error("pikepdf could not open %s: %s", file_path, e)
        wcag_sc, sec508_ref, sev = get_refs("pdf-untagged")
        findings.append(Finding(
            id=str(uuid.uuid4())[:8],
            rule="pdf-untagged",
            wcag_sc=wcag_sc,
            sec508_ref=sec508_ref,
            severity=Severity.CRITICAL,
            title="PDF could not be opened for accessibility checks",
            description=f"File could not be parsed: {e}",
            location="Document",
            source="deterministic",
        ))
        return findings

    with pdf:
        root = pdf.Root

        # 1. Tagged PDF check
        is_tagged = False
        try:
            mark_info = root.get("/MarkInfo")
            if mark_info and mark_info.get("/Marked") == True:  # noqa: E712
                is_tagged = True
        except Exception:
            pass

        try:
            if "/StructTreeRoot" in root:
                is_tagged = True
        except Exception:
            pass

        if not is_tagged:
            wcag_sc, sec508_ref, sev = get_refs("pdf-untagged")
            findings.append(Finding(
                id=str(uuid.uuid4())[:8],
                rule="pdf-untagged",
                wcag_sc=wcag_sc,
                sec508_ref=sec508_ref,
                severity=sev,
                title="PDF is not tagged",
                description=(
                    "This PDF lacks a tag tree (StructTreeRoot / MarkInfo Marked=true). "
                    "Screen readers cannot determine reading order or element roles. "
                    "Full remediation required — not just rule fixes."
                ),
                location="Document",
                source="deterministic",
            ))

        # 2. Document language
        try:
            lang = root.get("/Lang")
            if not lang or str(lang).strip() == "":
                wcag_sc, sec508_ref, sev = get_refs("pdf-no-lang")
                findings.append(Finding(
                    id=str(uuid.uuid4())[:8],
                    rule="pdf-no-lang",
                    wcag_sc=wcag_sc,
                    sec508_ref=sec508_ref,
                    severity=sev,
                    title="PDF document language not set",
                    description="The /Lang entry is missing or empty. Screen readers need this to select correct pronunciation rules.",
                    location="Document /Lang",
                    suggested_fix="Set the document language (e.g., /Lang 'en-US') in Document Properties > Advanced.",
                    source="deterministic",
                ))
        except Exception:
            pass

        # 3. Document title in metadata
        try:
            info = pdf.docinfo
            title = info.get("/Title", "")
            if not title or str(title).strip() == "":
                wcag_sc, sec508_ref, sev = get_refs("pdf-no-title")
                findings.append(Finding(
                    id=str(uuid.uuid4())[:8],
                    rule="pdf-no-title",
                    wcag_sc=wcag_sc,
                    sec508_ref=sec508_ref,
                    severity=sev,
                    title="PDF document title not set",
                    description="The /Title metadata entry is missing or empty. Tab order / page title SC 2.4.2 requires a descriptive title.",
                    location="Document /Title",
                    suggested_fix="Add a descriptive title in File > Properties > Description (Title field).",
                    source="deterministic",
                ))
        except Exception:
            pass

        # 4. Form fields missing accessible name (/TU tooltip)
        try:
            if "/AcroForm" in root:
                acro = root["/AcroForm"]
                fields = acro.get("/Fields", [])
                for field_ref in fields:
                    try:
                        field = pdf.get_object(field_ref.objgen)
                        tu = field.get("/TU", "")
                        t = field.get("/T", "")
                        if not tu or str(tu).strip() == "":
                            wcag_sc, sec508_ref, sev = get_refs("pdf-form-field-no-name")
                            findings.append(Finding(
                                id=str(uuid.uuid4())[:8],
                                rule="pdf-form-field-no-name",
                                wcag_sc=wcag_sc,
                                sec508_ref=sec508_ref,
                                severity=sev,
                                title="PDF form field missing accessible name",
                                description=f"Form field '{t}' has no /TU (tooltip / accessible name). Screen readers cannot identify its purpose.",
                                location=f"AcroForm field: {t}",
                                suggested_fix="Add a /TU tooltip string to each form field in the PDF authoring tool.",
                                source="deterministic",
                            ))
                    except Exception:
                        continue
        except Exception:
            pass

        # 5. Figures without alt text (tagged PDFs)
        if is_tagged:
            try:
                struct_root = root.get("/StructTreeRoot")
                if struct_root:
                    _check_figure_alts(pdf, struct_root, findings)
            except Exception as e:
                logger.debug("Figure alt check error: %s", e)

    return findings


def _check_figure_alts(pdf: pikepdf.Pdf, node, findings: list[Finding], depth: int = 0) -> None:
    if depth > 20:
        return
    try:
        s_type = str(node.get("/S", ""))
        if s_type == "/Figure":
            alt = node.get("/Alt", "")
            if not alt or str(alt).strip() == "":
                wcag_sc, sec508_ref, sev = get_refs("pdf-figure-no-alt")
                findings.append(Finding(
                    id=str(uuid.uuid4())[:8],
                    rule="pdf-figure-no-alt",
                    wcag_sc=wcag_sc,
                    sec508_ref=sec508_ref,
                    severity=sev,
                    title="PDF figure missing alt text",
                    description="A tagged Figure element has no /Alt attribute. Screen readers will skip or misread this image.",
                    location="Struct tree Figure element",
                    suggested_fix="Add alt text (/Alt) to the Figure tag via the PDF authoring tool's tag properties.",
                    source="deterministic",
                ))

        kids = node.get("/K", [])
        if not isinstance(kids, list):
            kids = [kids]
        for kid in kids:
            try:
                resolved = pdf.get_object(kid.objgen) if hasattr(kid, "objgen") else kid
                if hasattr(resolved, "get"):
                    _check_figure_alts(pdf, resolved, findings, depth + 1)
            except Exception:
                continue
    except Exception:
        pass


def scan_pdf(file_path: str) -> list[Finding]:
    findings: list[Finding] = []

    # veraPDF pass (optional — degrades gracefully if not installed)
    if _verapdf_available():
        findings.extend(_run_verapdf(file_path))
    else:
        logger.warning(
            "veraPDF not found at '%s'. Install veraPDF (requires Java 11+) for deep PDF/UA validation. "
            "Running pikepdf-only checks.",
            VERAPDF_PATH,
        )

    # pikepdf structural checks (always run)
    findings.extend(_pikepdf_checks(file_path))

    return findings
