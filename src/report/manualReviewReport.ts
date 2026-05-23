import fs from "fs-extra";
import path from "node:path";
import type { Finding } from "../models/Finding.js";

export async function writeManualReviewReport(outDir: string, findings: Finding[]): Promise<void> {
  const manual = findings.filter((finding) => finding.confidence === "manual_required");
  const grouped = groupBy(manual, (finding) => finding.assetPathOrUrl);
  const lines = [
    "# Manual Review Checklist",
    "",
    "This checklist contains items that automated tools cannot fully validate. Review keyboard access, screen reader order, reading order, meaningful alt text, captions/transcripts, form errors, document structure, table headers, language, and color contrast where applicable.",
    ""
  ];
  for (const [asset, assetFindings] of Object.entries(grouped)) {
    lines.push(`## ${asset}`, "");
    for (const finding of assetFindings) {
      lines.push(`- [ ] **${finding.title}** (${finding.ruleId})`);
      lines.push(`  ${finding.recommendation}`);
    }
    lines.push("");
  }
  await fs.writeFile(path.join(outDir, "manual-review.md"), `${lines.join("\n")}\n`);
}

function groupBy<T>(values: T[], getKey: (value: T) => string): Record<string, T[]> {
  return values.reduce<Record<string, T[]>>((groups, value) => {
    const key = getKey(value);
    groups[key] ||= [];
    groups[key].push(value);
    return groups;
  }, {});
}
