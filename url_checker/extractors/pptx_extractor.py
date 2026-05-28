# =============================================================================
# pptx_extractor.py — Pulls every URL out of a PowerPoint (.pptx) file.
#
# PowerPoint files store URLs in two ways:
#   1. "Embedded" hyperlinks — text formatted as a clickable link.
#      In python-pptx these live on individual text "runs" (a contiguous
#      piece of text with the same formatting) as run.hyperlink.address.
#   2. "Plain-text" URLs — URLs typed literally into a text box,
#      e.g. "More info at https://www.epa.gov/report".
# We collect both types, slide by slide.
# =============================================================================

import logging
from typing import List

from extractors.base import BaseExtractor, ExtractedUrl
from utils.url_utils import extract_plain_urls, get_context

logger = logging.getLogger(__name__)


class PptxExtractor(BaseExtractor):

    def extract(self):
        # type: () -> List[ExtractedUrl]
        """Open the .pptx file and return every URL found inside it."""

        # python-pptx is the library that reads PowerPoint files.
        # Lazy import here so the app loads even if the library is missing.
        try:
            from pptx import Presentation
        except ImportError:
            logger.error("python-pptx not installed")
            return []

        # Try to open the file; if it's corrupt or not a valid .pptx, log and stop.
        try:
            prs = Presentation(self.file_path)
        except Exception as e:
            logger.error("Cannot open %s: %s", self.file_path, e)
            return []

        results = []  # type: List[ExtractedUrl]

        # ----------------------------------------------------------------
        # Walk every slide in the presentation
        # ----------------------------------------------------------------
        # enumerate(prs.slides, 1) gives us (1, slide1), (2, slide2), etc.
        # so slide_num starts at 1 (human-friendly) instead of 0.
        for slide_num, slide in enumerate(prs.slides, 1):
            label = "Slide {}".format(slide_num)

            # A slide is made up of "shapes" — text boxes, images, charts, etc.
            for shape in slide.shapes:
                # Only shapes that have a text frame (i.e. contain text) are relevant.
                # Images, tables, and charts have no text_frame.
                if not shape.has_text_frame:
                    continue

                # A text frame contains paragraphs (like lines in a text box).
                for para in shape.text_frame.paragraphs:
                    # para.text gives the full visible text of this paragraph,
                    # joining all the individual formatting runs together.
                    para_text = para.text

                    # Each paragraph is made of "runs" — adjacent characters with
                    # the same formatting (bold, italic, color, hyperlink, etc.).
                    # A hyperlink lives on a run level, not the paragraph level.
                    for run in para.runs:
                        try:
                            # run.hyperlink is None if no hyperlink is attached.
                            # run.hyperlink.address is the actual URL string.
                            if run.hyperlink and run.hyperlink.address:
                                results.append(ExtractedUrl(
                                    url=run.hyperlink.address,
                                    source_file=self.source_name,
                                    location=label,
                                    # Use the first 100 chars of the paragraph text
                                    # as context so reviewers can see what the link says
                                    context=para_text[:100],
                                    link_type="embedded",
                                ))
                        except Exception:
                            # Some shapes or runs have unusual structures that
                            # cause attribute errors; silently skip them.
                            pass

                    # -------- Plain-text URLs in this paragraph --------
                    # After processing embedded links, also scan the raw paragraph
                    # text for URLs that were typed in (not formatted as hyperlinks).
                    if para_text.strip():    # skip completely empty paragraphs
                        for url, pos in extract_plain_urls(para_text):
                            results.append(ExtractedUrl(
                                url=url,
                                source_file=self.source_name,
                                location=label,
                                context=get_context(para_text, pos),  # ~100-char snippet
                                link_type="plain-text",
                            ))

        return results
