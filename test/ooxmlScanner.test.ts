import { describe, expect, it } from "vitest";
import path from "node:path";
import { scanOoxml } from "../src/documents/ooxmlScanner.js";

describe("scanOoxml", () => {
  it("does not crash on invalid files", async () => {
    const filePath = path.resolve("samples/sample.docx");
    const result = await scanOoxml(filePath, "scan", "docx");
    expect(result.findings.some((finding) => finding.ruleId === "ooxml.invalid")).toBe(true);
  });
});
