from typing import List, Optional, Tuple
from urllib.parse import urlparse

from utils.constants import SOFT_404_PATTERNS


def classify_url_result(
    original_url,       # type: str
    status_code,        # type: Optional[int]
    final_url,          # type: Optional[str]
    redirect_chain,     # type: List[Tuple[int, str]]
    body_preview,       # type: bytes
    error_type,         # type: Optional[str]
):
    # type: (...) -> Tuple[str, Optional[str]]
    """
    Determine the status tier and reason for a checked URL.

    Returns (tier, reason) where tier is one of:
      "Alive" | "Suspicious" | "Dead" | "Skipped"
    and reason is a human-readable note (None for Alive).
    """

    # Error conditions (no HTTP response) → Dead
    if status_code is None:
        reasons = {
            "timeout":            "Request timed out after retry",
            "dns":                "DNS resolution failed — domain may not exist",
            "ssl":                "SSL/TLS certificate error",
            "connection_refused": "Connection refused by server",
        }
        return "Dead", reasons.get(error_type or "", "Connection error — could not reach server")

    # Hard 404 / 410 → Dead
    if status_code == 404:
        return "Dead", "404 Not Found"
    if status_code == 410:
        return "Dead", "410 Gone — resource permanently removed"

    # Auth walls → Suspicious (page exists, blocked)
    if status_code == 401:
        return "Suspicious", "401 Unauthorized — page exists but requires authentication"
    if status_code == 403:
        return "Suspicious", "403 Forbidden — page exists but access is blocked (may be bot protection)"

    # 5xx after retry → Suspicious
    if status_code >= 500:
        return "Suspicious", "{} Server Error after retry".format(status_code)

    # 2xx: run deeper checks
    if 200 <= status_code < 300:
        # Soft-404 body scan (case-insensitive)
        if body_preview:
            body_lower = body_preview.decode("utf-8", errors="replace").lower()
            for pattern in SOFT_404_PATTERNS:
                if pattern in body_lower:
                    return "Suspicious", "Body matches soft-404 pattern: \"{}\"".format(pattern)

        # Redirect-to-root / link-rot detection.
        # If the original URL had a non-trivial path and the final URL is root,
        # the cited content was likely removed and the site silently redirected home.
        if redirect_chain and final_url:
            original_path = urlparse(original_url).path.rstrip("/")
            final_path = urlparse(final_url).path.rstrip("/")
            if original_path and original_path != "/" and (not final_path or final_path == ""):
                return (
                    "Suspicious",
                    "Original URL had a deep path; redirect lands at root domain. "
                    "Cited content likely removed.",
                )

        return "Alive", None

    # Anything else (1xx, bare 3xx without a resolved final page, etc.)
    return "Suspicious", "Unexpected final status: {}".format(status_code)
