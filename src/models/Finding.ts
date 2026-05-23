export type AssetType =
  | "web_page"
  | "pdf"
  | "docx"
  | "pptx"
  | "xlsx"
  | "legacy_document"
  | "unknown_document";

export type FindingImpact =
  | "critical"
  | "serious"
  | "moderate"
  | "minor"
  | "needs_review"
  | "unknown";

export type FindingConfidence = "automated" | "semi_automated" | "manual_required";

export type Finding = {
  id: string;
  scanId: string;
  assetType: AssetType;
  assetPathOrUrl: string;
  ruleId: string;
  title: string;
  description: string;
  impact: FindingImpact;
  confidence: FindingConfidence;
  wcagCriteria: string[];
  section508Reference: string;
  helpUrl?: string;
  selector?: string;
  htmlSnippet?: string;
  location?: string;
  recommendation: string;
  raw?: unknown;
};

export const SECTION_508_RELATED =
  "Section 508 Revised Standards E205.4 / WCAG A-AA related requirement";
