from datetime import datetime, timezone
from typing import List

from scanners.base import Finding, Severity


def build_report(findings: List[Finding], scan_target: str, scan_type: str) -> dict:
    # Deduplicate: collapse same rule + location across repeated elements
    seen: dict[str, Finding] = {}
    dupes = 0
    for f in findings:
        key = f"{f.rule}|{f.location}"
        if key in seen:
            dupes += 1
        else:
            seen[key] = f

    deduped = list(seen.values())

    # Sort: severity order, then location alpha
    _order = {Severity.CRITICAL: 0, Severity.SERIOUS: 1, Severity.MODERATE: 2, Severity.MINOR: 3}
    deduped.sort(key=lambda f: (_order[f.severity], f.location))

    summary = {
        "Critical": sum(1 for f in deduped if f.severity == Severity.CRITICAL),
        "Serious":  sum(1 for f in deduped if f.severity == Severity.SERIOUS),
        "Moderate": sum(1 for f in deduped if f.severity == Severity.MODERATE),
        "Minor":    sum(1 for f in deduped if f.severity == Severity.MINOR),
        "total":    len(deduped),
    }

    return {
        "scan_target": scan_target,
        "scan_type": scan_type,
        "scanned_at": datetime.now(timezone.utc).isoformat(),
        "summary": summary,
        "findings": deduped,
        "deduped_count": dupes,
    }
