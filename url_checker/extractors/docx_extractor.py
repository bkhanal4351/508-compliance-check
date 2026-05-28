# =============================================================================
# docx_extractor.py — Pulls every URL out of a Microsoft Word (.docx) file.
#
# Word documents store URLs in two different ways:
#   1. "Embedded" hyperlinks — text the user clicked that has a URL behind it.
#      These live in the document's relationship file, not in the visible text.
#   2. "Plain-text" URLs — URLs literally typed into the document body,
#      e.g. "Visit https://www.epa.gov for more information."
# We collect both types.
# =============================================================================

import logging
from typing import List, Set

from extractors.base import BaseExtractor, ExtractedUrl
from utils.url_utils import extract_plain_urls, get_context

logger = logging.getLogger(__name__)


class DocxExtractor(BaseExtractor):

    def extract(self):
        # type: () -> List[ExtractedUrl]
        """Open the .docx file and return every URL found inside it."""

        # python-docx is the library that reads Word files.
        # We import it here (not at the top) so the app still loads even if
        # python-docx is not installed — the error is shown per-file, not at startup.
        try:
            from docx import Document
        except ImportError:
            logger.error("python-docx not installed")
            return []

        # Try to open the file; if it's corrupt or not a valid .docx, log and stop
        try:
            doc = Document(self.file_path)
        except Exception as e:
            logger.error("Cannot open %s: %s", self.file_path, e)
            return []

        results = []         # type: List[ExtractedUrl]  — will grow as we find URLs
        seen_embedded = set()  # type: Set[str]  — tracks URLs already added to avoid duplicates

        # ----------------------------------------------------------------
        # PART 1: Embedded hyperlinks stored in document relationships
        # ----------------------------------------------------------------
        # Word stores clickable links in a "relationships" table inside the .docx
        # ZIP file.  doc.part.rels is a dictionary of those relationships.
        try:
            for rel in doc.part.rels.values():
                # We only want hyperlink relationships that point to external URLs
                # (as opposed to internal cross-references between document sections)
                if "hyperlink" in rel.reltype and rel.is_external:
                    url = rel.target_ref      # the actual URL string
                    if url and url not in seen_embedded:
                        seen_embedded.add(url)   # mark as seen to avoid duplicates
                        results.append(ExtractedUrl(
                            url=url,
                            source_file=self.source_name,
                            location="Document (hyperlink relationship)",
                            context="",         # no surrounding text for relationship-based links
                            link_type="embedded",
                        ))
        except Exception as e:
            logger.warning("Could not read hyperlink rels from %s: %s", self.source_name, e)

        # Also check headers and footers — they have their own separate relationship tables
        for part_name in ("header", "footer"):
            try:
                # getattr(doc, "headers") or getattr(doc, "footers") returns a list
                for part in getattr(doc, "{}s".format(part_name), []):
                    for rel in part.part.rels.values():
                        if "hyperlink" in rel.reltype and rel.is_external:
                            url = rel.target_ref
                            if url and url not in seen_embedded:
                                seen_embedded.add(url)
                                results.append(ExtractedUrl(
                                    url=url,
                                    source_file=self.source_name,
                                    location="Document ({} hyperlink)".format(part_name),
                                    context="",
                                    link_type="embedded",
                                ))
            except Exception:
                pass  # headers/footers are optional; silently skip if they cause problems

        # ----------------------------------------------------------------
        # PART 2: Plain-text URLs in the document body and tables
        # ----------------------------------------------------------------
        # We walk every paragraph (including those inside tables) and use a
        # regex to find any URL-shaped text.
        for i, para in enumerate(_all_paragraphs(doc), 1):
            text = para.text         # the full visible text of this paragraph
            if not text.strip():     # skip empty paragraphs
                continue
            # extract_plain_urls returns [(url, position_in_text), ...]
            for url, pos in extract_plain_urls(text):
                results.append(ExtractedUrl(
                    url=url,
                    source_file=self.source_name,
                    location="Paragraph {}".format(i),
                    context=get_context(text, pos),   # ~50 chars before and after the URL
                    link_type="plain-text",
                ))

        return results


def _all_paragraphs(doc):
    """
    Generator that yields every paragraph in the document, including paragraphs
    that live inside table cells (which doc.paragraphs alone misses).
    """
    # Yield top-level body paragraphs first
    for para in doc.paragraphs:
        yield para
    # Then dive into every table → row → cell → paragraph
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for para in cell.paragraphs:
                    yield para
