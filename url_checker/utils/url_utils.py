# =============================================================================
# url_utils.py — Helper functions for finding, cleaning, and classifying URLs.
# Every other module that deals with URLs calls these helpers so the logic
# lives in one place and doesn't get copy-pasted everywhere.
# =============================================================================

import re
from typing import List, Optional, Tuple
from urllib.parse import urlparse, urlunparse

# A "regular expression" (search pattern) that finds URLs inside plain text.
# It looks for text that starts with http://, https://, or www. and then
# grabs everything after it until it hits a space or a punctuation character
# that would not be part of a URL (like a closing bracket or a comma).
# re.IGNORECASE means it also matches HTTP:// or HTTPS:// with capital letters.
URL_REGEX = re.compile(
    r'(?:https?://|www\.)[^\s<>"\'\)\]\}\,\|\\\^`]+',
    re.IGNORECASE,
)

# URL schemes (the part before "://") that are never real web pages and
# should be ignored without even trying to visit them.
# mailto: = email address, tel: = phone number, javascript: = browser script, etc.
_SKIP_SCHEMES = {"mailto", "tel", "javascript", "ftp", "data", "file", "urn"}


def extract_plain_urls(text):
    # type: (str) -> List[Tuple[str, int]]
    """
    Scan a block of text and return every URL found, along with its position.
    Returns a list of pairs: (the_url, where_it_starts_in_the_text).
    The position is used later to grab the surrounding context (the sentence around the link).
    """
    results = []
    # finditer walks through the text and yields every match of URL_REGEX
    for m in URL_REGEX.finditer(text):
        # m.group() is the matched URL text
        # rstrip removes trailing punctuation that got accidentally included
        # (e.g. a URL followed by a period at the end of a sentence)
        url = m.group().rstrip(".,;:!?)'\"")
        # m.start() is the character position in the text where the URL begins
        results.append((url, m.start()))
    return results


def normalize_url(url):
    # type: (str) -> str
    """
    Produce a "standard form" of a URL used for deduplication.
    Two URLs that look slightly different but point to the same page
    (e.g. HTTP vs http, trailing slash or not) will get the same
    normalized form and be treated as one URL, not two.
    """
    try:
        # urlparse splits the URL into its parts: scheme, host, path, etc.
        p = urlparse(url.strip())               # strip() removes leading/trailing spaces
        # Make the scheme (http/https) and host (example.com) lowercase
        # so "HTTP://Example.COM/page" equals "http://example.com/page"
        p = p._replace(scheme=p.scheme.lower(), netloc=p.netloc.lower())
        # Reassemble the URL parts back into a single string
        s = urlunparse(p)
        # Remove a trailing slash if the URL has a real path after the host,
        # so "example.com/page/" and "example.com/page" are treated the same.
        # We do NOT strip the slash if the path IS just "/" (the homepage).
        if s.endswith("/") and p.path not in ("/", ""):
            s = s.rstrip("/")
        return s
    except Exception:
        # If anything goes wrong just return the URL unchanged
        return url


def classify_skip_reason(url):
    # type: (str) -> Optional[str]
    """
    Decide whether a URL should be skipped entirely (not checked at all).
    Returns a human-readable reason string if it should be skipped,
    or None if it is a real web URL worth checking.
    """
    url = url.strip()

    # Completely empty string — nothing to check
    if not url:
        return "Empty URL"

    # Anchor-only links (e.g. "#section-3") point to a position on the
    # current page, not to an external resource — nothing to visit
    if url.startswith("#"):
        return "Anchor-only link"

    try:
        # Break the URL into parts so we can inspect the scheme, host, etc.
        p = urlparse(url)
    except Exception:
        return "Malformed URL"

    # Grab the scheme (the part before "://") and lowercase it
    scheme = p.scheme.lower()

    # If the scheme is one of the known non-web types, skip it
    if scheme in _SKIP_SCHEMES:
        return "{}: link".format(scheme)

    # If there's no scheme AND no host, it's a relative path like "/about"
    # which only makes sense in context of a specific website — skip it
    if not scheme and not p.netloc:
        return "Relative URL"

    # If the scheme is http/https but there's no hostname (e.g. "https://"),
    # the URL is broken and we can't visit it
    if scheme in ("http", "https") and not p.netloc:
        return "Malformed URL (missing host)"

    # Passed all checks — this is a real URL worth checking
    return None


def is_epa_internal(url):
    # type: (str) -> bool
    """
    Returns True if the URL is on an EPA government domain (*.epa.gov).
    Used to visually flag internal links separately from external ones,
    since a broken internal link needs to be fixed by EPA staff directly.
    """
    try:
        # urlparse(url).netloc extracts just the hostname part (e.g. "www.epa.gov")
        return urlparse(url).netloc.lower().endswith(".epa.gov")
    except Exception:
        return False


def get_context(text, pos, window=50):
    # type: (str, int, int) -> str
    """
    Return a short snippet of text surrounding the URL at position `pos`.
    This gives reviewers a "preview" of the sentence where the link appeared,
    so they know what the link was referring to in the document.

    window=50 means we grab 50 characters before and after the URL position.
    """
    # Don't go before the beginning of the text
    start = max(0, pos - window)
    # Don't go past the end of the text
    end = min(len(text), pos + window)
    # Extract that slice, then flatten newlines so it displays on one line
    return text[start:end].replace("\n", " ").replace("\r", "").strip()
