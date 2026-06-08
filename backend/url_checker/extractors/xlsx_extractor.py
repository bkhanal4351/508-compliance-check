# =============================================================================
# xlsx_extractor.py — Pulls every URL out of an Excel (.xlsx) file.
#
# Excel files store URLs in two ways:
#   1. "Embedded" hyperlinks — a cell with a clickable link.  In openpyxl these
#      are accessed through cell.hyperlink, which has a .target or .url attribute
#      holding the destination URL.  The visible cell text can be anything
#      (e.g. "Annual Report" linking to a PDF).
#   2. "Plain-text" URLs — URLs literally typed into a cell's value,
#      e.g. a cell that just contains "https://www.epa.gov/report".
# We scan every cell across every worksheet for both types.
# =============================================================================

import logging
from typing import List

from extractors.base import BaseExtractor, ExtractedUrl
from url_checker_utils.url_utils import extract_plain_urls, get_context

logger = logging.getLogger(__name__)


class XlsxExtractor(BaseExtractor):

    def extract(self):
        # type: () -> List[ExtractedUrl]
        """Open the .xlsx file and return every URL found inside it."""

        # openpyxl is the library that reads Excel files.
        # Lazy import so the app still loads if the library is missing.
        try:
            from openpyxl import load_workbook
        except ImportError:
            logger.error("openpyxl not installed")
            return []

        # Open the workbook in read-only mode for speed, and data_only=True so we
        # get cell values (not formulas).  If the file is corrupt, log and stop.
        #   read_only=True  — streams the file instead of loading it all into memory;
        #                      much faster for large spreadsheets.
        #   data_only=True  — returns cell values as computed numbers/strings,
        #                      not raw formulas like "=SUM(A1:A10)".
        try:
            wb = load_workbook(self.file_path, read_only=True, data_only=True)
        except Exception as e:
            logger.error("Cannot open %s: %s", self.file_path, e)
            return []

        results = []  # type: List[ExtractedUrl]

        # ----------------------------------------------------------------
        # Walk every worksheet (tab) in the workbook
        # ----------------------------------------------------------------
        for sheet_name in wb.sheetnames:
            try:
                ws = wb[sheet_name]   # get the worksheet object by name

                # iter_rows() streams every row in the sheet.
                # Each row is a tuple of cell objects.
                for row in ws.iter_rows():
                    for cell in row:
                        # cell.coordinate is the Excel address, e.g. "B12"
                        coord = cell.coordinate
                        # Human-readable location: "Sheet 'Budget', B12"
                        location = "Sheet '{}', {}".format(sheet_name, coord)

                        # -------- PART 1: Embedded hyperlinks --------
                        # cell.hyperlink is an object if the cell has a hyperlink,
                        # or None if it is just a plain cell.
                        try:
                            hl = cell.hyperlink
                            if hl:
                                # Different versions of openpyxl use either .target
                                # or .url; getattr with None fallback handles both.
                                url = getattr(hl, "target", None) or getattr(hl, "url", None)
                                if url:
                                    results.append(ExtractedUrl(
                                        url=url,
                                        source_file=self.source_name,
                                        location=location,
                                        # Use the cell's visible text (capped at 100 chars)
                                        # as context so reviewers know what the link says
                                        context=str(cell.value or "")[:100],
                                        link_type="embedded",
                                    ))
                        except Exception:
                            # Some cell structures raise errors on .hyperlink access;
                            # silently skip them and continue to the next cell.
                            pass

                        # -------- PART 2: Plain-text URLs in cell values --------
                        # val is the actual text content of the cell, or None if empty.
                        val = cell.value
                        # Only proceed if val is a non-empty string
                        # (numbers, dates, and None are not URLs).
                        if val and isinstance(val, str) and val.strip():
                            # extract_plain_urls scans the cell text for URL-shaped strings
                            for url, pos in extract_plain_urls(val):
                                results.append(ExtractedUrl(
                                    url=url,
                                    source_file=self.source_name,
                                    location=location,
                                    context=get_context(val, pos),   # ~100-char snippet
                                    link_type="plain-text",
                                ))

            except Exception as e:
                # If an entire sheet fails (e.g. it's encrypted or uses an
                # unsupported format), log a warning and continue with the next sheet.
                logger.warning("Error reading sheet '%s' in %s: %s", sheet_name, self.source_name, e)

        return results
