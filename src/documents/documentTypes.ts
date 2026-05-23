import path from "node:path";
import type { AssetType } from "../models/Finding.js";

const LEGACY_EXTENSIONS = new Set([".doc", ".ppt", ".xls", ".rtf", ".odt", ".ods", ".odp", ".csv"]);

export function documentTypeForPath(filePath: string): AssetType {
  const extension = path.extname(filePath).toLowerCase();
  if (extension === ".pdf") return "pdf";
  if (extension === ".docx") return "docx";
  if (extension === ".pptx") return "pptx";
  if (extension === ".xlsx") return "xlsx";
  if (LEGACY_EXTENSIONS.has(extension)) return "legacy_document";
  return "unknown_document";
}

export function isSupportedDocumentPath(filePath: string): boolean {
  return documentTypeForPath(filePath) !== "unknown_document";
}
