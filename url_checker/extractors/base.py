from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple


@dataclass
class UrlLocation:
    source_file: str
    location: str   # "Page 3", "Slide 2", "Sheet 'Data' B4", "Paragraph 12"
    context: str    # ~100-char snippet surrounding the URL
    link_type: str  # "embedded" | "plain-text"


@dataclass
class ExtractedUrl:
    url: str
    source_file: str
    location: str
    context: str
    link_type: str  # "embedded" | "plain-text"


@dataclass
class CheckResult:
    url: str
    final_url: Optional[str]                        # URL after all redirects (None if same or error)
    status_code: Optional[int]
    tier: str                                        # "Alive" | "Suspicious" | "Dead" | "Skipped"
    redirect_count: int
    redirect_chain: List[Tuple[int, str]]            # [(status_code, url), ...] each hop
    response_time_ms: float
    error_type: Optional[str]                        # "timeout"|"dns"|"ssl"|"connection_refused"|None
    reason: Optional[str]                            # Human note for Suspicious / Dead / Skipped
    page_title: Optional[str]
    is_epa_internal: bool
    locations: List[UrlLocation] = field(default_factory=list)
    checked_at: datetime = field(default_factory=datetime.utcnow)


class BaseExtractor(ABC):
    def __init__(self, file_path):
        self.file_path = Path(file_path)
        self.source_name = self.file_path.name

    @abstractmethod
    def extract(self):
        # type: () -> List[ExtractedUrl]
        """Extract all URLs from the document. Must not raise — return [] on error."""
        ...
