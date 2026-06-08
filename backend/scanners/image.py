import logging
import uuid
from pathlib import Path
from typing import Optional

from scanners.base import Finding, Severity
from utils.wcag_refs import get_refs

logger = logging.getLogger(__name__)

_BAD_ALTS = {"image", "photo", "picture", "graphic", "icon", "img", "figure"}


def _f(rule: str, title: str, description: str, location: str,
       snippet: str = None, fix: str = None) -> Finding:
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
        source="deterministic",
    )


def scan_image(file_path: str, provided_alt: Optional[str] = None) -> list[Finding]:
    findings: list[Finding] = []
    path = Path(file_path)

    try:
        from PIL import Image
        with Image.open(file_path) as img:
            width, height = img.size
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

    # Deterministic quality check on the provided alt text
    alt_lower = provided_alt.lower().strip()
    if alt_lower in _BAD_ALTS or alt_lower in {path.stem.lower(), path.name.lower()} or len(alt_lower) < 3:
        findings.append(_f(
            "standalone-image-alt-poor",
            "Image alt text is generic or too short",
            f"Alt text '{provided_alt}' appears to be a placeholder or filename and does not describe the image content.",
            location,
            snippet=f'alt="{provided_alt}"',
            fix="Replace with a meaningful description of what the image shows.",
        ))

    return findings
