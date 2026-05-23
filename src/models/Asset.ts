import type { AssetType } from "./Finding.js";

export type WebAsset = {
  type: "web_page";
  url: string;
  finalUrl?: string;
  title?: string;
  status?: number;
  depth?: number;
  rawResultPath?: string;
  screenshotPath?: string;
};

export type DocumentAsset = {
  type: Exclude<AssetType, "web_page">;
  path: string;
  sourceUrl?: string;
  sizeBytes?: number;
  rawResultPath?: string;
};

export type Asset = WebAsset | DocumentAsset;
