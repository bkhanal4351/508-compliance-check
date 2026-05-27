import logging
from typing import List

from extractors.base import BaseExtractor, ExtractedUrl
from utils.url_utils import extract_plain_urls, get_context

logger = logging.getLogger(__name__)


class PptxExtractor(BaseExtractor):
    def extract(self):
        # type: () -> List[ExtractedUrl]
        try:
            from pptx import Presentation
        except ImportError:
            logger.error("python-pptx not installed")
            return []

        try:
            prs = Presentation(self.file_path)
        except Exception as e:
            logger.error("Cannot open %s: %s", self.file_path, e)
            return []

        results = []  # type: List[ExtractedUrl]

        for slide_num, slide in enumerate(prs.slides, 1):
            label = "Slide {}".format(slide_num)
            for shape in slide.shapes:
                if not shape.has_text_frame:
                    continue
                for para in shape.text_frame.paragraphs:
                    para_text = para.text
                    for run in para.runs:
                        try:
                            if run.hyperlink and run.hyperlink.address:
                                results.append(ExtractedUrl(
                                    url=run.hyperlink.address,
                                    source_file=self.source_name,
                                    location=label,
                                    context=para_text[:100],
                                    link_type="embedded",
                                ))
                        except Exception:
                            pass

                    if para_text.strip():
                        for url, pos in extract_plain_urls(para_text):
                            results.append(ExtractedUrl(
                                url=url,
                                source_file=self.source_name,
                                location=label,
                                context=get_context(para_text, pos),
                                link_type="plain-text",
                            ))

        return results
