import fs from "fs-extra";
import path from "node:path";
import type { DocumentAsset } from "../models/Asset.js";
import type { Finding } from "../models/Finding.js";
import { SECTION_508_RELATED } from "../models/Finding.js";
import { shortHash } from "../utils/hashing.js";
import { runVeraPdfIfAvailable } from "./verapdf.js";

export async function scanPdf(filePath: string, scanId: string, outDir: string, timeoutMs: number): Promise<{ asset: DocumentAsset; findings: Finding[] }> {
  const findings: Finding[] = [];
  const stat = await fs.stat(filePath);
  const buffer = await fs.readFile(filePath);
  const header = buffer.subarray(0, 8).toString("latin1");
  const textSample = buffer.toString("latin1", 0, Math.min(buffer.length, 250000));
  const hasPdfHeader = header.startsWith("%PDF-");
  const probableText = /BT\s|\/ToUnicode|[\w ]{80,}/.test(textSample);

  if (!hasPdfHeader) {
    findings.push(pdfFinding(scanId, filePath, "pdf.header", "PDF header missing or invalid", "The file does not start with a standard PDF header.", "automated"));
  }
  if (!probableText) {
    findings.push(pdfFinding(scanId, filePath, "pdf.probable-scanned", "Probable scanned or image-only PDF", "No obvious text layer was detected in the PDF sample.", "semi_automated"));
  }

  const vera = await runVeraPdfIfAvailable(filePath, outDir, timeoutMs);
  let rawResultPath: string | undefined;
  if (vera.available) {
    rawResultPath = vera.rawPath;
    if (vera.exitCode !== 0 || /failed|non-compliant|error/i.test(vera.output)) {
      findings.push(pdfFinding(scanId, filePath, "pdf.verapdf", "veraPDF reported PDF validation issues", "Review the saved veraPDF output for PDF/UA or PDF/A validation details.", "semi_automated", rawResultPath));
    }
  } else {
    findings.push(pdfFinding(scanId, filePath, "pdf.verapdf-unavailable", "Manual PDF/UA or tagged PDF validation recommended", "veraPDF was not available locally, so full PDF tagging validation was not performed.", "manual_required"));
  }

  for (const [ruleId, title] of [
    ["pdf.reading-order", "Logical reading order"],
    ["pdf.alt-text", "Meaningful alt text"],
    ["pdf.table-headers", "Table headers"],
    ["pdf.form-labels", "Form labels"],
    ["pdf.title", "Document title"],
    ["pdf.language", "Document language"],
    ["pdf.color-contrast", "Color contrast"]
  ]) {
    findings.push(pdfFinding(scanId, filePath, ruleId, title, `Manually validate ${title.toLowerCase()} in the PDF.`, "manual_required"));
  }

  return { asset: { type: "pdf", path: filePath, sizeBytes: stat.size, rawResultPath }, findings };
}

function pdfFinding(
  scanId: string,
  filePath: string,
  ruleId: string,
  title: string,
  description: string,
  confidence: "automated" | "semi_automated" | "manual_required",
  rawPath?: string
): Finding {
  return {
    id: shortHash(`${scanId}:${filePath}:${ruleId}`),
    scanId,
    assetType: "pdf",
    assetPathOrUrl: filePath,
    ruleId,
    title,
    description,
    impact: confidence === "automated" ? "moderate" : "needs_review",
    confidence,
    wcagCriteria: [],
    section508Reference: SECTION_508_RELATED,
    location: rawPath,
    recommendation: description
  };
}
