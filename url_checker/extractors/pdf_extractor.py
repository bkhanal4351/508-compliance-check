import logging
import re
from typing import List

from extractors.base import BaseExtractor, ExtractedUrl
from utils.url_utils import extract_plain_urls, get_context

logger = logging.getLogger(__name__)

# Join hyphenated line-wraps before URL scanning: "exam-\nple" → "example"
_HYPHEN_WRAP = re.compile(r"-\s*\n\s*")


class PdfExtractor(BaseExtractor):
    def extract(self):
        # type: () -> List[ExtractedUrl]
        try:
            import fitz  # PyMuPDF
        except ImportError:
            logger.error("PyMuPDF not installed")
            return []

        try:
            doc = fitz.open(str(self.file_path))
        except Exception as e:
            logger.error("Cannot open %s: %s", self.file_path, e)
            return []

        results = []          # type: List[ExtractedUrl]
        seen_embedded = set()
        has_extractable_text = False

        for page_num in range(len(doc)):
            page = doc[page_num]
            label = "Page {}".format(page_num + 1)

            # Embedded annotation links
            try:
                for link in page.get_links():
                    url = link.get("uri", "")
                    if url and url not in seen_embedded:
                        seen_embedded.add(url)
                        results.append(ExtractedUrl(
                            url=url,
                            source_file=self.source_name,
                            location=label,
                            context="",
                            link_type="embedded",
                        ))
            except Exception as e:
                logger.warning("Link extraction failed on %s %s: %s", self.source_name, label, e)

            # Plain-text URLs
            try:
                raw_text = page.get_text()
            except Exception:
                raw_text = ""

            if raw_text.strip():
                has_extractable_text = True
                text = _HYPHEN_WRAP.sub("", raw_text)
                for url, pos in extract_plain_urls(text):
                    results.append(ExtractedUrl(
                        url=url,
                        source_file=self.source_name,
                        location=label,
                        context=get_context(text, pos),
                        link_type="plain-text",
                    ))

        doc.close()

        if not has_extractable_text and not results:
            logger.warning(
                "%s appears to be a scanned PDF with no extractable text. OCR is required.",
                self.source_name,
            )
            results.append(ExtractedUrl(
                url="__SCANNED_PDF_WARNING__",
                source_file=self.source_name,
                location="Document",
                context="No extractable text — this may be a scanned PDF. OCR is needed.",
                link_type="plain-text",
            ))

        return results
