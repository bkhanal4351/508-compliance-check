import fs from "fs-extra";
import path from "node:path";
import type { Asset } from "../models/Asset.js";
import type { Finding } from "../models/Finding.js";
import type { ScanResult } from "../models/ScanResult.js";
import { createSummary } from "./jsonReport.js";

export async function writeHtmlReport(outDir: string, result: ScanResult): Promise<void> {
  const summary = createSummary(result);
  const findingsByAsset = groupBy(result.findings, (finding) => finding.assetPathOrUrl);
  const automatedFindings = result.findings.filter((finding) => finding.confidence === "automated");
  const reviewFindings = result.findings.filter((finding) => finding.confidence !== "automated");
  const html = `<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>508 Scanner Local Report</title>
  <style>
    body { margin: 0; font-family: system-ui, -apple-system, Segoe UI, sans-serif; color: #17202a; background: #fff; line-height: 1.5; }
    header, main { max-width: 1180px; margin: 0 auto; padding: 24px; }
    header { border-bottom: 4px solid #005ea8; }
    a { color: #005ea8; }
    .skip-link { position: absolute; left: 8px; top: -40px; background: #fff; padding: 8px; border: 2px solid #005ea8; }
    .skip-link:focus { top: 8px; }
    .disclaimer { border-left: 6px solid #b50909; padding: 12px 16px; background: #fff3f2; }
    .interpretation { border-left: 6px solid #2e8540; padding: 12px 16px; background: #f3fff5; margin: 18px 0; }
    .warning { border-left-color: #f9c642; background: #fff8df; }
    table { width: 100%; border-collapse: collapse; margin: 16px 0 28px; }
    caption { text-align: left; font-weight: 700; margin-bottom: 8px; }
    th, td { border: 1px solid #a9b4c0; padding: 8px; vertical-align: top; }
    th { background: #eef3f8; text-align: left; }
    code { overflow-wrap: anywhere; }
    .finding { border-top: 1px solid #a9b4c0; padding: 16px 0; }
    .finding dl { display: grid; grid-template-columns: minmax(130px, 210px) 1fr; gap: 6px 12px; margin: 12px 0; }
    .finding dt { font-weight: 700; }
    .finding dd { margin: 0; }
    .snippet { display: block; white-space: pre-wrap; background: #f5f7fa; border: 1px solid #c8d1da; padding: 8px; margin-top: 4px; }
    .badge { display: inline-block; padding: 2px 6px; border: 1px solid #4b5563; border-radius: 4px; font-size: 0.9rem; }
    .badge.automated { border-color: #b50909; color: #7d0000; background: #fff3f2; }
    .badge.review { border-color: #7d5f00; color: #4d3b00; background: #fff8df; }
  </style>
</head>
<body>
  <a class="skip-link" href="#main">Skip to report content</a>
  <header>
    <h1>508 Scanner Local Report</h1>
    <p>Target: <code>${escapeHtml(result.target || "Local document scan")}</code></p>
    <p>Scan timestamp: ${escapeHtml(result.startedAt)} to ${escapeHtml(result.finishedAt)}</p>
    <p class="disclaimer">This report provides automated and semi-automated Section 508/WCAG issue detection. It is not a full legal certification of accessibility compliance.</p>
  </header>
  <main id="main">
    <h2>Summary</h2>
    ${interpretationBlock(automatedFindings.length, reviewFindings.length)}
    ${summaryTable(summary)}
    <h2>How to Read This Report</h2>
    <table>
      <caption>Finding labels</caption>
      <thead><tr><th scope="col">Label</th><th scope="col">Meaning</th><th scope="col">How to use it</th></tr></thead>
      <tbody>
        <tr><th scope="row">Confirmed Automated Issue</th><td>axe-core or a document checker found a condition that is likely an accessibility failure.</td><td>Treat this as a fix candidate. Use the selector, URL, WCAG criterion, and recommendation to locate and remediate it.</td></tr>
        <tr><th scope="row">Needs Manual Review</th><td>The tool could not prove pass or fail. This includes axe incomplete checks and human-review checklist items.</td><td>Do not count this as confirmed non-compliance until a reviewer verifies it manually.</td></tr>
        <tr><th scope="row">Where</th><td>The page URL, visible text, HTML snippet, and CSS selector when available.</td><td>Open the page, search for the visible text first. If needed, open browser developer tools and run the selector lookup shown in the finding.</td></tr>
      </tbody>
    </table>
    <h2>Confirmed Automated Issues</h2>
    ${findingsTable("Confirmed automated issues", automatedFindings)}
    <h2>Needs Manual Review</h2>
    ${findingsTable("Manual review and inconclusive checks", reviewFindings)}
    <h2>Scan Settings</h2>
    ${objectTable("Scan settings", result.settings)}
    <h2>Assets</h2>
    ${assetsTable(result.assets)}
    <h2>Skipped URLs and Files</h2>
    ${simpleItemsTable("Skipped items", result.skippedItems.map((item) => ({ target: item.target, reason: item.reason })))}
    <h2>Crawl Errors</h2>
    ${simpleItemsTable("Crawl errors", result.crawlErrors.map((item) => ({ target: item.url, reason: item.message })))}
    <h2>Detailed Findings Grouped by Asset</h2>
    ${Object.entries(findingsByAsset).map(([asset, findings]) => assetFindingsSection(asset, findings)).join("\n")}
  </main>
</body>
</html>`;
  await fs.writeFile(path.join(outDir, "report.html"), html);
}

