import fs from "fs-extra";
import path from "node:path";
import type { ScanResult, ScanSettings } from "./models/ScanResult.js";
import type { Asset } from "./models/Asset.js";
import type { Finding } from "./models/Finding.js";
import { createScanId } from "./utils/hashing.js";
import { createLogger } from "./utils/logger.js";
import type { Logger } from "./utils/logger.js";
import { ensureOutputDirs } from "./utils/fs.js";
import { crawlAndScan } from "./crawl/crawler.js";
import { scanDocuments } from "./documents/scanDocuments.js";
import { writeCsvReport } from "./report/csvReport.js";
import { writeHtmlReport } from "./report/htmlReport.js";
import { writeJsonReports } from "./report/jsonReport.js";
import { writeManualReviewReport } from "./report/manualReviewReport.js";

export async function runScan(settings: ScanSettings, loggerOverride?: Logger): Promise<ScanResult> {
  const logger = loggerOverride || createLogger(settings.verbose);
  const scanId = createScanId();
  const startedAt = new Date().toISOString();
  await ensureOutputDirs(settings.outDir);
  logger.info(`Writing reports to ${settings.outDir}`);

  const assets: Asset[] = [];
  const findings: Finding[] = [];
  const crawlErrors: ScanResult["crawlErrors"] = [];
  const skippedItems: ScanResult["skippedItems"] = [];
  let crawl;
  const documentFiles = [...settings.files];

  if (settings.url) {
    const crawlResult = await crawlAndScan(settings.url, scanId, settings, logger);
    assets.push(...crawlResult.assets);
    findings.push(...crawlResult.findings);
    crawl = crawlResult.metadata;
    crawlErrors.push(...crawlResult.metadata.errors);
    skippedItems.push(...crawlResult.metadata.skipped);
    documentFiles.push(...crawlResult.metadata.downloadedFiles);
  }

  if (documentFiles.length) {
    const uniqueFiles = Array.from(new Set(documentFiles.map((file) => path.resolve(file))));
    const documentResult = await scanDocuments(uniqueFiles, scanId, settings.outDir, settings.timeoutMs, logger);
    assets.push(...documentResult.assets);
    findings.push(...documentResult.findings);
    crawlErrors.push(...documentResult.errors);
  }

  const result: ScanResult = {
    scanId,
    startedAt,
    finishedAt: new Date().toISOString(),
    target: settings.url,
    settings,
    assets,
    findings,
    crawl,
    crawlErrors,
    skippedItems,
    toolVersions: await getToolVersions()
  };

  await writeJsonReports(settings.outDir, result);
  await writeCsvReport(settings.outDir, result.findings);
  await writeManualReviewReport(settings.outDir, result.findings);
  await writeHtmlReport(settings.outDir, result);

  logger.info(`Done. Findings: ${result.findings.length}`);
  return result;
}

async function getToolVersions(): Promise<ScanResult["toolVersions"]> {
  const packageJson = await fs.readJson(new URL("../package.json", import.meta.url));
  const versions = packageJson.dependencies || {};
  return {
    node: process.version,
    packageVersion: packageJson.version,
    playwright: versions.playwright,
    axeCorePlaywright: versions["@axe-core/playwright"]
  };
}
