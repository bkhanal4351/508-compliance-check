import { describe, expect, it } from "vitest";
import { isDocumentUrl, normalizeUrl } from "../src/crawl/url.js";

describe("normalizeUrl", () => {
  it("removes fragments and normalizes trailing slashes", () => {
    expect(normalizeUrl("HTTPS://Example.com/a/#section")).toBe("https://example.com/a");
  });

  it("ignores unsupported protocols", () => {
    expect(normalizeUrl("mailto:test@example.com")).toBeNull();
    expect(normalizeUrl("javascript:alert(1)")).toBeNull();
  });

  it("detects document URLs", () => {
    expect(isDocumentUrl("https://example.com/report.PDF")).toBe(true);
    expect(isDocumentUrl("https://example.com/page")).toBe(false);
  });
});
