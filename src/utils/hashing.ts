import crypto from "node:crypto";

export function shortHash(value: string): string {
  return crypto.createHash("sha256").update(value).digest("hex").slice(0, 12);
}

export function createScanId(): string {
  return `scan-${new Date().toISOString().replace(/[:.]/g, "-")}-${shortHash(String(Math.random()))}`;
}
