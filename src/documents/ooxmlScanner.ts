import fs from "fs-extra";
import JSZip from "jszip";
import path from "node:path";
import type { DocumentAsset } from "../models/Asset.js";
import type { AssetType, Finding } from "../models/Finding.js";
import { SECTION_508_RELATED } from "../models/Finding.js";
import { shortHash } from "../utils/hashing.js";

export async function scanOoxml(filePath: string, scanId: string, assetType: "docx" | "pptx" | "xlsx"): Promise<{ asset: DocumentAsset; findings: Finding[] }> {
  const stat = await fs.stat(filePath);
  const findings: Finding[] = [];
  try {
    const zip = await JSZip.loadAsync(await fs.readFile(filePath));
    if (assetType === "docx") await scanDocx(zip, filePath, scanId, findings);
    if (assetType === "pptx") await scanPptx(zip, filePath, scanId, findings);
    if (assetType === "xlsx") await scanXlsx(zip, filePath, scanId, findings);
  } catch (error) {
    findings.push(ooxmlFinding(scanId, filePath, assetType, "ooxml.invalid", "Could not inspect document package", `The file could not be opened as an OOXML package: ${String(error)}`, "needs_review", "manual_required"));
  }
  return { asset: { type: assetType, path: filePath, sizeBytes: stat.size }, findings };
}

async function scanDocx(zip: JSZip, filePath: string, scanId: string, findings: Finding[]): Promise<void> {
  const core = await readZipText(zip, "docProps/core.xml");
  const documentXml = await readZipText(zip, "word/document.xml");
  const drawingXml = await readAllMatching(zip, /^word\/(document|header\d+|footer\d+)\.xml$/);
  if (!/<dc:title>[^<]+<\/dc:title>/.test(core)) {
    findings.push(ooxmlFinding(scanId, filePath, "docx", "docx.title", "Missing core document title metadata", "The DOCX package does not appear to include title metadata.", "moderate", "semi_automated"));
  }
  if (/<(w:drawing|w:pict)\b/.test(documentXml) && !/(descr|title)="[^"]+"/.test(drawingXml)) {
    findings.push(ooxmlFinding(scanId, filePath, "docx", "docx.image-alt", "Images may lack alternative text", "Drawings or images were found without obvious title or description metadata.", "needs_review", "manual_required"));
  }
  if (/<w:tbl\b/.test(documentXml)) findings.push(ooxmlFinding(scanId, filePath, "docx", "docx.tables", "Tables require manual accessibility review", "Validate header rows, reading order, and table purpose.", "needs_review", "manual_required"));
  if (/<w:hyperlink\b/.test(documentXml)) findings.push(ooxmlFinding(scanId, filePath, "docx", "docx.links", "Hyperlinks require meaningful text review", "Validate link text in context.", "needs_review", "manual_required"));
  findings.push(ooxmlFinding(scanId, filePath, "docx", "docx.headings", "Heading and style structure review", "Validate heading levels and document structure.", "needs_review", "manual_required"));
  findings.push(ooxmlFinding(scanId, filePath, "docx", "docx.language", "Document language review", "Validate document language and language changes.", "needs_review", "manual_required"));
}

