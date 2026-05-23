#!/usr/bin/env node
import { Command } from "commander";
import path from "node:path";
import { runScan } from "./index.js";
import type { ScanSettings } from "./models/ScanResult.js";

const program = new Command();

program
  .name("508-scanner-local")
  .description("Local-first Section 508 / WCAG automated and semi-automated scanner.")
  .option("--url <url>", "Starting website URL")
  .option("--files <paths...>", "Local document files to scan", [])
  .option("--max-pages <number>", "Maximum pages to crawl", parseInteger, 25)
  .option("--max-depth <number>", "Maximum crawl depth", parseInteger, 3)
  .option("--concurrency <number>", "Concurrent page scans", parseInteger, 2)
  .option("--out <directory>", "Output directory")
  .option("--include-screenshots", "Save screenshots for scanned pages", false)
  .option("--download-documents", "Download discovered documents", true)
  .option("--no-download-documents", "Do not download discovered documents")
  .option("--timeout-ms <number>", "Page and document timeout in milliseconds", parseInteger, 60000)
  .option("--same-origin", "Restrict crawl to the same origin", true)
  .option("--no-same-origin", "Allow URLs outside the same origin when same-host also allows them")
  .option("--same-host", "Restrict crawl to the same host", true)
  .option("--no-same-host", "Allow URLs outside the same host when same-origin also allows them")
  .option("--verbose", "Show verbose progress", false)
  .action(async (options) => {
    if (!options.url && (!options.files || options.files.length === 0)) {
      program.error("Provide --url, --files, or both.");
    }
    const outDir = path.resolve(options.out || path.join("reports", timestampForPath()));
    const settings: ScanSettings = {
      url: options.url,
      files: options.files || [],
      maxPages: options.maxPages,
      maxDepth: options.maxDepth,
      concurrency: Math.max(1, options.concurrency),
      outDir,
      includeScreenshots: Boolean(options.includeScreenshots),
      downloadDocuments: Boolean(options.downloadDocuments),
      timeoutMs: options.timeoutMs,
      sameOrigin: Boolean(options.sameOrigin),
      sameHost: Boolean(options.sameHost),
      verbose: Boolean(options.verbose),
      maxDownloadBytes: 50 * 1024 * 1024
    };
    try {
      await runScan(settings);
    } catch (error) {
      console.error(`Scan failed: ${String(error)}`);
      process.exitCode = 1;
    }
  });

program.parseAsync();

function parseInteger(value: string): number {
  const parsed = Number.parseInt(value, 10);
  if (!Number.isFinite(parsed) || parsed < 0) throw new Error(`Invalid number: ${value}`);
  return parsed;
}

function timestampForPath(): string {
  return new Date().toISOString().replace(/[:.]/g, "-");
}
