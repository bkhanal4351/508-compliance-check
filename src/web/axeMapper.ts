import type { AxeResults, Result } from "axe-core";
import type { AssetType, Finding, FindingImpact } from "../models/Finding.js";
import { SECTION_508_RELATED } from "../models/Finding.js";
import { shortHash } from "../utils/hashing.js";

const WCAG_TAG_PATTERN = /^wcag(\d)(\d)(\d)$/;

export function axeImpactToFindingImpact(impact?: string | null): FindingImpact {
  if (impact === "critical" || impact === "serious" || impact === "moderate" || impact === "minor") return impact;
  return "unknown";
}

export function extractWcagCriteria(tags: string[]): string[] {
  return tags
    .map((tag) => {
      const match = tag.match(WCAG_TAG_PATTERN);
      return match ? `${match[1]}.${match[2]}.${match[3]}` : null;
    })
    .filter((value): value is string => Boolean(value));
}

export function mapAxeViolations(scanId: string, assetUrl: string, results: AxeResults, assetType: AssetType = "web_page"): Finding[] {
  return results.violations.flatMap((violation) => mapAxeResult(scanId, assetUrl, violation, "automated", assetType));
}

export function mapAxeIncomplete(scanId: string, assetUrl: string, results: AxeResults, assetType: AssetType = "web_page"): Finding[] {
  return results.incomplete.flatMap((incomplete) => mapAxeResult(scanId, assetUrl, incomplete, "manual_required", assetType));
}

function mapAxeResult(
  scanId: string,
  assetUrl: string,
  result: Result,
  confidence: "automated" | "manual_required",
  assetType: AssetType
): Finding[] {
  const nodes = result.nodes.length ? result.nodes : [undefined];
  return nodes.map((node, index) => ({
    id: shortHash(`${scanId}:${assetUrl}:${result.id}:${confidence}:${index}:${node?.target.join(",") ?? ""}`),
    scanId,
    assetType,
    assetPathOrUrl: assetUrl,
    ruleId: result.id,
    title: confidence === "manual_required" ? `Needs review: ${result.help}` : result.help,
    description: result.description,
    impact: confidence === "manual_required" ? "needs_review" : axeImpactToFindingImpact(result.impact),
    confidence,
    wcagCriteria: extractWcagCriteria(result.tags),
    section508Reference: SECTION_508_RELATED,
    helpUrl: result.helpUrl,
    selector: node?.target.join(", "),
    htmlSnippet: node?.html,
    recommendation: node?.failureSummary || result.help,
    raw: { resultId: result.id, tags: result.tags, node }
  }));
}
