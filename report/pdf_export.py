import logging
from pathlib import Path
from typing import List

from jinja2 import Environment, FileSystemLoader
from weasyprint import HTML

from scanners.base import Finding

logger = logging.getLogger(__name__)

_TEMPLATE_DIR = Path(__file__).parent / "templates"


def export_pdf(report: dict, output_path: str) -> str:
    env = Environment(loader=FileSystemLoader(str(_TEMPLATE_DIR)), autoescape=True)
    template = env.get_template("report.html")

    # Convert Finding objects to plain dicts for Jinja
    findings_dicts = [f.model_dump() for f in report.get("findings", [])]
    for fd in findings_dicts:
        fd["severity"] = fd["severity"].value if hasattr(fd["severity"], "value") else fd["severity"]

    html_str = template.render(
        scan_target=report.get("scan_target", ""),
        scan_type=report.get("scan_type", ""),
        scanned_at=report.get("scanned_at", ""),
        summary=report.get("summary", {}),
        findings=findings_dicts,
        deduped_count=report.get("deduped_count", 0),
    )

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    HTML(string=html_str, base_url=str(_TEMPLATE_DIR)).write_pdf(str(output))
    logger.info("PDF report written to %s", output)
    return str(output)


def export_csv(report: dict) -> str:
    """Return CSV string of findings."""
    import csv
    import io

    fields = ["id", "severity", "rule", "wcag_sc", "sec508_ref", "title", "location", "source", "suggested_fix"]
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for f in report.get("findings", []):
        row = f.model_dump() if hasattr(f, "model_dump") else f
        row["severity"] = row["severity"].value if hasattr(row["severity"], "value") else row["severity"]
        writer.writerow({k: row.get(k, "") for k in fields})
    return buf.getvalue()
