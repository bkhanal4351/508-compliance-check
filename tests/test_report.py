import pytest
from scanners.base import Finding, Severity
from report.builder import build_report


def _make_finding(rule: str, location: str, severity: Severity = Severity.SERIOUS) -> Finding:
    return Finding(
        id="test1234",
        rule=rule,
        wcag_sc="1.1.1",
        sec508_ref="E205.4",
        severity=severity,
        title=f"Test: {rule}",
        description="Test finding",
        location=location,
        source="deterministic",
    )


def test_build_report_structure():
    findings = [
        _make_finding("image-alt-missing", "Page 1: img", Severity.CRITICAL),
        _make_finding("link-text-generic", "Page 1: a", Severity.MODERATE),
        _make_finding("heading-order-skipped", "Page 1: h3", Severity.MODERATE),
    ]
    report = build_report(findings, "https://example.com", "url")
    assert report["scan_target"] == "https://example.com"
    assert report["scan_type"] == "url"
    assert report["summary"]["Critical"] == 1
    assert report["summary"]["Moderate"] == 2
    assert report["summary"]["total"] == 3
    assert report["scanned_at"]


def test_build_report_deduplication():
    f1 = _make_finding("image-alt-missing", "Page 1: img")
    f2 = _make_finding("image-alt-missing", "Page 1: img")  # duplicate
    f3 = _make_finding("link-text-generic", "Page 1: a")
    report = build_report([f1, f2, f3], "test.pdf", "document")
    assert report["summary"]["total"] == 2
    assert report["deduped_count"] == 1


def test_build_report_sort_order():
    findings = [
        _make_finding("link-text-generic", "z-location", Severity.MODERATE),
        _make_finding("image-alt-missing", "a-location", Severity.CRITICAL),
        _make_finding("heading-order-skipped", "m-location", Severity.SERIOUS),
    ]
    report = build_report(findings, "test", "url")
    severities = [f.severity for f in report["findings"]]
    assert severities[0] == Severity.CRITICAL
    assert severities[1] == Severity.SERIOUS
    assert severities[2] == Severity.MODERATE


def test_build_report_empty():
    report = build_report([], "test.pdf", "document")
    assert report["summary"]["total"] == 0
    assert report["findings"] == []
