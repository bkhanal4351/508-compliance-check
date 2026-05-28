# =============================================================================
# base.py — Shared data structures and the abstract base class for extractors.
#
# Think of this file as the "blueprint" file.  It defines the shape of the
# data that flows through the entire application:
#   1. UrlLocation  — where inside a document a URL was found
#   2. ExtractedUrl — a URL pulled out of a document (before checking)
#   3. CheckResult  — the full result after a URL has been checked
#   4. BaseExtractor — the template every document extractor must follow
# =============================================================================

from abc import ABC, abstractmethod          # ABC = Abstract Base Class toolkit
from dataclasses import dataclass, field     # dataclass auto-generates __init__ etc.
from datetime import datetime                # for timestamps
from pathlib import Path                     # cross-platform file path handling
from typing import List, Optional, Tuple     # type hints for older Python


# @dataclass automatically creates an __init__ method so we don't have to
# write one by hand.  It also makes the object printable for debugging.

@dataclass
class UrlLocation:
    """
    Records WHERE inside a document a particular URL was found.
    A single URL might appear in multiple places — each appearance
    gets its own UrlLocation object.
    """
    source_file: str  # The filename, e.g. "policy_doc.docx"
    location: str     # Human-readable position: "Page 3", "Slide 2", "Paragraph 12"
    context: str      # ~100-char text snippet surrounding the URL in the document
    link_type: str    # "embedded" = clickable hyperlink; "plain-text" = URL typed in text


@dataclass
class ExtractedUrl:
    """
    A URL that was found inside a document, before we have checked whether
    it actually works.  The extractor creates one of these for every URL it finds.
    """
    url: str          # The URL itself, exactly as it appeared in the document
    source_file: str  # Which file it came from
    location: str     # Where in that file (page number, paragraph, etc.)
    context: str      # Text surrounding the URL (helps reviewers understand context)
    link_type: str    # "embedded" or "plain-text"


@dataclass
class CheckResult:
    """
    Everything we know about a URL after it has been checked.
    One CheckResult is created for each unique URL across all uploaded documents.
    """
    # The original URL exactly as it appeared in the document
    url: str

    # If the server redirected us somewhere else, this is where we ended up.
    # None if the URL worked without any redirect or if the check failed.
    final_url: Optional[str]

    # The HTTP status number the server replied with (200=OK, 404=Not Found, etc.)
    # None if we never got a response (e.g. the site timed out or DNS failed)
    status_code: Optional[int]

    # Our verdict: "Alive", "Suspicious", "Dead", or "Skipped"
    tier: str

    # How many redirects happened before we got a final response (0 = no redirects)
    redirect_count: int

    # The full list of redirect steps, each as (status_code, url).
    # e.g. [(301, "http://old.gov/page"), (302, "https://new.gov/page")]
    redirect_chain: List[Tuple[int, str]]

    # How long the request took, in milliseconds
    response_time_ms: float

    # If the request failed with a connection error, what kind of error was it?
    # "timeout", "dns", "ssl", "connection_refused", or None if we got a response
    error_type: Optional[str]

    # Plain-English explanation of why we flagged this URL as Dead or Suspicious.
    # None for Alive URLs (no explanation needed).
    reason: Optional[str]

    # The <title> tag of the page, if we were asked to fetch it. None otherwise.
    page_title: Optional[str]

    # True if the URL is on an *.epa.gov domain (internal link)
    is_epa_internal: bool

    # If the URL is Dead, the URL of the last-known archived snapshot on
    # the Wayback Machine (archive.org). None if no snapshot exists.
    wayback_url: Optional[str] = None

    # Human-readable date of the Wayback snapshot, e.g. "Apr 15, 2023".
    wayback_snapshot_date: Optional[str] = None

    # All the places in all uploaded documents where this URL appeared.
    # field(default_factory=list) means "start with an empty list by default".
    locations: List[UrlLocation] = field(default_factory=list)

    # When the check was performed (UTC time). Filled in automatically.
    checked_at: datetime = field(default_factory=datetime.utcnow)


class BaseExtractor(ABC):
    """
    Template (abstract base class) that every document-type extractor must follow.

    Think of it like a job description: any extractor that wants to work in
    this app must be able to accept a file path and produce a list of ExtractedUrl
    objects.  The ABC machinery will raise an error at startup if a subclass
    forgets to implement the extract() method.
    """

    def __init__(self, file_path):
        # Store the file path as a Path object (works on Windows and Mac alike)
        self.file_path = Path(file_path)
        # Keep just the filename (e.g. "report.pdf") for display in results
        self.source_name = self.file_path.name

    @abstractmethod
    def extract(self):
        # type: () -> List[ExtractedUrl]
        """
        Open the document and return every URL found inside it.
        MUST NOT raise an exception — if something goes wrong, return [].
        Each concrete extractor (DocxExtractor, PdfExtractor, etc.) overrides this.
        """
        ...
