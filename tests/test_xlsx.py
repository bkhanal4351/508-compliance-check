from pathlib import Path
from scanners.xlsx_scanner import scan_xlsx

FIXTURES = Path(__file__).parent / "fixtures"


def test_xlsx_finds_default_sheet_name():
    findings = scan_xlsx(str(FIXTURES / "sample.xlsx"))
    rules = {f.rule for f in findings}
    assert "xlsx-default-sheet-name" in rules, f"Expected xlsx-default-sheet-name, got: {rules}"


def test_xlsx_finds_no_table_structure():
    findings = scan_xlsx(str(FIXTURES / "sample.xlsx"))
    rules = {f.rule for f in findings}
    assert "xlsx-no-table-structure" in rules, f"Expected xlsx-no-table-structure, got: {rules}"


def test_xlsx_finding_fields_populated():
    findings = scan_xlsx(str(FIXTURES / "sample.xlsx"))
    assert findings
    f = findings[0]
    assert f.rule
    assert f.wcag_sc
    assert f.sec508_ref
    assert f.severity
    assert f.location
    assert f.source == "deterministic"
