import { describe, expect, it } from "vitest";
import { isPrivateOrLocalIp } from "../src/crawl/safety.js";

describe("isPrivateOrLocalIp", () => {
  it("blocks private and local IPv4 ranges", () => {
    expect(isPrivateOrLocalIp("127.0.0.1")).toBe(true);
    expect(isPrivateOrLocalIp("10.1.2.3")).toBe(true);
    expect(isPrivateOrLocalIp("172.16.0.1")).toBe(true);
    expect(isPrivateOrLocalIp("192.168.1.1")).toBe(true);
    expect(isPrivateOrLocalIp("169.254.169.254")).toBe(true);
  });

  it("allows public IPv4 addresses", () => {
    expect(isPrivateOrLocalIp("93.184.216.34")).toBe(false);
  });
});