async function scanPptx(zip: JSZip, filePath: string, scanId: string, findings: Finding[]): Promise<void> {
  const slideFiles = Object.keys(zip.files).filter((name) => /^ppt\/slides\/slide\d+\.xml$/.test(name)).sort();
  const titles: string[] = [];
  for (const slide of slideFiles) {
    const xml = await readZipText(zip, slide);
    const titleMatches = Array.from(xml.matchAll(/<a:t>([^<]+)<\/a:t>/g)).map((match) => match[1].trim()).filter(Boolean);
    const title = titleMatches[0] || "";
    titles.push(title);
    if (!title) findings.push(ooxmlFinding(scanId, filePath, "pptx", "pptx.slide-title", `Slide may be missing a title: ${path.basename(slide)}`, "A clear slide title was not detected.", "needs_review", "manual_required"));
    if (/<p:pic\b/.test(xml) && !/(descr|title)="[^"]+"/.test(xml)) {
      findings.push(ooxmlFinding(scanId, filePath, "pptx", "pptx.image-alt", `Images may lack alt text: ${path.basename(slide)}`, "Images were found without obvious title or description metadata.", "needs_review", "manual_required"));
    }
    if (/<a:tbl\b/.test(xml)) findings.push(ooxmlFinding(scanId, filePath, "pptx", "pptx.tables", `Tables require review: ${path.basename(slide)}`, "Validate table headers and reading order.", "needs_review", "manual_required"));
    if (/<p:audio|<p:video|<a:videoFile|<a:audioFile/.test(xml)) findings.push(ooxmlFinding(scanId, filePath, "pptx", "pptx.media", `Media requires captions review: ${path.basename(slide)}`, "Validate captions, transcripts, and audio descriptions.", "needs_review", "manual_required"));
  }
  const duplicates = titles.filter((title, index) => title && titles.indexOf(title) !== index);
  if (duplicates.length) findings.push(ooxmlFinding(scanId, filePath, "pptx", "pptx.duplicate-title", "Duplicate slide titles detected", "Duplicate slide titles can make navigation harder.", "needs_review", "manual_required"));
  findings.push(ooxmlFinding(scanId, filePath, "pptx", "pptx.reading-order", "Reading order requires manual review", "Validate slide object reading order.", "needs_review", "manual_required"));
}

async function scanXlsx(zip: JSZip, filePath: string, scanId: string, findings: Finding[]): Promise<void> {
  const workbook = await readZipText(zip, "xl/workbook.xml");
  const sheetNames = Array.from(workbook.matchAll(/name="([^"]*)"/g)).map((match) => match[1]);
  sheetNames.forEach((name) => {
    if (!name || /^sheet\d+$/i.test(name)) {
      findings.push(ooxmlFinding(scanId, filePath, "xlsx", "xlsx.generic-sheet-name", "Worksheet name may be blank or generic", `Worksheet name "${name}" should be meaningful.`, "needs_review", "manual_required"));
    }
  });
  const worksheetXml = await readAllMatching(zip, /^xl\/worksheets\/sheet\d+\.xml$/);
  if (/<mergeCell\b/.test(worksheetXml)) findings.push(ooxmlFinding(scanId, filePath, "xlsx", "xlsx.merged-cells", "Merged cells detected", "Merged cells can complicate navigation and should be reviewed.", "needs_review", "manual_required"));
  if (Object.keys(zip.files).some((name) => /^xl\/drawings\//.test(name))) findings.push(ooxmlFinding(scanId, filePath, "xlsx", "xlsx.drawings", "Drawings, charts, or images require alt text review", "Validate chart titles, image alt text, and object names.", "needs_review", "manual_required"));
  findings.push(ooxmlFinding(scanId, filePath, "xlsx", "xlsx.tables", "Tables and headers require manual review", "Validate headers, table structure, and frozen panes where useful.", "needs_review", "manual_required"));
  findings.push(ooxmlFinding(scanId, filePath, "xlsx", "xlsx.color-only", "Color-only meaning requires manual review", "Validate that color is not the only way information is conveyed.", "needs_review", "manual_required"));
  findings.push(ooxmlFinding(scanId, filePath, "xlsx", "xlsx.navigation", "Workbook navigation complexity requires review", "Validate sheet order, names, and navigation complexity.", "needs_review", "manual_required"));
}

async function readZipText(zip: JSZip, name: string): Promise<string> {
  return (await zip.file(name)?.async("text")) || "";
}

async function readAllMatching(zip: JSZip, pattern: RegExp): Promise<string> {
  const chunks = await Promise.all(Object.keys(zip.files).filter((name) => pattern.test(name)).map((name) => readZipText(zip, name)));
  return chunks.join("\n");
}

function ooxmlFinding(
  scanId: string,
  filePath: string,
  assetType: AssetType,
  ruleId: string,
  title: string,
  description: string,
  impact: "moderate" | "needs_review",
  confidence: "semi_automated" | "manual_required"
): Finding {
  return {
    id: shortHash(`${scanId}:${filePath}:${ruleId}:${title}`),
    scanId,
    assetType,
    assetPathOrUrl: filePath,
    ruleId,
    title,
    description,
    impact,
    confidence,
    wcagCriteria: [],
    section508Reference: SECTION_508_RELATED,
    recommendation: description
  };
}
