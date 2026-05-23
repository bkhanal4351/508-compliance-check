import { XMLParser } from "fast-xml-parser";
import { isInScope, type ScopeOptions } from "./scope.js";
import { normalizeUrl } from "./url.js";

export async function discoverSitemapUrls(startUrl: string, scopeOptions: ScopeOptions, timeoutMs: number): Promise<string[]> {
  const origin = new URL(startUrl).origin;
  const sitemapUrl = `${origin}/sitemap.xml`;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(sitemapUrl, { signal: controller.signal });
    if (!response.ok) return [];
    const xml = await response.text();
    const parser = new XMLParser({ ignoreAttributes: false });
    const parsed = parser.parse(xml);
    const urls = collectLocValues(parsed)
      .map((value) => normalizeUrl(value))
      .filter((value): value is string => Boolean(value))
      .filter((value) => isInScope(value, startUrl, scopeOptions));
    return Array.from(new Set(urls));
  } catch {
    return [];
  } finally {
    clearTimeout(timer);
  }
}

function collectLocValues(value: unknown): string[] {
  if (!value || typeof value !== "object") return [];
  if (Array.isArray(value)) return value.flatMap(collectLocValues);
  const object = value as Record<string, unknown>;
  const own = typeof object.loc === "string" ? [object.loc] : [];
  return own.concat(Object.values(object).flatMap(collectLocValues));
}
