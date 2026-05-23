export const DOCUMENT_EXTENSIONS = [
  ".pdf",
  ".docx",
  ".pptx",
  ".xlsx",
  ".doc",
  ".ppt",
  ".xls",
  ".rtf",
  ".odt",
  ".ods",
  ".odp",
  ".csv"
];

const IGNORED_PROTOCOLS = new Set(["mailto:", "tel:", "javascript:", "data:", "blob:"]);

export function normalizeUrl(rawUrl: string, baseUrl?: string): string | null {
  try {
    const parsed = new URL(rawUrl, baseUrl);
    if (IGNORED_PROTOCOLS.has(parsed.protocol)) return null;
    if (parsed.protocol !== "http:" && parsed.protocol !== "https:") return null;
    parsed.hash = "";
    parsed.username = "";
    parsed.password = "";
    if ((parsed.protocol === "http:" && parsed.port === "80") || (parsed.protocol === "https:" && parsed.port === "443")) {
      parsed.port = "";
    }
    parsed.hostname = parsed.hostname.toLowerCase();
    parsed.pathname = parsed.pathname.replace(/\/{2,}/g, "/");
    if (parsed.pathname !== "/" && parsed.pathname.endsWith("/")) {
      parsed.pathname = parsed.pathname.slice(0, -1);
    }
    return parsed.toString();
  } catch {
    return null;
  }
}

export function isDocumentUrl(url: string): boolean {
  try {
    const pathname = new URL(url).pathname.toLowerCase();
    return DOCUMENT_EXTENSIONS.some((extension) => pathname.endsWith(extension));
  } catch {
    return false;
  }
}

export function filenameFromUrl(url: string, fallbackName: string): string {
  try {
    const pathname = decodeURIComponent(new URL(url).pathname);
    const name = pathname.split("/").filter(Boolean).pop();
    return name && name.includes(".") ? sanitizeFilename(name) : fallbackName;
  } catch {
    return fallbackName;
  }
}

export function sanitizeFilename(name: string): string {
  return name.replace(/[^a-zA-Z0-9._-]/g, "_").slice(0, 180);
}
