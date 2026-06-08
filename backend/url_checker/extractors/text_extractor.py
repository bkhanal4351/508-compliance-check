# =============================================================================
# text_extractor.py — Pulls every URL out of a plain text or HTML file.
#
# Both .txt and .html/.htm files are handled the same way: we read the file
# line by line and run a regex on each line looking for URL-shaped strings.
# For HTML files this is not a full parse — we scan the raw source text, so
# we'll find URLs in both href attributes AND in visible body text.
# =============================================================================

import logging
from typing import List

from extractors.base import BaseExtractor, ExtractedUrl
from url_checker_utils.url_utils import extract_plain_urls, get_context

logger = logging.getLogger(__name__)


class TextExtractor(BaseExtractor):
    """Handles plain .txt and .html/.htm files via line-by-line regex scan."""

    def extract(self):
        # type: () -> List[ExtractedUrl]
        """Read the file and return every URL found inside it."""

        # read_text() opens the file and returns its entire content as a string.
        # encoding="utf-8" covers the vast majority of text files.
        # errors="replace" means if a character can't be decoded (e.g. an
        # unexpected byte in an otherwise UTF-8 file) we substitute a
        # replacement character instead of crashing.
        try:
            text = self.file_path.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            logger.error("Cannot read %s: %s", self.file_path, e)
            return []

        results = []  # type: List[ExtractedUrl]

        # splitlines() splits the whole text into individual lines
        # (handles \n, \r\n, \r, etc. automatically).
        lines = text.splitlines()

        # enumerate(lines, 1) gives us (1, line1), (2, line2), etc.
        # so line_num starts at 1, matching what users see in a text editor.
        for line_num, line in enumerate(lines, 1):
            # extract_plain_urls scans the line for URL-shaped strings and
            # returns a list of (url, character_position_in_line) pairs.
            for url, pos in extract_plain_urls(line):
                results.append(ExtractedUrl(
                    url=url,
                    source_file=self.source_name,
                    # Location tells reviewers exactly which line in the file
                    location="Line {}".format(line_num),
                    # get_context returns ~100 characters around the URL in that line
                    context=get_context(line, pos),
                    link_type="plain-text",
                ))

        return results
