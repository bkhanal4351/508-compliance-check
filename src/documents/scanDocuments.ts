import fs from "fs-extra";
import type { Asset } from "../models/Asset.js";
import type { AssetType, Finding } from "../models/Finding.js";
import { SECTION_508_RELATED } from "../models/Finding.js";
import { shortHash } from "../utils/hashing.js";
import type { Logger } from "../utils/logger.js";
import { documentTypeForPath } from "./documentTypes.js";
import { scanOoxml } from "./ooxmlScanner.js";
import { scanPdf } from "./pdfScanner.js";

export async function scanDocuments(filePaths: string[], scanId: string, outDir: string, timeoutMs: number, logger: Logger): Promise<{ assets: Asset[]; findings: Finding[]; errors: { url: string; message: string }[] }> {
  const assets: Asset[] = [];
  const findings: Finding[] = [];
  const errors: { url: string; message: string }[] = [];

  for (const filePath of filePaths) {
    try {
      logger.info(`Scanning document: ${filePath}`);
      if (!(await fs.pathExists(filePath))) {
        errors.push({ url: filePath, message: "File does not exist" });
        continue;
      }
      const type = documentTypeForPath(filePath);
      if (type === "pdf") {
        const result = await scanPdf(filePath, scanId, outDir, timeoutMs);
        assets.push(result.asset);
        findings.push(...result.findings);
      } else if (type === "docx" || type === "pptx" || type === "xlsx") {
        const result = await scanOoxml(filePath, scanId, type);
        assets.push(result.asset);
        findings.push(...result.findings);
      } else {
        const stat = await fs.stat(filePath);
        const documentType = type as Exclude<AssetType, "web_page">;
        assets.push({ type: documentType, path: filePath, sizeBytes: stat.size });
        findings.push(manualUnsupportedFinding(scanId, filePath, documentType));
      }
    } catch (error) {
      errors.push({ url: filePath, message: String(error) });
    }
  }

  return { assets, findings, errors };
}

function manualUnsupportedFinding(scanId: string, filePath: string, assetType: Exclude<AssetType, "web_page">): Finding {
  return {
    id: shortHash(`${scanId}:${filePath}:unsupported-document`),
    scanId,
    assetType,
    assetPathOrUrl: filePath,
    ruleId: "document.manual-review-required",
    title: "Manual document accessibility review required",
    description: "This file type is not fully supported by the local automated checker.",
    impact: "needs_review",
    confidence: "manual_required",
    wcagCriteria: [],
    section508Reference: SECTION_508_RELATED,
    recommendation: "Review document structure, reading order, text alternatives, language, headings, tables, and color contrast manually."
  };
}
