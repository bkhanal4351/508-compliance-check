#!/usr/bin/env node
import http from "node:http";
import fs from "fs-extra";
import path from "node:path";
import { runScan } from "./index.js";
import type { ScanResult, ScanSettings } from "./models/ScanResult.js";
import type { Logger } from "./utils/logger.js";

type JobStatus = "queued" | "running" | "completed" | "failed";

type ScanJob = {
  id: string;
  status: JobStatus;
  createdAt: string;
  updatedAt: string;
  settings: ScanSettings;
  messages: string[];
  result?: ScanResult;
  error?: string;
};

const projectRoot = process.cwd();
const publicDir = path.join(projectRoot, "public");
const reportsRoot = path.join(projectRoot, "reports");
const jobs = new Map<string, ScanJob>();

const host = process.env.HOST || "127.0.0.1";
const port = Number(process.env.PORT || 5081);

const server = http.createServer(async (request, response) => {
  try {
    const url = new URL(request.url || "/", `http://${request.headers.host || `${host}:${port}`}`);
    if (request.method === "GET" && url.pathname === "/") return serveFile(response, path.join(publicDir, "index.html"));
    if (request.method === "GET" && url.pathname.startsWith("/assets/")) {
      return serveFile(response, path.join(publicDir, url.pathname.replace(/^\/assets\//, "")));
    }
    if (request.method === "GET" && url.pathname === "/api/jobs") return json(response, Array.from(jobs.values()).map(serializeJob));
    if (request.method === "GET" && url.pathname.startsWith("/api/jobs/")) {
      const job = jobs.get(url.pathname.split("/").pop() || "");
      return job ? json(response, serializeJob(job)) : notFound(response);
    }
    if (request.method === "POST" && url.pathname === "/api/scans") return createScanJob(request, response);
    if (request.method === "GET" && url.pathname.startsWith("/reports/")) {
      return serveFile(response, safeJoin(projectRoot, decodeURIComponent(url.pathname.slice(1))));
    }
    return notFound(response);
  } catch (error) {
    json(response, { error: String(error) }, 500);
  }
});

server.listen(port, host, () => {
  console.log(`508 Scanner Local UI running at http://${host}:${port}`);
});

async function createScanJob(request: http.IncomingMessage, response: http.ServerResponse): Promise<void> {
  const body = await readJsonBody(request);
  const id = `job-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
  const requestedOutName = typeof body.outName === "string" && body.outName.trim()
    ? body.outName
    : `ui-scan-${new Date().toISOString().replace(/[:.]/g, "-")}`;
  const outName = sanitizePathSegment(requestedOutName);
  const settings: ScanSettings = {
    url: emptyToUndefined(body.url),
    files: Array.isArray(body.files) ? body.files.filter((file): file is string => typeof file === "string" && Boolean(file)) : splitLines(body.filesText),
    maxPages: numberOrDefault(body.maxPages, 25),
    maxDepth: numberOrDefault(body.maxDepth, 3),
    concurrency: Math.max(1, numberOrDefault(body.concurrency, 2)),
    outDir: path.join(reportsRoot, outName),
    includeScreenshots: Boolean(body.includeScreenshots),
    downloadDocuments: body.downloadDocuments !== false,
    timeoutMs: numberOrDefault(body.timeoutMs, 60000),
    sameOrigin: body.sameOrigin !== false,
    sameHost: body.sameHost !== false,
    verbose: Boolean(body.verbose),
    maxDownloadBytes: 50 * 1024 * 1024
  };

  if (!settings.url && settings.files.length === 0) {
    return json(response, { error: "Provide a URL, one or more local file paths, or both." }, 400);
  }

  const job: ScanJob = {
    id,
    status: "queued",
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
    settings,
    messages: ["Scan queued."]
  };
  jobs.set(id, job);
  void runJob(job);
  json(response, serializeJob(job), 202);
}

async function runJob(job: ScanJob): Promise<void> {
  job.status = "running";
  job.updatedAt = new Date().toISOString();
  job.messages.push("Scan started.");
  const logger = jobLogger(job);
  try {
    job.result = await runScan(job.settings, logger);
    job.status = "completed";
    job.messages.push("Scan completed.");
  } catch (error) {
    job.status = "failed";
    job.error = String(error);
    job.messages.push(`Scan failed: ${String(error)}`);
  } finally {
    job.updatedAt = new Date().toISOString();
  }
}

function jobLogger(job: ScanJob): Logger {
  const push = (level: string, message: string) => {
    job.messages.push(`${new Date().toLocaleTimeString()} ${level}: ${message}`);
    job.updatedAt = new Date().toISOString();
  };
  return {
    info: (message) => push("info", message),
    warn: (message) => push("warn", message),
    error: (message) => push("error", message),
    verbose: (message) => {
      if (job.settings.verbose) push("verbose", message);
    }
  };
}

function serializeJob(job: ScanJob): Record<string, unknown> {
  const relativeOut = path.relative(projectRoot, job.settings.outDir).split(path.sep).join("/");
  return {
    id: job.id,
    status: job.status,
    createdAt: job.createdAt,
    updatedAt: job.updatedAt,
    target: job.settings.url || "Document scan",
    outDir: job.settings.outDir,
    reportUrl: `/${relativeOut}/report.html`,
    summaryUrl: `/${relativeOut}/summary.json`,
    csvUrl: `/${relativeOut}/findings.csv`,
    manualReviewUrl: `/${relativeOut}/manual-review.md`,
    messages: job.messages.slice(-100),
    error: job.error,
    summary: job.result
      ? {
          findings: job.result.findings.length,
          assets: job.result.assets.length,
          manualReviewItems: job.result.findings.filter((finding) => finding.confidence === "manual_required").length,
          automatedIssues: job.result.findings.filter((finding) => finding.confidence === "automated").length
        }
      : undefined
  };
}

async function readJsonBody(request: http.IncomingMessage): Promise<Record<string, unknown>> {
  let raw = "";
  for await (const chunk of request) raw += String(chunk);
  return raw ? JSON.parse(raw) : {};
}

function splitLines(value: unknown): string[] {
  return typeof value === "string" ? value.split(/\r?\n/).map((line) => line.trim()).filter(Boolean) : [];
}

function emptyToUndefined(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() ? value.trim() : undefined;
}

function numberOrDefault(value: unknown, fallback: number): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : fallback;
}

function sanitizePathSegment(value: string): string {
  return value.replace(/[^a-zA-Z0-9._-]/g, "_").slice(0, 120) || "ui-scan";
}

function safeJoin(root: string, target: string): string {
  const resolved = path.resolve(root, target);
  if (!resolved.startsWith(root)) throw new Error("Requested path is outside the project directory.");
  return resolved;
}

async function serveFile(response: http.ServerResponse, filePath: string): Promise<void> {
  if (!(await fs.pathExists(filePath)) || (await fs.stat(filePath)).isDirectory()) return notFound(response);
  response.writeHead(200, { "content-type": contentType(filePath) });
  fs.createReadStream(filePath).pipe(response);
}

function json(response: http.ServerResponse, value: unknown, status = 200): void {
  response.writeHead(status, { "content-type": "application/json" });
  response.end(JSON.stringify(value));
}

function notFound(response: http.ServerResponse): void {
  response.writeHead(404, { "content-type": "text/plain; charset=utf-8" });
  response.end("Not found");
}

function contentType(filePath: string): string {
  const extension = path.extname(filePath).toLowerCase();
  if (extension === ".html") return "text/html; charset=utf-8";
  if (extension === ".css") return "text/css; charset=utf-8";
  if (extension === ".js") return "text/javascript; charset=utf-8";
  if (extension === ".json") return "application/json; charset=utf-8";
  if (extension === ".csv") return "text/csv; charset=utf-8";
  if (extension === ".md") return "text/markdown; charset=utf-8";
  if (extension === ".png") return "image/png";
  return "application/octet-stream";
}
