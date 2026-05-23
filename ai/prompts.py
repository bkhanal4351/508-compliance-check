import logging
from typing import Any

from ai.client import complete_json
from scanners.base import Finding

logger = logging.getLogger(__name__)

_SYSTEM = (
    "You are a Section 508 / WCAG 2.1 AA accessibility expert. You evaluate "
    "specific accessibility issues with precision. Always respond with valid "
    "JSON only. No markdown, no preamble."
)

_JSON_SHAPE = {
    "passes": "<true|false>",
    "reasoning": "<1-2 sentence explanation>",
    "suggested_fix": "<string or null>",
    "confidence": "<0.0-1.0>",
}


def _default_fail(reasoning: str) -> dict[str, Any]:
    return {"passes": False, "reasoning": reasoning, "suggested_fix": None, "confidence": 0.0}


def check_alt_text_quality(image_context: str, nearby_heading: str, alt_text: str) -> dict[str, Any]:
    prompt = f"""Evaluate this alt text for accessibility quality.

Image context: {image_context}
Nearby heading: {nearby_heading}
Alt text: "{alt_text}"

A meaningful alt text:
- Describes the content and function of the image in context
- Is not redundant with surrounding visible text
- Is not generic ("image", "photo", "graphic", a filename, or empty when content is meaningful)
- Is concise but informative (typically under 125 chars)
- Conveys what a sighted user would gain from seeing the image

Respond with this JSON shape:
{{
  "passes": true or false,
  "reasoning": "1-2 sentence explanation",
  "suggested_fix": "improved alt text, or null if passes",
  "confidence": 0.0-1.0
}}"""
    result = complete_json(prompt, _SYSTEM)
    return result if result else _default_fail("Semantic check unavailable")


def check_link_text_quality(link_text: str, surrounding_context: str, href: str) -> dict[str, Any]:
    prompt = f"""Evaluate this hyperlink text for accessibility quality.

Link text: "{link_text}"
Surrounding context: "{surrounding_context}"
href: "{href}"

Accessible link text:
- Makes sense out of context (screen readers list links in isolation)
- Is not generic: "click here", "here", "read more", "link", "more"
- Is not the raw URL
- Describes the destination or action clearly

Respond with this JSON shape:
{{
  "passes": true or false,
  "reasoning": "1-2 sentence explanation",
  "suggested_fix": "better link text, or null if passes",
  "confidence": 0.0-1.0
}}"""
    result = complete_json(prompt, _SYSTEM)
    return result if result else _default_fail("Semantic check unavailable")


def check_heading_order(headings: list[tuple[int, str]]) -> dict[str, Any]:
    formatted = "\n".join(f"  H{level}: {text}" for level, text in headings)
    prompt = f"""Evaluate this heading structure for accessibility quality.

Headings (in document order):
{formatted}

Accessible heading structure:
- Starts at H1 (exactly one H1 per page is ideal)
- Does not skip levels (e.g., H1 → H3 without H2)
- Levels reflect logical document hierarchy, not visual styling
- Each heading text is meaningful (not "Untitled" or empty)

Respond with this JSON shape:
{{
  "passes": true or false,
  "reasoning": "1-2 sentence explanation",
  "suggested_fix": "description of how to fix, or null if passes",
  "confidence": 0.0-1.0
}}"""
    result = complete_json(prompt, _SYSTEM)
    return result if result else _default_fail("Semantic check unavailable")


def check_error_message_clarity(message: str, field_context: str) -> dict[str, Any]:
    prompt = f"""Evaluate this form error message for accessibility quality.

Error message: "{message}"
Field context: "{field_context}"

An accessible error message:
- Clearly identifies what went wrong
- Tells the user how to fix it
- Does not rely solely on color or icon
- Is specific (not "Invalid input" or "Error")

Respond with this JSON shape:
{{
  "passes": true or false,
  "reasoning": "1-2 sentence explanation",
  "suggested_fix": "improved error message, or null if passes",
  "confidence": 0.0-1.0
}}"""
    result = complete_json(prompt, _SYSTEM)
    return result if result else _default_fail("Semantic check unavailable")


def suggest_remediation(finding: Finding) -> str:
    prompt = f"""Provide a concrete, actionable remediation for this accessibility finding.

Rule: {finding.rule}
WCAG SC: {finding.wcag_sc}
Section 508: {finding.sec508_ref}
Title: {finding.title}
Description: {finding.description}
Location: {finding.location}
Snippet: {finding.snippet or "N/A"}

Respond with this JSON shape:
{{
  "passes": true,
  "reasoning": "",
  "suggested_fix": "step-by-step remediation instructions in 1-3 sentences",
  "confidence": 1.0
}}"""
    result = complete_json(prompt, _SYSTEM)
    return result.get("suggested_fix") or "No remediation suggestion available."


def run_semantic_check(check_type: str, kwargs: dict[str, Any]) -> dict[str, Any] | None:
    """Dispatcher called from scanners. Returns None on hard failure."""
    try:
        if check_type == "alt_text":
            return check_alt_text_quality(
                kwargs.get("image_context", ""),
                kwargs.get("nearby_heading", ""),
                kwargs.get("alt_text", ""),
            )
        elif check_type == "link_text":
            return check_link_text_quality(
                kwargs.get("link_text", ""),
                kwargs.get("surrounding_context", ""),
                kwargs.get("href", ""),
            )
        elif check_type == "heading_order":
            return check_heading_order(kwargs.get("headings", []))
        elif check_type == "error_message":
            return check_error_message_clarity(
                kwargs.get("message", ""),
                kwargs.get("field_context", ""),
            )
        else:
            logger.warning("Unknown semantic check type: %s", check_type)
            return None
    except Exception as e:
        logger.warning("Semantic check %s failed: %s", check_type, e)
        return None
