import logging
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from scanners.base import Finding, Severity
from utils.wcag_refs import get_refs

logger = logging.getLogger(__name__)

AXE_JS = Path(__file__).parent / "axe.min.js"

# axe impact -> Severity
_IMPACT_MAP = {
    "critical": Severity.CRITICAL,
    "serious":  Severity.SERIOUS,
    "moderate": Severity.MODERATE,
    "minor":    Severity.MINOR,
}

# axe rule -> internal rule ID (partial; rest fall through to axe's rule id)
_AXE_RULE_MAP = {
    "image-alt":                "image-alt-missing",
    "color-contrast":           "color-contrast-insufficient",
    "label":                    "form-label-missing",
    "heading-order":            "heading-order-skipped",
    "link-name":                "link-text-generic",
    "html-has-lang":            "language-of-page-missing",
    "html-lang-valid":          "language-of-page-missing",
    "keyboard":                 "keyboard-trap",
    "aria-required-attr":       "aria-label-invalid",
    "aria-valid-attr":          "aria-label-invalid",
    "aria-valid-attr-value":    "aria-label-invalid",
    "button-name":              "form-label-missing",
    "bypass":                   "skip-link-missing",
    "document-title":           "page-title-missing",
    "region":                   "landmark-missing",
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
    description = violation.get("description", "")
    help_text = violation.get("help", description)

    for node in violation.get("nodes", []):
        target = _node_target(node)
        snippet = node.get("html", "")[:300] if node.get("html") else None
        failure_msgs = "; ".join(
            item.get("message", "") for item in node.get("any", []) + node.get("all", []) + node.get("none", [])
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
        page.add_script_tag(path=str(AXE_JS))
        result = page.evaluate("() => axe.run().then(r => JSON.stringify(r))")
        import json
        data = json.loads(result)
        findings = []
        for v in data.get("violations", []):
            findings.extend(_axe_to_finding(v, page_url, page_index))
        return findings
    except Exception as e:
        logger.error("axe-core failed on %s: %s", page_url, e)
        return []


def _collect_semantic_context(page) -> dict:
    """Collect elements for semantic AI checks."""
    try:
        return page.evaluate("""() => {
            const imgs = Array.from(document.querySelectorAll('img')).map(img => ({
                src: img.src,
                alt: img.alt,
                nearbyHeading: (() => {
                    let el = img;
                    while (el && el !== document.body) {
                        el = el.parentElement;
                        const h = el ? el.querySelector('h1,h2,h3,h4,h5,h6') : null;
                        if (h) return h.textContent.trim();
                    }
                    const prev = img.closest('section,article,div');
                    if (prev) {
                        const h = prev.querySelector('h1,h2,h3,h4,h5,h6');
                        if (h) return h.textContent.trim();
                    }
                    return '';
                })(),
            }));

            const links = Array.from(document.querySelectorAll('a[href]')).map(a => ({
                text: a.textContent.trim(),
                href: a.href,
                context: a.closest('p,li,td,th') ? a.closest('p,li,td,th').textContent.trim().slice(0,200) : '',
            }));

            const headings = Array.from(document.querySelectorAll('h1,h2,h3,h4,h5,h6')).map(h => ({
                level: parseInt(h.tagName[1]),
                text: h.textContent.trim(),
            }));

            const errors = Array.from(document.querySelectorAll('[role="alert"],[aria-live="assertive"],[aria-invalid="true"]')).map(el => ({
                message: el.textContent.trim().slice(0,300),
                context: el.closest('form,fieldset,div') ? (el.closest('form,fieldset,div').textContent || '').trim().slice(0,300) : '',
            }));

            return { imgs, links, headings, errors };
        }""")
    except Exception as e:
        logger.warning("Could not collect semantic context: %s", e)
        return {}


def _semantic_findings(context: dict, page_index: int, semantic_fn) -> list[Finding]:
    """Run semantic checks and convert results to Findings. semantic_fn is injected to avoid circular import."""
    findings = []
    if not context:
        return findings

    # Check alt text quality
    for img in context.get("imgs", []):
        alt = img.get("alt", "")
        src = img.get("src", "")
        heading = img.get("nearbyHeading", "")
        # Skip decorative (explicit empty alt)
        if alt == "":
            continue
        result = semantic_fn("alt_text", {
            "image_context": f"src={src}",
            "nearby_heading": heading,
            "alt_text": alt,
        })
        if result and not result.get("passes"):
            wcag_sc, sec508_ref, sev = get_refs("image-alt-not-meaningful")
            findings.append(Finding(
                id=str(uuid.uuid4())[:8],
                rule="image-alt-not-meaningful",
                wcag_sc=wcag_sc,
                sec508_ref=sec508_ref,
                severity=sev,
                title="Image alt text may not be meaningful",
                description=result.get("reasoning", "Alt text does not adequately describe the image."),
                location=f"Page {page_index+1}: img[src='{src[:60]}']",
                snippet=f'alt="{alt}"',
                suggested_fix=result.get("suggested_fix"),
                source="semantic",
                needs_human_review=True,
            ))

    # Check link text quality
    generic_link_texts = {"click here", "here", "read more", "link", "more", "learn more"}
    for link in context.get("links", []):
        text = link.get("text", "").lower().strip()
        if not text or text in generic_link_texts or text == link.get("href", "").lower():
            result = semantic_fn("link_text", {
                "link_text": link.get("text", ""),
                "surrounding_context": link.get("context", ""),
                "href": link.get("href", ""),
            })
            if result and not result.get("passes"):
                wcag_sc, sec508_ref, sev = get_refs("link-text-generic")
                findings.append(Finding(
                    id=str(uuid.uuid4())[:8],
                    rule="link-text-generic",
                    wcag_sc=wcag_sc,
                    sec508_ref=sec508_ref,
                    severity=sev,
                    title="Link text is not descriptive",
                    description=result.get("reasoning", "Link text does not describe the destination."),
                    location=f"Page {page_index+1}: a[href='{link.get('href','')[:60]}']",
                    snippet=f'<a href="{link.get("href","")}">{link.get("text","")}</a>',
                    suggested_fix=result.get("suggested_fix"),
                    source="semantic",
                    needs_human_review=True,
                ))

    # Check heading order
    headings = context.get("headings", [])
    if headings:
        result = semantic_fn("heading_order", {
            "headings": [(h["level"], h["text"]) for h in headings],
        })
        if result and not result.get("passes"):
            wcag_sc, sec508_ref, sev = get_refs("heading-order-skipped")
            findings.append(Finding(
                id=str(uuid.uuid4())[:8],
                rule="heading-order-skipped",
                wcag_sc=wcag_sc,
                sec508_ref=sec508_ref,
                severity=sev,
                title="Heading structure is illogical",
                description=result.get("reasoning", "Heading levels are skipped or out of order."),
                location=f"Page {page_index+1}: heading outline",
                suggested_fix=result.get("suggested_fix"),
                source="semantic",
                needs_human_review=True,
            ))

    return findings


def scan_url(
    url: str,
    max_depth: int = 1,
    max_pages: int = 25,
    progress_callback=None,
    use_semantic: bool = True,
) -> list[Finding]:
    from utils.crawler import discover_urls

    urls = discover_urls(url, max_depth, max_pages)
    logger.info("Discovered %d URL(s) to scan", len(urls))

    all_findings: list[Finding] = []

    # Lazy-import semantic to avoid circular imports at module load time
    semantic_fn = None
    if use_semantic:
        try:
            from ai.prompts import run_semantic_check
            semantic_fn = run_semantic_check
        except Exception as e:
            logger.warning("Semantic checks disabled: %s", e)

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

            if semantic_fn:
                ctx = _collect_semantic_context(page)
                all_findings.extend(_semantic_findings(ctx, i, semantic_fn))

            page.close()
            time.sleep(1)  # 1 page/second rate limit

        browser.close()

    return all_findings
