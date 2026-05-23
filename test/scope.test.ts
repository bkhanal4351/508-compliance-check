import { describe, expect, it } from "vitest";
import { isInScope } from "../src/crawl/scope.js";

describe("isInScope", () => {
  it("enforces same-origin scope", () => {
    expect(isInScope("https://example.com/a", "https://example.com/start", { sameOrigin: true, sameHost: true })).toBe(true);
    expect(isInScope("http://example.com/a", "https://example.com/start", { sameOrigin: true, sameHost: true })).toBe(false);
  });

  it("can allow same-host across origins", () => {
    expect(isInScope("http://example.com/a", "https://example.com/start", { sameOrigin: false, sameHost: true })).toBe(true);
  });
});
