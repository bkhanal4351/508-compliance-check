from typing import Tuple
from scanners.base import Severity

# rule_id -> (wcag_sc, sec508_ref, default_severity)
_REFS: dict[str, Tuple[str, str, Severity]] = {
    "image-alt-missing":            ("1.1.1",       "E205.4", Severity.CRITICAL),
    "image-alt-not-meaningful":     ("1.1.1",       "E205.4", Severity.SERIOUS),
    "color-contrast-insufficient":  ("1.4.3",       "E207.2", Severity.SERIOUS),
    "form-label-missing":           ("1.3.1, 3.3.2","E207.2", Severity.CRITICAL),
    "heading-order-skipped":        ("1.3.1",       "E205.4", Severity.MODERATE),
    "link-text-generic":            ("2.4.4",       "E205.4", Severity.MODERATE),
    "document-language-missing":    ("3.1.1",       "E205.4", Severity.SERIOUS),
    "pdf-untagged":                 ("1.3.1",       "E205.4", Severity.CRITICAL),
    "pdf-no-title":                 ("2.4.2",       "E205.4", Severity.MODERATE),
    "table-header-missing":         ("1.3.1",       "E205.4", Severity.SERIOUS),
    "slide-title-missing":          ("2.4.6",       "E205.4", Severity.SERIOUS),
    "keyboard-trap":                ("2.1.2",       "E207.2", Severity.CRITICAL),
    "aria-label-invalid":           ("4.1.2",       "E207.2", Severity.SERIOUS),
    # Web
    "page-title-missing":           ("2.4.2",       "E205.4", Severity.SERIOUS),
    "landmark-missing":             ("1.3.1",       "E205.4", Severity.MODERATE),
    "skip-link-missing":            ("2.4.1",       "E205.4", Severity.MODERATE),
    "focus-visible-missing":        ("2.4.7",       "E207.2", Severity.SERIOUS),
    "language-of-page-missing":     ("3.1.1",       "E205.4", Severity.SERIOUS),
    # PDF
    "pdf-no-lang":                  ("3.1.1",       "E205.4", Severity.SERIOUS),
    "pdf-no-mark-info":             ("1.3.1",       "E205.4", Severity.SERIOUS),
    "pdf-figure-no-alt":            ("1.1.1",       "E205.4", Severity.SERIOUS),
    "pdf-form-field-no-name":       ("1.3.1, 3.3.2","E207.2", Severity.CRITICAL),
    # DOCX
    "docx-image-alt-missing":       ("1.1.1",       "E205.4", Severity.SERIOUS),
    "docx-no-heading":              ("1.3.1",       "E205.4", Severity.MODERATE),
    "docx-heading-skipped":         ("1.3.1",       "E205.4", Severity.MODERATE),
    "docx-fake-heading":            ("1.3.1",       "E205.4", Severity.MODERATE),
    "docx-table-no-header":         ("1.3.1",       "E205.4", Severity.SERIOUS),
    "docx-link-text-generic":       ("2.4.4",       "E205.4", Severity.MODERATE),
    "docx-no-language":             ("3.1.1",       "E205.4", Severity.SERIOUS),
    "docx-fake-list":               ("1.3.1",       "E205.4", Severity.MINOR),
    # PPTX
    "pptx-slide-title-missing":     ("2.4.6",       "E205.4", Severity.SERIOUS),
    "pptx-slide-title-duplicate":   ("2.4.6",       "E205.4", Severity.MINOR),
    "pptx-shape-alt-missing":       ("1.1.1",       "E205.4", Severity.SERIOUS),
    "pptx-reading-order":           ("1.3.2",       "E205.4", Severity.MODERATE),
    "pptx-color-contrast":          ("1.4.3",       "E207.2", Severity.SERIOUS),
    # XLSX
    "xlsx-no-title":                ("2.4.2",       "E205.4", Severity.MODERATE),
    "xlsx-default-sheet-name":      ("2.4.6",       "E205.4", Severity.MINOR),
    "xlsx-no-table-structure":      ("1.3.1",       "E205.4", Severity.MODERATE),
    "xlsx-merged-cells":            ("1.3.1",       "E205.4", Severity.MODERATE),
    "xlsx-image-alt-missing":       ("1.1.1",       "E205.4", Severity.SERIOUS),
    # Image
    "standalone-image-alt-missing": ("1.1.1",       "E205.4", Severity.CRITICAL),
    "standalone-image-alt-poor":    ("1.1.1",       "E205.4", Severity.SERIOUS),
}

_FALLBACK = ("Unknown", "Unknown", Severity.MODERATE)


def get_refs(rule_id: str) -> Tuple[str, str, Severity]:
    return _REFS.get(rule_id, _FALLBACK)
