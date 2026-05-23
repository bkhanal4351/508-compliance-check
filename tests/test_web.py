import pytest
from pathlib import Path
from scanners.web import scan_url

FIXTURES = Path(__file__).parent / "fixtures"
BAD_HTML = FIXTURES / "bad.html"
GOOD_HTML = FIXTURES / "good.html"


def test_bad_html_finds_violations():
    url = BAD_HTML.as_uri()
    findings = scan_url(url, max_depth=0, max_pages=1, use_semantic=False)
    assert len(findings) >= 5, f"Expected >=5 findings, got {len(findings)}: {[f.rule for f in findings]}"
    rule_ids = {f.rule for f in findings}
    assert len(rule_ids) >= 3, f"Expected >=3 distinct rules, got {rule_ids}"


def test_good_html_minimal_violations():
    url = GOOD_HTML.as_uri()
    findings = scan_url(url, max_depth=0, max_pages=1, use_semantic=False)
    critical = [f for f in findings if f.severity.value == "Critical"]
    assert len(critical) == 0, f"Good HTML should have no Critical findings: {[(f.rule, f.location) for f in critical]}"


def test_finding_fields_populated():
    url = BAD_HTML.as_uri()
    findings = scan_url(url, max_depth=0, max_pages=1, use_semantic=False)
    assert findings, "No findings returned"
    f = findings[0]
    assert f.id
    assert f.rule
    assert f.wcag_sc
    assert f.sec508_ref
    assert f.severity
    assert f.title
    assert f.description
    assert f.location
    assert f.source == "deterministic"
