import { AxeBuilder } from "@axe-core/playwright";
import type { Browser } from "playwright";
import path from "node:path";
import fs from "fs-extra";
import type { Finding } from "../models/Finding.js";
import type { WebAsset } from "../models/Asset.js";
import type { PageMetadata } from "./pageMetadata.js";
import { extractRenderedLinks, getPageMetadata } from "./pageMetadata.js";
import { mapAxeIncomplete, mapAxeViolations } from "./axeMapper.js";
import { shortHash } from "../utils/hashing.js";

export type PageScanResult = {
  asset: WebAsset;
  metadata?: PageMetadata;
  findings: Finding[];
  passCount: number;
  links: string[];
};

export async function scanPage(
  browser: Browser,
  url: string,
  scanId: string,
  outDir: string,
  includeScreenshots: boolean,
  timeoutMs: number,
  depth?: number
): Promise<PageScanResult> {
  const context = await browser.newContext();
  const page = await context.newPage();
  page.setDefaultTimeout(timeoutMs);
  const slug = shortHash(url);
  const rawPath = path.join(outDir, "raw", "web", `${slug}.json`);
  const screenshotPath = path.join(outDir, "screenshots", `${slug}.png`);

  try {
    const response = await page.goto(url, { waitUntil: "networkidle", timeout: timeoutMs });
    const finalUrl = page.url();
    const metadata = await getPageMetadata(page);
    const links = await extractRenderedLinks(page);
    const axeResults = await runAxe(page);
    await fs.writeJson(rawPath, { url, finalUrl, metadata, axe: axeResults }, { spaces: 2 });
    if (includeScreenshots) {
      await page.screenshot({ path: screenshotPath, fullPage: true });
    }
    const findings = [
      ...mapAxeViolations(scanId, finalUrl, axeResults),
      ...mapAxeIncomplete(scanId, finalUrl, axeResults),
      ...manualReviewFindings(scanId, finalUrl, metadata)
    ];
    return {
      asset: {
        type: "web_page",
        url,
        finalUrl,
        title: metadata.title,
        status: response?.status(),
        depth,
        rawResultPath: rawPath,
        screenshotPath: includeScreenshots ? screenshotPath : undefined
      },
      metadata,
      findings,
      passCount: axeResults.passes.length,
      links
    };
  } finally {
    await context.close();
  }
}

async function runAxe(page: import("playwright").Page): Promise<import("axe-core").AxeResults> {
  try {
    return await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "section508"]).analyze();
  } catch (error) {
    if (String(error).toLowerCase().includes("section508")) {
      return new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze();
    }
    throw error;
  }
}

function manualReviewFindings(scanId: string, url: string, metadata: PageMetadata): Finding[] {
  const base = [
    ["manual.keyboard", "Keyboard-only navigation", "Validate that all interactive content can be reached and operated by keyboard."],
    ["manual.focus-order", "Visible focus order", "Validate focus visibility and logical focus order."],
    ["manual.screen-reader-order", "Screen reader reading order", "Validate reading order and accessible names with assistive technology."],
    ["manual.image-alt-meaning", "Meaningfulness of image alternative text", "Validate whether image text alternatives are accurate and meaningful."],
    ["manual.link-text-context", "Meaningfulness of link text in context", "Validate links make sense in their surrounding context."]
  ];
  if (metadata.formControlCount > 0) {
    base.push(["manual.form-errors", "Error message clarity for forms", "Validate form labels, instructions, and error messages."]);
  }
  if (metadata.mediaCount > 0) {
    base.push(["manual.media-captions", "Captions/transcripts for audio/video", "Validate captions, transcripts, and audio descriptions where needed."]);
  }
  if (metadata.mediaCount > 0 || metadata.hasAnimations) {
    base.push(["manual.motion", "Motion/animation pause, stop, hide review", "Validate moving or auto-updating content can be paused, stopped, or hidden."]);
  }

  return base.map(([ruleId, title, description]) => ({
    id: shortHash(`${scanId}:${url}:${ruleId}`),
    scanId,
    assetType: "web_page",
    assetPathOrUrl: url,
    ruleId,
    title,
    description,
    impact: "needs_review",
    confidence: "manual_required",
    wcagCriteria: [],
    section508Reference: "Section 508 Revised Standards E205.4 / WCAG A-AA related requirement",
    recommendation: description
  }));
}
