import logging
import math
import uuid
from typing import Optional

from pptx import Presentation
from pptx.enum.shapes import PP_PLACEHOLDER
from pptx.util import Pt

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


def _relative_luminance(r: int, g: int, b: int) -> float:
    def linearize(c: int) -> float:
        s = c / 255.0
        return s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4
    return 0.2126 * linearize(r) + 0.7152 * linearize(g) + 0.0722 * linearize(b)


def _contrast_ratio(fg: tuple, bg: tuple) -> float:
    l1 = _relative_luminance(*fg)
    l2 = _relative_luminance(*bg)
    lighter, darker = (l1, l2) if l1 > l2 else (l2, l1)
    return (lighter + 0.05) / (darker + 0.05)


def _parse_color(color_str: Optional[str]) -> Optional[tuple]:
    if not color_str:
        return None
    s = color_str.lstrip("#")
    if len(s) == 6:
        try:
            return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))
        except ValueError:
            return None
    return None


def _check_slide_titles(prs: Presentation) -> list[Finding]:
    findings = []
    titles_seen: dict[str, list[int]] = {}

    for slide_idx, slide in enumerate(prs.slides):
        slide_num = slide_idx + 1
        title_text = None

        for shape in slide.shapes:
            if shape.has_text_frame and shape.shape_type in (13, 14):
                pass
            try:
                if shape.is_placeholder:
                    ph = shape.placeholder_format
                    if ph and ph.idx == 0:  # title placeholder
                        title_text = shape.text_frame.text.strip() if shape.has_text_frame else ""
                        break
            except Exception:
                pass

        if title_text is None:
            findings.append(_f(
                "pptx-slide-title-missing",
                f"Slide {slide_num} has no title placeholder",
                f"Slide {slide_num} does not have a title placeholder shape. Screen readers use slide titles for navigation.",
                f"Slide {slide_num}",
                fix=f"Add a title placeholder to slide {slide_num} via Insert → Text Box or using a slide layout that includes a title.",
            ))
        elif title_text == "":
            findings.append(_f(
                "pptx-slide-title-missing",
                f"Slide {slide_num} title is empty",
                f"Slide {slide_num} has a title placeholder but the text is empty. Each slide needs a unique, descriptive title.",
                f"Slide {slide_num}",
                fix=f"Enter a descriptive title in the title placeholder of slide {slide_num}.",
            ))
        else:
            titles_seen.setdefault(title_text.lower(), []).append(slide_num)

    for title, slides in titles_seen.items():
        if len(slides) > 1:
            findings.append(_f(
                "pptx-slide-title-duplicate",
                f"Duplicate slide title: '{title}'",
                f"Slides {slides} share the same title '{title}'. Duplicate titles prevent users from identifying specific slides.",
                f"Slides {slides}",
                fix="Give each slide a unique, descriptive title.",
            ))

    return findings


def _check_shape_alt_text(prs: Presentation) -> list[Finding]:
    findings = []
    for slide_idx, slide in enumerate(prs.slides):
        slide_num = slide_idx + 1
        for shape in slide.shapes:
            # Skip title/body text placeholders that don't need alt text
            try:
                if shape.is_placeholder:
                    ph = shape.placeholder_format
                    if ph and ph.idx in (0, 1):
                        continue
            except Exception:
                pass

            # Only check shapes that could represent visual content
            shape_type = shape.shape_type
            # 1=auto_shape, 3=chart, 5=picture, 6=text_box, 13=picture, 14=media
            if shape_type not in (1, 3, 5, 6, 13, 14):
                continue

            try:
                # python-pptx exposes alt text via the XML
                sp_elem = shape._element
                nv_pr = sp_elem.find(".//{http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing}nvPr")
                # Try p:nvSpPr/p:cNvPr/@descr
                descr = None
                for tag in [
                    "{http://schemas.openxmlformats.org/presentationml/2006/main}nvSpPr",
                    "{http://schemas.openxmlformats.org/presentationml/2006/main}nvPicPr",
                    "{http://schemas.openxmlformats.org/presentationml/2006/main}nvGraphicFramePr",
                    "{http://schemas.openxmlformats.org/presentationml/2006/main}nvGrpSpPr",
                ]:
                    nv_sp = sp_elem.find(tag)
                    if nv_sp is not None:
                        cnv_pr = nv_sp.find("{http://schemas.openxmlformats.org/presentationml/2006/main}cNvPr")
                        if cnv_pr is None:
                            cnv_pr = nv_sp.find("{http://schemas.openxmlformats.org/drawingml/2006/main}cNvPr")
                        if cnv_pr is None:
                            # try without namespace
                            for child in nv_sp:
                                if child.tag.endswith("}cNvPr") or child.tag == "cNvPr":
                                    cnv_pr = child
                                    break
                        if cnv_pr is not None:
                            descr = cnv_pr.get("descr", None)
                            break

                # Fallback: check shape.name attribute for alt
                if descr is None:
                    # python-pptx 0.6.23+ exposes shape.alt_text
                    try:
                        descr = getattr(shape, "alt_text", None) or ""
                    except Exception:
                        descr = ""

                descr = (descr or "").strip()
                if not descr:
                    findings.append(_f(
                        "pptx-shape-alt-missing",
                        f"Shape on slide {slide_num} missing alt text",
                        f"Shape '{shape.name}' (type {shape_type}) on slide {slide_num} has no alt text. Screen readers cannot convey its content.",
                        f"Slide {slide_num}: shape '{shape.name}'",
                        fix="Right-click the shape → Edit Alt Text → enter a meaningful description, or mark as decorative.",
                    ))
            except Exception as e:
                logger.debug("Alt text check error on slide %d shape '%s': %s", slide_num, shape.name, e)

    return findings


