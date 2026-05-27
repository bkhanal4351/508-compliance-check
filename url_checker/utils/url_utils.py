import re
from typing import List, Optional, Tuple
from urllib.parse import urlparse, urlunparse

# Matches http://, https://, and bare www. URLs; stops at whitespace and common delimiters
URL_REGEX = re.compile(
    r'(?:https?://|www\.)[^\s<>"\'\)\]\}\,\|\\\^`]+',
    re.IGNORECASE,
)

_SKIP_SCHEMES = {"mailto", "tel", "javascript", "ftp", "data", "file", "urn"}


def extract_plain_urls(text):
    # type: (str) -> List[Tuple[str, int]]
    """Return [(url, start_pos), ...] for all URLs found in plain text."""
    results = []
    for m in URL_REGEX.finditer(text):
        url = m.group().rstrip(".,;:!?)'\"")
        results.append((url, m.start()))
    return results


def normalize_url(url):
    # type: (str) -> str
    """Lowercase scheme+host; strip trailing slash except for bare roots."""
    try:
        p = urlparse(url.strip())
        p = p._replace(scheme=p.scheme.lower(), netloc=p.netloc.lower())
        s = urlunparse(p)
        if s.endswith("/") and p.path not in ("/", ""):
            s = s.rstrip("/")
        return s
    except Exception:
        return url


def classify_skip_reason(url):
    # type: (str) -> Optional[str]
    """Return a skip reason string if this URL should not be checked, else None."""
    url = url.strip()
    if not url:
        return "Empty URL"
    if url.startswith("#"):
        return "Anchor-only link"

    try:
        p = urlparse(url)
    except Exception:
        return "Malformed URL"

    scheme = p.scheme.lower()

    if scheme in _SKIP_SCHEMES:
        return "{}: link".format(scheme)

    if not scheme and not p.netloc:
        return "Relative URL"

    if scheme in ("http", "https") and not p.netloc:
        return "Malformed URL (missing host)"

    return None


def is_epa_internal(url):
    # type: (str) -> bool
    try:
        return urlparse(url).netloc.lower().endswith(".epa.gov")
    except Exception:
        return False


def get_context(text, pos, window=50):
    # type: (str, int, int) -> str
    """Return up to `window` characters before and after `pos`, single-line."""
    start = max(0, pos - window)
    end = min(len(text), pos + window)
    return text[start:end].replace("\n", " ").replace("\r", "").strip()
