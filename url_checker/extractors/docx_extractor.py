import logging
from typing import List, Set

from extractors.base import BaseExtractor, ExtractedUrl
from utils.url_utils import extract_plain_urls, get_context

logger = logging.getLogger(__name__)


class DocxExtractor(BaseExtractor):
    def extract(self):
        # type: () -> List[ExtractedUrl]
        try:
            from docx import Document
        except ImportError:
            logger.error("python-docx not installed")
            return []

        try:
            doc = Document(self.file_path)
        except Exception as e:
            logger.error("Cannot open %s: %s", self.file_path, e)
            return []

        results = []   # type: List[ExtractedUrl]
        seen_embedded = set()  # type: Set[str]

        # --- Embedded hyperlinks via document relationships ---
        try:
            for rel in doc.part.rels.values():
                if "hyperlink" in rel.reltype and rel.is_external:
                    url = rel.target_ref
                    if url and url not in seen_embedded:
                        seen_embedded.add(url)
                        results.append(ExtractedUrl(
                            url=url,
                            source_file=self.source_name,
                            location="Document (hyperlink relationship)",
                            context="",
                            link_type="embedded",
                        ))
        except Exception as e:
            logger.warning("Could not read hyperlink rels from %s: %s", self.source_name, e)

        # Headers and footers
        for part_name in ("header", "footer"):
            try:
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
                pass

        # --- Plain-text URLs in paragraphs ---
        for i, para in enumerate(_all_paragraphs(doc), 1):
            text = para.text
            if not text.strip():
                continue
            for url, pos in extract_plain_urls(text):
                results.append(ExtractedUrl(
                    url=url,
                    source_file=self.source_name,
                    location="Paragraph {}".format(i),
                    context=get_context(text, pos),
                    link_type="plain-text",
                ))

        return results


def _all_paragraphs(doc):
    """Yield all paragraphs including those inside tables."""
    for para in doc.paragraphs:
        yield para
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for para in cell.paragraphs:
                    yield para
