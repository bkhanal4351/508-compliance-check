# =============================================================================
# pdf_extractor.py — Pulls every URL out of a PDF file.
#
# PDFs store URLs in two different ways:
#   1. "Embedded" annotation links — invisible clickable rectangles drawn on
#      top of text.  They point to a URL but the visible text might say
#      anything (e.g. "Click here" with a hyperlink underneath).
#   2. "Plain-text" URLs — URLs literally typed into the document body,
#      e.g. "Visit https://www.epa.gov for details."
#
# We also handle a special case: scanned PDFs.  When a document is created by
# scanning a paper page and saving it as a PDF, the text is just an image —
# there is nothing for us to read.  In that case we warn the user that OCR
# (optical character recognition) software is needed to extract URLs.
# =============================================================================

import logging
import re
from typing import List

from extractors.base import BaseExtractor, ExtractedUrl
from url_checker_utils.url_utils import extract_plain_urls, get_context

logger = logging.getLogger(__name__)

# Some PDFs wrap long URLs across two lines with a hyphen, like:
#   "Visit https://www.epa.gov/re-
#    ports/2024/policy"
# This regex matches a hyphen followed by optional spaces and a newline,
# so we can stitch the pieces back together before searching for URLs.
_HYPHEN_WRAP = re.compile(r"-\s*\n\s*")


class PdfExtractor(BaseExtractor):

    def extract(self):
        # type: () -> List[ExtractedUrl]
        """Open the PDF and return every URL found inside it."""

        # PyMuPDF (imported as "fitz") is the library that reads PDF files.
        # We import it here rather than at the top so the app still loads even
        # if the library is not installed — the error is shown per-file.
        try:
            import fitz  # PyMuPDF
        except ImportError:
            logger.error("PyMuPDF not installed")
            return []

        # Try to open the PDF; if it's corrupt or password-protected, log and stop.
        # str() converts the Path object to a plain string, which fitz.open() requires.
        try:
            doc = fitz.open(str(self.file_path))
        except Exception as e:
            logger.error("Cannot open %s: %s", self.file_path, e)
            return []

        results = []           # type: List[ExtractedUrl]  — grows as we find URLs
        seen_embedded = set()  # tracks URLs already added from annotations, to avoid duplicates
        has_extractable_text = False  # flag: did we find any readable text anywhere?

        # ----------------------------------------------------------------
        # Loop over every page in the PDF
        # ----------------------------------------------------------------
        for page_num in range(len(doc)):
            page = doc[page_num]
            # Create a human-readable label for this page (1-indexed, not 0-indexed)
            label = "Page {}".format(page_num + 1)

            # -------- PART 1: Embedded annotation/hyperlink links --------
            # PDFs can have invisible clickable rectangles ("annotations") layered
            # on top of the text.  get_links() returns all of them as a list of
            # dictionaries.  Each dict has a "uri" key if it links to a URL.
            try:
                for link in page.get_links():
                    url = link.get("uri", "")    # the URL, or "" if no "uri" key
                    if url and url not in seen_embedded:
                        seen_embedded.add(url)   # mark so we don't add it twice
                        results.append(ExtractedUrl(
                            url=url,
                            source_file=self.source_name,
                            location=label,
                            context="",           # annotations don't have surrounding text
                            link_type="embedded",
                        ))
            except Exception as e:
                logger.warning("Link extraction failed on %s %s: %s", self.source_name, label, e)

            # -------- PART 2: Plain-text URLs in the page body --------
            # get_text() asks PyMuPDF to convert all the characters on this page
            # into a single string.  If the PDF is scanned (image only), this
            # returns an empty string.
            try:
                raw_text = page.get_text()
            except Exception:
                raw_text = ""

            if raw_text.strip():   # skip completely blank or unreadable pages
                has_extractable_text = True   # we know at least one page has real text

                # Fix hyphenated line-wraps before we run the URL regex.
                # sub("", raw_text) removes every hyphen-newline sequence,
                # effectively joining the broken halves of any URL.
                text = _HYPHEN_WRAP.sub("", raw_text)

                # extract_plain_urls scans the joined text for URL-shaped strings
                # and returns a list of (url, character_position) pairs.
                for url, pos in extract_plain_urls(text):
                    results.append(ExtractedUrl(
                        url=url,
                        source_file=self.source_name,
                        location=label,
                        context=get_context(text, pos),   # ~100 chars around the URL
                        link_type="plain-text",
                    ))

        # Always close the document when we are done — frees memory and file handle
        doc.close()

        # ----------------------------------------------------------------
        # PART 3: Scanned PDF warning
        # ----------------------------------------------------------------
        # If we processed all pages but found ZERO readable text AND ZERO
        # annotation links, the PDF is almost certainly a scanned image.
        # We can't read the URLs, so we add a special sentinel entry to tell
        # the UI to show a warning instead of silently returning nothing.
        if not has_extractable_text and not results:
            logger.warning(
                "%s appears to be a scanned PDF with no extractable text. OCR is required.",
                self.source_name,
            )
            results.append(ExtractedUrl(
                url="__SCANNED_PDF_WARNING__",     # special flag value the UI recognises
                source_file=self.source_name,
                location="Document",
                context="No extractable text — this may be a scanned PDF. OCR is needed.",
                link_type="plain-text",
            ))

        return results
