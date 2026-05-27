import logging
from typing import List

from extractors.base import BaseExtractor, ExtractedUrl
from utils.url_utils import extract_plain_urls, get_context

logger = logging.getLogger(__name__)


class TextExtractor(BaseExtractor):
    """Handles plain .txt and .html/.htm files via regex scan."""

    def extract(self):
        # type: () -> List[ExtractedUrl]
        try:
            text = self.file_path.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            logger.error("Cannot read %s: %s", self.file_path, e)
            return []

        results = []  # type: List[ExtractedUrl]
        lines = text.splitlines()

        for line_num, line in enumerate(lines, 1):
            for url, pos in extract_plain_urls(line):
                results.append(ExtractedUrl(
                    url=url,
                    source_file=self.source_name,
                    location="Line {}".format(line_num),
                    context=get_context(line, pos),
                    link_type="plain-text",
                ))

        return results
