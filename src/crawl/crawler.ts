import { chromium, type Browser } from "playwright";
import fs from "fs-extra";
import path from "node:path";
import pLimit from "p-limit";
import type { Asset } from "../models/Asset.js";
import type { Finding } from "../models/Finding.js";
import type { CrawlMetadata, ScanSettings } from "../models/ScanResult.js";
import type { Logger } from "../utils/logger.js";
import { scanPage } from "../web/scanPage.js";
import { assertUrlIsSafe } from "./safety.js";
import { discoverSitemapUrls } from "./sitemap.js";
import { isInScope } from "./scope.js";
import { filenameFromUrl, isDocumentUrl, normalizeUrl, sanitizeFilename } from "./url.js";
import { shortHash } from "../utils/hashing.js";

export type CrawlResult = {
  assets: Asset[];
  findings: Finding[];
  metadata: CrawlMetadata;
};

type QueueItem = { url: string; depth: number };

export async function crawlAndScan(startUrl: string, scanId: string, settings: ScanSettings, logger: Logger): Promise<CrawlResult> {
  const browser = await chromium.launch();
  const metadata: CrawlMetadata = {
    startedAt: new Date().toISOString(),
    startUrl,
    pagesVisited: [],
    documentsFound: [],
    downloadedFiles: [],
    errors: [],
    skipped: []
  };
  const assets: Asset[] = [];
  const findings: Finding[] = [];
  const visited = new Set<string>();
  const queued = new Set<string>();
  const queue: QueueItem[] = [];

  const normalizedStart = normalizeUrl(startUrl);
  if (!normalizedStart) throw new Error(`Invalid start URL: ${startUrl}`);
  const crawlRoot = normalizedStart;
  queue.push({ url: crawlRoot, depth: 0 });
  queued.add(crawlRoot);

  const sitemapUrls = await discoverSitemapUrls(crawlRoot, settings, Math.min(settings.timeoutMs, 15000));
  for (const url of sitemapUrls.slice(0, settings.maxPages)) {
    if (!queued.has(url)) {
      queue.push({ url, depth: 1 });
      queued.add(url);
    }
  }

  try {
    while (queue.length > 0 && visited.size < settings.maxPages) {
      const remainingPageBudget = Math.max(0, settings.maxPages - visited.size);
      const batch = queue.splice(0, Math.min(Math.max(1, settings.concurrency), remainingPageBudget));
      const limit = pLimit(settings.concurrency);
      await Promise.all(batch.map((item) => limit(() => visitPage(browser, item))));
    }
  } finally {
    await browser.close();
    metadata.finishedAt = new Date().toISOString();
    await fs.writeJson(path.join(settings.outDir, "crawl-metadata.json"), metadata, { spaces: 2 });
  }

  return { assets, findings, metadata };

  async function visitPage(browserInstance: Browser, item: QueueItem): Promise<void> {
    if (visited.has(item.url) || visited.size >= settings.maxPages || item.depth > settings.maxDepth) return;
    if (!isInScope(item.url, crawlRoot, settings)) {
      metadata.skipped.push({ target: item.url, reason: "URL outside configured crawl scope" });
      return;
    }

    // SSRF protection: crawled pages can link to internal services even in a local CLI, so resolve before requesting.
    const safety = await assertUrlIsSafe(item.url);
    if (!safety.safe) {
      metadata.skipped.push({ target: item.url, reason: safety.reason });
      return;
    }

    visited.add(item.url);
    logger.info(`Scanning page ${visited.size}/${settings.maxPages}: ${item.url}`);
    try {
      const pageResult = await scanPage(
        browserInstance,
        item.url,
        scanId,
        settings.outDir,
        settings.includeScreenshots,
        settings.timeoutMs,
        item.depth
      );
      assets.push(pageResult.asset);
      findings.push(...pageResult.findings);
      metadata.pagesVisited.push(item.url);

      for (const rawLink of pageResult.links) {
        const link = normalizeUrl(rawLink, item.url);
        if (!link) continue;
        if (isDocumentUrl(link)) {
          await recordDocument(link);
          continue;
        }
        if (item.depth + 1 <= settings.maxDepth && !queued.has(link) && !visited.has(link) && isInScope(link, crawlRoot, settings)) {
          queued.add(link);
          queue.push({ url: link, depth: item.depth + 1 });
        }
      }
    } catch (error) {
      metadata.errors.push({ url: item.url, depth: item.depth, message: String(error) });
      logger.warn(`Failed page scan: ${item.url}`);
    }
  }

  async function recordDocument(documentUrl: string): Promise<void> {
    if (!metadata.documentsFound.includes(documentUrl)) metadata.documentsFound.push(documentUrl);
    if (!settings.downloadDocuments) return;
    const safety = await assertUrlIsSafe(documentUrl);
    if (!safety.safe) {
      metadata.skipped.push({ target: documentUrl, reason: safety.reason });
      return;
    }
    try {
      const downloadedPath = await downloadDocument(documentUrl, settings.outDir, settings.timeoutMs, settings.maxDownloadBytes);
      if (!metadata.downloadedFiles.includes(downloadedPath)) metadata.downloadedFiles.push(downloadedPath);
    } catch (error) {
      metadata.errors.push({ url: documentUrl, message: `Document download failed: ${String(error)}` });
    }
  }
}

async function downloadDocument(url: string, outDir: string, timeoutMs: number, maxBytes: number): Promise<string> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(url, { signal: controller.signal });
    if (!response.ok || !response.body) throw new Error(`HTTP ${response.status}`);
    const contentLength = Number(response.headers.get("content-length") || "0");
    if (contentLength > maxBytes) throw new Error(`File exceeds max download size of ${maxBytes} bytes`);
    const name = filenameFromUrl(url, `${shortHash(url)}.bin`);
    const targetPath = path.join(outDir, "downloads", sanitizeFilename(name));
    const chunks: Uint8Array[] = [];
    let total = 0;
    for await (const chunk of response.body as AsyncIterable<Uint8Array>) {
      total += chunk.length;
      if (total > maxBytes) throw new Error(`File exceeds max download size of ${maxBytes} bytes`);
      chunks.push(chunk);
    }
    await fs.writeFile(targetPath, Buffer.concat(chunks));
    return targetPath;
  } finally {
    clearTimeout(timer);
  }
}
