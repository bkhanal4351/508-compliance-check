import logging
import time
import uuid
from pathlib import Path

from scanners.base import Finding, Severity
from utils.wcag_refs import get_refs

logger = logging.getLogger(__name__)

AXE_JS = Path(__file__).parent / "axe.min.js"

_IMPACT_MAP = {
    "critical": Severity.CRITICAL,
    "serious":  Severity.SERIOUS,
    "moderate": Severity.MODERATE,
    "minor":    Severity.MINOR,
}

_AXE_RULE_MAP = {
    "image-alt":             "image-alt-missing",
    "color-contrast":        "color-contrast-insufficient",
    "label":                 "form-label-missing",
    "heading-order":         "heading-order-skipped",
    "link-name":             "link-text-generic",
    "html-has-lang":         "language-of-page-missing",
    "html-lang-valid":       "language-of-page-missing",
    "keyboard":              "keyboard-trap",
    "aria-required-attr":    "aria-label-invalid",
    "aria-valid-attr":       "aria-label-invalid",
    "aria-valid-attr-value": "aria-label-invalid",
    "button-name":           "form-label-missing",
    "bypass":                "skip-link-missing",
    "document-title":        "page-title-missing",
    "region":                "landmark-missing",
}


def _node_target(node: dict) -> str:
    try:
        return " > ".join(node.get("target", []))
    except Exception:
        return "unknown"


def _axe_to_finding(violation: dict, page_url: str, page_index: int) -> list[Finding]:
    findings = []
    rule_id_raw = violation.get("id", "unknown")
    rule_id = _AXE_RULE_MAP.get(rule_id_raw, rule_id_raw)
    impact = violation.get("impact", "moderate")
    severity = _IMPACT_MAP.get(impact, Severity.MODERATE)
    wcag_sc, sec508_ref, _ = get_refs(rule_id)
    help_text = violation.get("help", violation.get("description", ""))

    for node in violation.get("nodes", []):
        target = _node_target(node)
        snippet = node.get("html", "")[:300] if node.get("html") else None
        failure_msgs = "; ".join(
            item.get("message", "")
            for item in node.get("any", []) + node.get("all", []) + node.get("none", [])
        )
        desc = f"{help_text}. {failure_msgs}".strip(". ")
        findings.append(Finding(
            id=str(uuid.uuid4())[:8],
            rule=rule_id,
            wcag_sc=wcag_sc,
            sec508_ref=sec508_ref,
            severity=severity,
            title=violation.get("help", rule_id),
            description=desc,
            location=f"Page {page_index+1}: {target}",
            snippet=snippet,
            suggested_fix=violation.get("helpUrl"),
            source="deterministic",
        ))
    return findings


def _run_axe_on_page(page, page_url: str, page_index: int) -> list[Finding]:
    try:
        import json
        page.add_script_tag(path=str(AXE_JS))
        result = page.evaluate("() => axe.run().then(r => JSON.stringify(r))")
        data = json.loads(result)
        findings = []
        for v in data.get("violations", []):
            findings.extend(_axe_to_finding(v, page_url, page_index))
        return findings
    except Exception as e:
        logger.error("axe-core failed on %s: %s", page_url, e)
        return []


def scan_url(
    url: str,
    max_depth: int = 1,
    max_pages: int = 25,
    progress_callback=None,
    use_semantic: bool = False,  # kept for API compatibility; no-op in this build
) -> list[Finding]:
    from utils.crawler import discover_urls

    urls = discover_urls(url, max_depth, max_pages)
    logger.info("Discovered %d URL(s) to scan", len(urls))

    all_findings: list[Finding] = []

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.error("playwright not installed")
        return all_findings

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context_pw = browser.new_context(user_agent="508-Scanner/1.0")

        for i, page_url in enumerate(urls):
            if progress_callback:
                progress_callback(i, len(urls), page_url)

            logger.info("Scanning page %d/%d: %s", i + 1, len(urls), page_url)
            page = context_pw.new_page()
            try:
                page.goto(page_url, wait_until="networkidle", timeout=30000)
            except Exception as e:
                logger.warning("Could not load %s: %s", page_url, e)
                page.close()
                continue

            all_findings.extend(_run_axe_on_page(page, page_url, i))
            page.close()
            time.sleep(1)

        browser.close()

    return all_findings
