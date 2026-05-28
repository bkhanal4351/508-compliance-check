# =============================================================================
# status_classifier.py — The brain that decides if a URL is Alive, Suspicious,
# Dead, or Skipped.
#
# This module is kept completely separate from the HTTP code so it can be
# tested without making any real web requests (see tests/test_status_classifier.py).
# Every decision rule lives here in one place.
# =============================================================================

from typing import List, Optional, Tuple
from urllib.parse import urlparse   # splits a URL into its parts (scheme, host, path…)

from utils.constants import SOFT_404_PATTERNS  # the list of "page not found" phrases


def classify_url_result(
    original_url,       # type: str   — the URL as it appeared in the document
    status_code,        # type: Optional[int]  — HTTP response code, or None if no response
    final_url,          # type: Optional[str]  — where we actually ended up after redirects
    redirect_chain,     # type: List[Tuple[int, str]]  — each redirect hop
    body_preview,       # type: bytes  — first 5 KB of the response body
    error_type,         # type: Optional[str]  — "timeout", "dns", "ssl", etc.
):
    # type: (...) -> Tuple[str, Optional[str]]
    """
    Given everything we know about a URL check, return a verdict.

    Returns a pair: (tier, reason)
      tier   — one of "Alive", "Suspicious", "Dead", "Skipped"
      reason — a plain-English explanation, or None for Alive URLs
    """

    # -------------------------------------------------------------------------
    # CASE 1: We never got any HTTP response at all (connection-level failure)
    # -------------------------------------------------------------------------
    if status_code is None:
        # Map the type of network failure to a user-friendly message
        reasons = {
            "timeout":            "Request timed out after retry",
            "dns":                "DNS resolution failed — domain may not exist",
            "ssl":                "SSL/TLS certificate error",
            "connection_refused": "Connection refused by server",
        }
        # Look up the reason; fall back to a generic message if unknown
        return "Dead", reasons.get(error_type or "", "Connection error — could not reach server")

    # -------------------------------------------------------------------------
    # CASE 2: Server explicitly said the page is gone
    # 404 = "Not Found" — the page never existed or was deleted
    # 410 = "Gone"      — the page existed but was deliberately removed
    # -------------------------------------------------------------------------
    if status_code == 404:
        return "Dead", "404 Not Found"
    if status_code == 410:
        return "Dead", "410 Gone — resource permanently removed"

    # -------------------------------------------------------------------------
    # CASE 3: Server said the page exists but we can't read it
    # 401 = need to log in first
    # 403 = access denied (could be login, or could be bot blocking)
    # We mark these Suspicious rather than Dead because the page IS there —
    # a human reviewer may be able to access it normally.
    # -------------------------------------------------------------------------
    if status_code == 401:
        return "Suspicious", "401 Unauthorized — page exists but requires authentication"
    if status_code == 403:
        return "Suspicious", "403 Forbidden — page exists but access is blocked (may be bot protection)"

    # -------------------------------------------------------------------------
    # CASE 4: Server had an internal error (5xx codes = server's fault)
    # We already retried once, so mark Suspicious rather than Dead — the
    # server might recover later.
    # -------------------------------------------------------------------------
    if status_code >= 500:
        return "Suspicious", "{} Server Error after retry".format(status_code)

    # -------------------------------------------------------------------------
    # CASE 5: Server returned "OK" (200–299 range) — but we still do two more
    # checks because some servers lie and return 200 even for missing pages.
    # -------------------------------------------------------------------------
    if 200 <= status_code < 300:

        # --- Sub-check A: Soft-404 body scan ---
        # Read the first 5 KB of the page and look for phrases like
        # "page not found" or "no longer available".
        # If found, the server is returning a 200 but showing an error page.
        if body_preview:
            # Decode the raw bytes to a string; lowercase it for comparison
            body_lower = body_preview.decode("utf-8", errors="replace").lower()
            for pattern in SOFT_404_PATTERNS:
                if pattern in body_lower:
                    # Found a soft-404 phrase — flag as Suspicious
                    return "Suspicious", "Body matches soft-404 pattern: \"{}\"".format(pattern)

        # --- Sub-check B: Redirect-to-root / link rot detection ---
        # This catches the most common subtle link rot:
        # The cited URL was https://agency.gov/report/2019/policy but the agency
        # later deleted that page and set up a redirect so ALL old URLs now
        # point to the homepage (https://agency.gov/).  A naive checker sees
        # a 200 and calls it alive — we catch it.
        if redirect_chain and final_url:
            # Extract just the path part of both URLs
            # e.g. "https://agency.gov/report/2019" → "/report/2019"
            original_path = urlparse(original_url).path.rstrip("/")
            # e.g. "https://agency.gov/" → ""  (after stripping the slash)
            final_path = urlparse(final_url).path.rstrip("/")

            # If the original URL had a real path (not just the homepage)
            # AND the final destination has no path (it's the root), flag it
            if original_path and original_path != "/" and (not final_path or final_path == ""):
                return (
                    "Suspicious",
                    "Original URL had a deep path; redirect lands at root domain. "
                    "Cited content likely removed.",
                )

        # Passed all checks — the URL genuinely appears to be working
        return "Alive", None

    # -------------------------------------------------------------------------
    # CASE 6: Any other status code (1xx informational, or a bare 3xx redirect
    # that didn't resolve to a final page) — flag as Suspicious to be safe
    # -------------------------------------------------------------------------
    return "Suspicious", "Unexpected final status: {}".format(status_code)
