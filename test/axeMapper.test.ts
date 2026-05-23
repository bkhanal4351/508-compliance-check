import { describe, expect, it } from "vitest";
import type { AxeResults } from "axe-core";
import { extractWcagCriteria, mapAxeViolations } from "../src/web/axeMapper.js";

describe("axeMapper", () => {
  it("extracts WCAG criteria from axe tags", () => {
    expect(extractWcagCriteria(["wcag111", "wcag2a", "best-practice"])).toEqual(["1.1.1"]);
  });

  it("maps violations to findings", () => {
    const results = {
      violations: [
        {
          id: "image-alt",
          impact: "critical",
          tags: ["wcag111", "wcag2a"],
          description: "Images must have alternate text",
          help: "Images must have alternate text",
          helpUrl: "https://dequeuniversity.com/rules/axe/4.10/image-alt",
          nodes: [{ target: ["img"], html: "<img>", failureSummary: "Fix alt text" }]
        }
      ],
      incomplete: [],
      passes: []
    } as unknown as AxeResults;
    const findings = mapAxeViolations("scan", "https://example.com", results);
    expect(findings[0]).toMatchObject({
      assetType: "web_page",
      ruleId: "image-alt",
      impact: "critical",
      confidence: "automated",
      wcagCriteria: ["1.1.1"]
    });
  });
});
