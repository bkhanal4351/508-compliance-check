# conftest.py — pytest configuration loaded automatically before any test runs.
#
# All domain modules (scanners, report, utils, url_checker) now live inside
# backend/ rather than the project root.  This file adds backend/ to Python's
# module search path so test files can still write:
#
#   from scanners.pdf import scan_pdf
#   from report.builder import build_report
#
# without any changes to the test files themselves.
#
# It also adds backend/url_checker/ so the url_checker's internal imports
# ("from extractors.base import ...") resolve the same way they do at runtime.

import sys
from pathlib import Path

BACKEND = Path(__file__).parent.parent / "backend"

# backend/ → lets tests import scanners, report, utils
sys.path.insert(0, str(BACKEND))

# backend/url_checker/ → lets url_checker's own modules import each other
sys.path.insert(0, str(BACKEND / "url_checker"))
