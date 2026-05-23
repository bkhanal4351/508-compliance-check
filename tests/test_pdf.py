from pathlib import Path
from scanners.pdf import scan_pdf
from scanners.base import Severity

FIXTURES = Path(__file__).parent / "fixtures"


def test_untagged_pdf_emits_critical():
    findings = scan_pdf(str(FIXTURES / "untagged.pdf"))
    rules = {f.rule for f in findings}
    assert "pdf-untagged" in rules, f"Expected pdf-untagged finding, got: {rules}"
    critical = [f for f in findings if f.rule == "pdf-untagged"]
    assert critical[0].severity == Severity.CRITICAL


def test_tagged_pdf_no_untagged_finding():
    findings = scan_pdf(str(FIXTURES / "tagged.pdf"))
    untagged = [f for f in findings if f.rule == "pdf-untagged"]
    assert not untagged, f"Tagged PDF should not emit pdf-untagged: {[f.description for f in untagged]}"


def test_pdf_finding_fields_populated():
    findings = scan_pdf(str(FIXTURES / "untagged.pdf"))
    assert findings
    f = findings[0]
    assert f.id
    assert f.rule
    assert f.wcag_sc
    assert f.sec508_ref
    assert f.severity
    assert f.title
    assert f.description
    assert f.source == "deterministic"
