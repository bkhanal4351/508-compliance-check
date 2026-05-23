import { describe, expect, it } from "vitest";
import { escapeCsv } from "../src/report/csvReport.js";

describe("escapeCsv", () => {
  it("escapes commas, quotes, and newlines", () => {
    expect(escapeCsv('a,"b"\nc')).toBe('"a,""b""\nc"');
  });
});
