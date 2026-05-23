from pathlib import Path
from scanners.docx_scanner import scan_docx

FIXTURES = Path(__file__).parent / "fixtures"


def test_docx_finds_heading_skip():
    findings = scan_docx(str(FIXTURES / "sample.docx"))
    rules = {f.rule for f in findings}
    assert "docx-heading-skipped" in rules, f"Expected docx-heading-skipped, got: {rules}"


def test_docx_finds_table_no_header():
    findings = scan_docx(str(FIXTURES / "sample.docx"))
    rules = {f.rule for f in findings}
    assert "docx-table-no-header" in rules, f"Expected docx-table-no-header, got: {rules}"


def test_docx_returns_findings_with_location():
    findings = scan_docx(str(FIXTURES / "sample.docx"))
    assert findings
    for f in findings:
        assert f.location, f"Finding {f.rule} has no location"
        assert f.rule
        assert f.wcag_sc
        assert f.sec508_ref
