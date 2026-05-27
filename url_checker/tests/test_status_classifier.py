"""
Unit tests for validators/status_classifier.py — covers every tier's trigger conditions.
Run from url_checker/: pytest tests/test_status_classifier.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from validators.status_classifier import classify_url_result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _classify(url="https://example.com/page", status=200, final_url=None,
               chain=None, body=b"<html><body>Normal content</body></html>",
               error_type=None):
    return classify_url_result(
        url, status, final_url or url, chain or [], body, error_type
    )


# ---------------------------------------------------------------------------
# Alive
# ---------------------------------------------------------------------------

def test_alive_200_clean_body():
    tier, reason = _classify(status=200)
    assert tier == "Alive"
    assert reason is None


def test_alive_200_no_body():
    tier, reason = _classify(status=200, body=b"")
    assert tier == "Alive"
    assert reason is None


def test_alive_redirect_to_non_root():
    tier, reason = classify_url_result(
        "https://example.com/old-path",
        200,
        "https://example.com/new-path",
        [(301, "https://example.com/old-path")],
        b"<html><body>Redirected content</body></html>",
        None,
    )
    assert tier == "Alive"
    assert reason is None


def test_alive_root_to_root_redirect():
    """Redirecting from root to root (e.g., http → https) is Alive."""
    tier, reason = classify_url_result(
        "https://example.com/",
        200,
        "https://www.example.com/",
        [(301, "https://example.com/")],
        b"<html><body>Home</body></html>",
        None,
    )
    assert tier == "Alive"


def test_alive_201():
    tier, reason = _classify(status=201)
    assert tier == "Alive"


def test_alive_204():
    tier, reason = _classify(status=204, body=b"")
    assert tier == "Alive"


# ---------------------------------------------------------------------------
# Dead
# ---------------------------------------------------------------------------

def test_dead_404():
    tier, reason = _classify(status=404)
    assert tier == "Dead"
    assert "404" in reason


def test_dead_410():
    tier, reason = _classify(status=410)
    assert tier == "Dead"
    assert "410" in reason or "Gone" in reason


def test_dead_timeout():
    tier, reason = classify_url_result(
        "https://example.com/", None, None, [], b"", "timeout"
    )
    assert tier == "Dead"
    assert "timed out" in reason.lower()


def test_dead_dns():
    tier, reason = classify_url_result(
        "https://nonexistent.invalid/", None, None, [], b"", "dns"
    )
    assert tier == "Dead"
    assert "dns" in reason.lower() or "domain" in reason.lower()


def test_dead_ssl():
    tier, reason = classify_url_result(
        "https://bad-ssl.example.com/", None, None, [], b"", "ssl"
    )
    assert tier == "Dead"
    assert "ssl" in reason.lower() or "tls" in reason.lower() or "certificate" in reason.lower()


def test_dead_connection_refused():
    tier, reason = classify_url_result(
        "https://localhost:19999/", None, None, [], b"", "connection_refused"
    )
    assert tier == "Dead"
    assert "refused" in reason.lower()


def test_dead_unknown_error():
    tier, reason = classify_url_result(
        "https://example.com/", None, None, [], b"", "unknown"
    )
    assert tier == "Dead"


# ---------------------------------------------------------------------------
# Suspicious
# ---------------------------------------------------------------------------

def test_suspicious_403():
    tier, reason = _classify(status=403)
    assert tier == "Suspicious"
    assert "403" in reason or "Forbidden" in reason


def test_suspicious_401():
    tier, reason = _classify(status=401)
    assert tier == "Suspicious"
    assert "401" in reason or "Unauthorized" in reason


def test_suspicious_503():
    tier, reason = _classify(status=503)
    assert tier == "Suspicious"
    assert "503" in reason or "Error" in reason


def test_suspicious_500():
    tier, reason = _classify(status=500)
    assert tier == "Suspicious"


def test_suspicious_soft404_page_not_found():
    tier, reason = _classify(
        status=200,
        body=b"<html><h1>Page Not Found</h1><p>Sorry.</p></html>",
    )
    assert tier == "Suspicious"
    assert "soft-404" in reason.lower() or "page not found" in reason.lower()


def test_suspicious_soft404_no_longer_available():
    tier, reason = _classify(
        status=200,
        body=b"<html><body>This content is no longer available.</body></html>",
    )
    assert tier == "Suspicious"


def test_suspicious_soft404_has_been_removed():
    tier, reason = _classify(
        status=200,
        body=b"<html><body>This page has been removed from our site.</body></html>",
    )
    assert tier == "Suspicious"


def test_suspicious_soft404_doesnt_exist():
    tier, reason = _classify(
        status=200,
        body=b"<html><body>The page you requested doesn't exist.</body></html>",
    )
    assert tier == "Suspicious"


def test_suspicious_redirect_to_root_deep_path():
    """Original URL has a deep path; final URL is root → Suspicious (link rot)."""
    tier, reason = classify_url_result(
        "https://treasury.gov/resource-center/data/2019-report",
        200,
        "https://treasury.gov/",
        [(301, "https://treasury.gov/resource-center/data/2019-report")],
        b"<html><body>Welcome to Treasury</body></html>",
        None,
    )
    assert tier == "Suspicious"
    assert "root" in reason.lower() or "removed" in reason.lower()


def test_suspicious_redirect_to_root_empty_path():
    """Final URL has empty path (no trailing slash)."""
    tier, reason = classify_url_result(
        "https://gsa.gov/portal/content/104790",
        200,
        "https://gsa.gov",
        [(301, "https://gsa.gov/portal/content/104790")],
        b"<html><body>GSA Home</body></html>",
        None,
    )
    assert tier == "Suspicious"


def test_suspicious_redirect_non_root_is_alive():
    """A redirect that lands on a non-root page is still Alive."""
    tier, reason = classify_url_result(
        "https://example.com/old",
        200,
        "https://example.com/new-location/page",
        [(301, "https://example.com/old")],
        b"<html><body>Content</body></html>",
        None,
    )
    assert tier == "Alive"


def test_soft404_case_insensitive():
    """Soft-404 patterns must match case-insensitively."""
    tier, reason = _classify(
        status=200,
        body=b"<html><body>PAGE NOT FOUND - please go home</body></html>",
    )
    assert tier == "Suspicious"