def _check_reading_order(prs: Presentation) -> list[Finding]:
    findings = []
    for slide_idx, slide in enumerate(prs.slides):
        slide_num = slide_idx + 1
        shapes = list(slide.shapes)
        if not shapes:
            continue
        # Title should be the first shape in the spTree
        title_shape = None
        title_index = None
        for i, shape in enumerate(shapes):
            try:
                if shape.is_placeholder and shape.placeholder_format and shape.placeholder_format.idx == 0:
                    title_shape = shape
                    title_index = i
                    break
            except Exception:
                pass
        if title_shape is not None and title_index != 0:
            findings.append(_f(
                "pptx-reading-order",
                f"Slide {slide_num}: title is not the first shape in reading order",
                f"The title placeholder is at position {title_index + 1} in the shape tree. Screen readers follow shape tree order, so non-title content may be read before the slide title.",
                f"Slide {slide_num}",
                fix="In the Selection Pane (Home → Arrange → Selection Pane), move the title to the top (last in list = first read).",
            ))
    return findings


def _check_color_contrast(prs: Presentation) -> list[Finding]:
    findings = []
    for slide_idx, slide in enumerate(prs.slides):
        slide_num = slide_idx + 1

        # Attempt to get slide background color
        bg_rgb = (255, 255, 255)  # default white
        try:
            bg = slide.background
            fill = bg.fill
            if fill.type is not None:
                fg_color = fill.fore_color
                if fg_color and fg_color.rgb:
                    bg_rgb = (fg_color.rgb.r, fg_color.rgb.g, fg_color.rgb.b)
        except Exception:
            pass

        for shape in slide.shapes:
            if not shape.has_text_frame:
                continue
            for para in shape.text_frame.paragraphs:
                for run in para.runs:
                    text = run.text.strip()
                    if not text:
                        continue
                    try:
                        font = run.font
                        color = font.color
                        if color is None or color.type is None:
                            continue
                        rgb = color.rgb
                        if rgb is None:
                            continue
                        fg_rgb = (rgb.r, rgb.g, rgb.b)
                        ratio = _contrast_ratio(fg_rgb, bg_rgb)
                        font_size = font.size
                        is_large = font_size is not None and font_size.pt >= 18
                        threshold = 3.0 if is_large else 4.5
                        if ratio < threshold:
                            findings.append(_f(
                                "pptx-color-contrast",
                                f"Slide {slide_num}: insufficient color contrast ({ratio:.1f}:1)",
                                f"Text '{text[:40]}' has a contrast ratio of {ratio:.1f}:1 against the background, below the {'3:1 (large text)' if is_large else '4.5:1 (normal text)'} WCAG minimum.",
                                f"Slide {slide_num}: shape '{shape.name}'",
                                snippet=f'"{text[:60]}" fg=#{rgb} bg=#{bg_rgb}',
                                fix=f"Adjust text or background color to achieve at least {threshold}:1 contrast ratio.",
                            ))
                    except Exception:
                        pass

    return findings


def scan_pptx(file_path: str, use_semantic: bool = False) -> list[Finding]:
    findings: list[Finding] = []
    try:
        prs = Presentation(file_path)
    except Exception as e:
        logger.error("Could not open PPTX %s: %s", file_path, e)
        return findings

    findings.extend(_check_slide_titles(prs))
    findings.extend(_check_shape_alt_text(prs))
    findings.extend(_check_reading_order(prs))
    findings.extend(_check_color_contrast(prs))

    return findings
