from pathlib import Path
from scanners.pptx_scanner import scan_pptx

FIXTURES = Path(__file__).parent / "fixtures"


def test_pptx_finds_missing_title():
    findings = scan_pptx(str(FIXTURES / "sample.pptx"))
    rules = {f.rule for f in findings}
    assert "pptx-slide-title-missing" in rules, f"Expected pptx-slide-title-missing, got: {rules}"


def test_pptx_finding_fields_populated():
    findings = scan_pptx(str(FIXTURES / "sample.pptx"))
    assert findings
    f = findings[0]
    assert f.rule
    assert f.wcag_sc
    assert f.sec508_ref
    assert f.severity
    assert f.location
    assert f.source == "deterministic"
