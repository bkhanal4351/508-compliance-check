import type { Asset } from "./Asset.js";
import type { Finding } from "./Finding.js";

export type ScanSettings = {
  url?: string;
  files: string[];
  maxPages: number;
  maxDepth: number;
  concurrency: number;
  outDir: string;
  includeScreenshots: boolean;
  downloadDocuments: boolean;
  timeoutMs: number;
  sameOrigin: boolean;
  sameHost: boolean;
  verbose: boolean;
  maxDownloadBytes: number;
};

export type CrawlError = {
  url: string;
  message: string;
  depth?: number;
  status?: number;
};

export type SkippedItem = {
  target: string;
  reason: string;
};

export type CrawlMetadata = {
  startedAt: string;
  finishedAt?: string;
  startUrl?: string;
  pagesVisited: string[];
  documentsFound: string[];
  downloadedFiles: string[];
  errors: CrawlError[];
  skipped: SkippedItem[];
};

export type ToolVersions = {
  node: string;
  packageVersion: string;
  playwright?: string;
  axeCorePlaywright?: string;
};

export type ScanResult = {
  scanId: string;
  startedAt: string;
  finishedAt: string;
  target?: string;
  settings: ScanSettings;
  assets: Asset[];
  findings: Finding[];
  crawl?: CrawlMetadata;
  crawlErrors: CrawlError[];
  skippedItems: SkippedItem[];
  toolVersions: ToolVersions;
};
