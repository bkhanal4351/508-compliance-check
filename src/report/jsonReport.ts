import fs from "fs-extra";
import path from "node:path";
import type { ScanResult } from "../models/ScanResult.js";

export async function writeJsonReports(outDir: string, result: ScanResult): Promise<void> {
  await fs.writeJson(path.join(outDir, "report.json"), result, { spaces: 2 });
  await fs.writeJson(path.join(outDir, "summary.json"), createSummary(result), { spaces: 2 });
}

export function createSummary(result: ScanResult): Record<string, unknown> {
  const byImpact = countBy(result.findings, (finding) => finding.impact);
  const byAssetType = countBy(result.findings, (finding) => finding.assetType);
  return {
    scanId: result.scanId,
    target: result.target,
    startedAt: result.startedAt,
    finishedAt: result.finishedAt,
    pagesCrawled: result.assets.filter((asset) => asset.type === "web_page").length,
    documentsScanned: result.assets.filter((asset) => asset.type !== "web_page").length,
    totalFindings: result.findings.length,
    automatedIssues: result.findings.filter((finding) => finding.confidence === "automated").length,
    manualReviewItems: result.findings.filter((finding) => finding.confidence === "manual_required").length,
    findingsByImpact: byImpact,
    findingsByAssetType: byAssetType,
    skippedItems: result.skippedItems.length,
    crawlErrors: result.crawlErrors.length
  };
}

function countBy<T>(values: T[], getKey: (value: T) => string): Record<string, number> {
  return values.reduce<Record<string, number>>((counts, value) => {
    const key = getKey(value);
    counts[key] = (counts[key] || 0) + 1;
    return counts;
  }, {});
}
