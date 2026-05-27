BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)

# Case-insensitive substrings that indicate a soft 404 when HTTP status is 200
SOFT_404_PATTERNS = [
    "page not found",
    "404 not found",
    "404 error",
    "doesn't exist",
    "does not exist",
    "no longer available",
    "has been removed",
    "page is no longer",
    "this page cannot be found",
    "sorry, we couldn't find",
    "sorry, we can't find",
    "the page you requested",
    "page has been deleted",
    "no longer exists",
    "could not be found",
    "cannot be found",
    "we couldn't find that page",
    "page was not found",
]

# Sort order for severity display (lower = shown first)
SEVERITY_ORDER = {"Dead": 0, "Suspicious": 1, "Alive": 2, "Skipped": 3}

TIER_BADGE_COLORS = {
    "Dead":       "#cc0000",
    "Suspicious": "#cc7700",
    "Alive":      "#007700",
    "Skipped":    "#666666",
}

# Openpyxl fill hex codes (no leading #)
TIER_EXCEL_FILLS = {
    "Dead":       "FFCCCC",
    "Suspicious": "FFF3CC",
    "Alive":      "CCFFCC",
    "Skipped":    "EEEEEE",
}

SUPPORTED_EXTENSIONS = {".docx", ".pdf", ".pptx", ".xlsx", ".txt", ".html", ".htm"}

MAX_FILE_SIZE_MB = 50
DEFAULT_TIMEOUT = 10
DEFAULT_MAX_WORKERS = 20
MAX_REDIRECTS = 5
MAX_RETRY_AFTER_SECS = 5
BODY_PREVIEW_BYTES = 5120