function interpretationBlock(automatedCount: number, reviewCount: number): string {
  if (automatedCount === 0) {
    return `<div class="interpretation">
      <p><strong>No confirmed automated accessibility failures were found in this scan.</strong></p>
      <p>The report still contains ${reviewCount} item(s) that need human review. Those items are not automatic Section 508 non-compliance findings; they are places to verify manually.</p>
    </div>`;
  }
  return `<div class="interpretation warning">
    <p><strong>${automatedCount} confirmed automated issue(s) were found.</strong></p>
    <p>Review those first. The report also contains ${reviewCount} manual-review item(s) that require human judgment before calling them compliant or non-compliant.</p>
  </div>`;
}

function summaryTable(summary: Record<string, unknown>): string {
  return objectTable("Summary metrics", summary);
}

function objectTable(caption: string, object: Record<string, unknown>): string {
  return `<table><caption>${escapeHtml(caption)}</caption><tbody>${Object.entries(object)
    .map(([key, value]) => `<tr><th scope="row">${escapeHtml(key)}</th><td>${escapeHtml(formatValue(value))}</td></tr>`)
    .join("")}</tbody></table>`;
}

function assetsTable(assets: Asset[]): string {
  if (!assets.length) return "<p>No assets were scanned.</p>";
  return `<table><caption>Scanned assets and raw result references</caption><thead><tr><th scope="col">Type</th><th scope="col">Target</th><th scope="col">Raw result</th></tr></thead><tbody>${assets
    .map((asset) => {
      const target = asset.type === "web_page" ? asset.finalUrl || asset.url : asset.path;
      const raw = asset.type === "web_page" ? asset.rawResultPath : asset.rawResultPath;
      return `<tr><td>${escapeHtml(asset.type)}</td><td><code>${escapeHtml(target)}</code></td><td><code>${escapeHtml(raw || "")}</code></td></tr>`;
    })
    .join("")}</tbody></table>`;
}

function simpleItemsTable(caption: string, items: { target: string; reason: string }[]): string {
  if (!items.length) return "<p>None recorded.</p>";
  return `<table><caption>${escapeHtml(caption)}</caption><thead><tr><th scope="col">Target</th><th scope="col">Reason</th></tr></thead><tbody>${items
    .map((item) => `<tr><td><code>${escapeHtml(item.target)}</code></td><td>${escapeHtml(item.reason)}</td></tr>`)
    .join("")}</tbody></table>`;
}

