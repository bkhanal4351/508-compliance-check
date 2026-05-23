import fs from "fs-extra";
import path from "node:path";
import type { Finding } from "../models/Finding.js";

const COLUMNS = [
  "assetType",
  "assetPathOrUrl",
  "impact",
  "confidence",
  "ruleId",
  "title",
  "description",
  "wcagCriteria",
  "section508Reference",
  "selector",
  "location",
  "recommendation"
] as const;

export function escapeCsv(value: unknown): string {
  const stringValue = Array.isArray(value) ? value.join("; ") : String(value ?? "");
  if (/[",\n\r]/.test(stringValue)) {
    return `"${stringValue.replace(/"/g, '""')}"`;
  }
  return stringValue;
}

export function findingsToCsv(findings: Finding[]): string {
  const rows = [
    COLUMNS.join(","),
    ...findings.map((finding) => COLUMNS.map((column) => escapeCsv(finding[column])).join(","))
  ];
  return `${rows.join("\n")}\n`;
}

export async function writeCsvReport(outDir: string, findings: Finding[]): Promise<void> {
  await fs.writeFile(path.join(outDir, "findings.csv"), findingsToCsv(findings));
}
