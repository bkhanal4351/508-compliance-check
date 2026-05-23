import logging
import uuid
from pathlib import Path
from typing import Optional

from scanners.base import Finding, Severity
from utils.wcag_refs import get_refs

logger = logging.getLogger(__name__)


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


def _extract_ocr_text(file_path: str) -> str:
    """Attempt OCR via pytesseract if available; return empty string on failure."""
    try:
        import pytesseract
        from PIL import Image
        img = Image.open(file_path)
        return pytesseract.image_to_string(img)
    except ImportError:
        logger.debug("pytesseract not installed; skipping OCR")
    except Exception as e:
        logger.warning("OCR failed for %s: %s", file_path, e)
    return ""


def scan_image(file_path: str, provided_alt: Optional[str] = None) -> list[Finding]:
    findings: list[Finding] = []
    path = Path(file_path)

    # Validate the file can be opened
    try:
        from PIL import Image
        with Image.open(file_path) as img:
            width, height = img.size
            mode = img.mode
    except Exception as e:
        logger.error("Could not open image %s: %s", file_path, e)
        return findings

    location = f"Image: {path.name} ({width}×{height})"

    if not provided_alt:
        findings.append(_f(
            "standalone-image-alt-missing",
            "Standalone image has no alt text",
            f"Image '{path.name}' was uploaded without any alt text. Screen readers have nothing to convey about this image.",
            location,
            fix="Provide a concise description of the image content when embedding or sharing this image.",
        ))
        return findings

    # Alt text was provided — check it semantically
    try:
        from ai.prompts import run_semantic_check

        # Also try to get OCR text to give the AI more context
        ocr_text = _extract_ocr_text(file_path)
        image_context = f"Standalone image '{path.name}' ({width}×{height}, {mode})"
        if ocr_text.strip():
            image_context += f". OCR text detected: '{ocr_text.strip()[:300]}'"

        result = run_semantic_check("alt_text", {
            "image_context": image_context,
            "nearby_heading": "",
            "alt_text": provided_alt,
        })

        if result and not result.get("passes"):
            wcag_sc, sec508_ref, sev = get_refs("standalone-image-alt-poor")
            findings.append(Finding(
                id=str(uuid.uuid4())[:8],
                rule="standalone-image-alt-poor",
                wcag_sc=wcag_sc,
                sec508_ref=sec508_ref,
                severity=sev,
                title="Image alt text may not adequately describe the image",
                description=result.get("reasoning", "The provided alt text does not sufficiently describe the image."),
                location=location,
                snippet=f'alt="{provided_alt}"',
                suggested_fix=result.get("suggested_fix"),
                source="semantic",
                needs_human_review=True,
            ))
        elif result and result.get("passes"):
            logger.info("Image alt text passed semantic check for %s", path.name)

    except Exception as e:
        logger.warning("Semantic alt text check unavailable: %s", e)
        # Fall back: flag obviously bad alt text deterministically
        bad_alts = {"image", "photo", "picture", "graphic", "icon", "img", path.stem.lower(), path.name.lower()}
        if provided_alt.lower().strip() in bad_alts or len(provided_alt.strip()) < 3:
            findings.append(_f(
                "standalone-image-alt-poor",
                "Image alt text is generic or too short",
                f"Alt text '{provided_alt}' appears to be a placeholder or filename. It does not describe the image content.",
                location,
                snippet=f'alt="{provided_alt}"',
                fix="Replace the alt text with a meaningful description of what the image shows.",
                semantic=False,
            ))

    return findings