function findingsTable(caption: string, findings: Finding[]): string {
  if (!findings.length) return `<p>No ${escapeHtml(caption.toLowerCase())} recorded.</p>`;
  return `<table>
    <caption>${escapeHtml(caption)}</caption>
    <thead>
      <tr>
        <th scope="col">Result type</th>
        <th scope="col">What</th>
        <th scope="col">Where</th>
        <th scope="col">WCAG / 508</th>
        <th scope="col">What to do</th>
      </tr>
    </thead>
    <tbody>
      ${findings.map((finding) => `<tr>
        <td>${finding.confidence === "automated" ? "Confirmed Automated Issue" : "Needs Manual Review"}</td>
        <td><strong>${escapeHtml(finding.title)}</strong><br><code>${escapeHtml(finding.ruleId)}</code><br>${escapeHtml(finding.description)}</td>
        <td>${whereMarkup(finding)}</td>
        <td>${finding.wcagCriteria.length ? `WCAG ${escapeHtml(finding.wcagCriteria.join(", "))}<br>` : ""}${escapeHtml(finding.section508Reference)}</td>
        <td>${escapeHtml(finding.recommendation)}</td>
      </tr>`).join("")}
    </tbody>
  </table>`;
}

function assetFindingsSection(asset: string, findings: Finding[]): string {
  return `<section><h3><code>${escapeHtml(asset)}</code></h3>${findings
    .map(
      (finding) => `<article class="finding">
        <h4>${escapeHtml(finding.title)}</h4>
        <p><span class="badge ${finding.confidence === "automated" ? "automated" : "review"}">${finding.confidence === "automated" ? "Confirmed Automated Issue" : "Needs Manual Review"}</span> <span class="badge">${escapeHtml(finding.impact)}</span> <code>${escapeHtml(finding.ruleId)}</code></p>
        <dl>
          <dt>What</dt><dd>${escapeHtml(finding.description)}</dd>
          <dt>Where</dt><dd>${whereMarkup(finding)}</dd>
          <dt>Why it matters</dt><dd>${finding.wcagCriteria.length ? `Related WCAG criterion: ${escapeHtml(finding.wcagCriteria.join(", "))}. ` : ""}${escapeHtml(finding.section508Reference)}</dd>
          <dt>Next step</dt><dd>${escapeHtml(finding.recommendation)}</dd>
        </dl>
      </article>`
    )
    .join("")}</section>`;
}

function whereMarkup(finding: Finding): string {
  const visibleText = visibleTextFromSnippet(finding.htmlSnippet);
  const selectorLookup = finding.selector ? `document.querySelector(${JSON.stringify(finding.selector)})` : "";
  return [
    `<strong>Page:</strong> <code>${escapeHtml(finding.assetPathOrUrl)}</code>`,
    visibleText ? `<strong>Visible text:</strong> ${escapeHtml(visibleText)}` : "",
    finding.htmlSnippet ? `<strong>HTML snippet:</strong> <code class="snippet">${escapeHtml(shorten(finding.htmlSnippet, 500))}</code>` : "",
    finding.selector ? `<strong>CSS selector:</strong> <code>${escapeHtml(finding.selector)}</code>` : "",
    selectorLookup ? `<strong>DevTools lookup:</strong> <code>${escapeHtml(selectorLookup)}</code>` : "",
    finding.location ? `<strong>Location:</strong> <code>${escapeHtml(finding.location)}</code>` : ""
  ]
    .filter(Boolean)
    .join("<br>");
}

function visibleTextFromSnippet(snippet?: string): string {
  if (!snippet) return "";
  return shorten(
    snippet
      .replace(/<script[\s\S]*?<\/script>/gi, "")
      .replace(/<style[\s\S]*?<\/style>/gi, "")
      .replace(/<[^>]+>/g, " ")
      .replace(/\s+/g, " ")
      .trim(),
    180
  );
}

function shorten(value: string, maxLength: number): string {
  return value.length > maxLength ? `${value.slice(0, maxLength - 1)}…` : value;
}

function groupBy<T>(values: T[], getKey: (value: T) => string): Record<string, T[]> {
  return values.reduce<Record<string, T[]>>((groups, value) => {
    const key = getKey(value);
    groups[key] ||= [];
    groups[key].push(value);
    return groups;
  }, {});
}

function formatValue(value: unknown): string {
  if (typeof value === "object" && value !== null) return JSON.stringify(value);
  return String(value ?? "");
}

function escapeHtml(value: string): string {
  return value.replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char] || char);
}
