# =============================================================================
# constants.py — Shared settings used by every part of the app.
# Think of this file like a "control panel" — changing a value here changes
# behaviour everywhere without hunting through dozens of other files.
# =============================================================================

# When the tool visits a URL it pretends to be a real Chrome browser on Windows.
# Many websites block requests that look like automated bots, so using a
# realistic browser identity ("User-Agent") avoids false "blocked" results.
BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)

# A list of phrases that appear on "Page Not Found" error pages even when the
# web server technically returns an OK (200) response.  Some websites are lazy
# and return a 200 status but show an error message in the page body — this
# list lets us catch those "fake OK" responses, called "soft 404s".
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

# Controls the order in which results are sorted on screen and in exports.
# Dead links are most urgent so they appear first (0), then Suspicious (1),
# then working links (2), then skipped ones (3).
SEVERITY_ORDER = {"Dead": 0, "Suspicious": 1, "Alive": 2, "Skipped": 3}

# Hex colour codes used to colour status badges in the Streamlit UI.
# Dark red = dead, dark orange = suspicious, dark green = alive, grey = skipped.
TIER_BADGE_COLORS = {
    "Dead":       "#cc0000",   # dark red
    "Suspicious": "#cc7700",   # dark orange
    "Alive":      "#007700",   # dark green
    "Skipped":    "#666666",   # grey
}

# Hex colour codes used to shade rows in the Excel export.
# These are lighter pastel versions of the badge colours so text stays readable.
# Note: openpyxl (the Excel library) does not use a # prefix.
TIER_EXCEL_FILLS = {
    "Dead":       "FFCCCC",   # light red background
    "Suspicious": "FFF3CC",   # light yellow background
    "Alive":      "CCFFCC",   # light green background
    "Skipped":    "EEEEEE",   # light grey background
}

# The file types (extensions) this tool knows how to read.
# A user uploading any other type will see a "not supported" warning.
SUPPORTED_EXTENSIONS = {".docx", ".pdf", ".pptx", ".xlsx", ".txt", ".html", ".htm"}

# The largest file the tool will accept (in megabytes).
# Files bigger than this are rejected to avoid slow uploads and memory issues.
MAX_FILE_SIZE_MB = 50

# How many seconds the tool waits for a website to respond before giving up.
DEFAULT_TIMEOUT = 10

# How many URLs are checked at the same time (concurrently).
# 20 means 20 web requests fly out in parallel — more = faster but
# also more likely to get rate-limited by servers.
DEFAULT_MAX_WORKERS = 20

# Maximum number of redirects to follow before stopping.
# (e.g. A → B → C → D → E = 4 redirects; at 5 we stop.)
MAX_REDIRECTS = 5

# If a server says "please wait X seconds before retrying" (via Retry-After
# header), we honour it — but cap it at this many seconds so we don't wait forever.
MAX_RETRY_AFTER_SECS = 5

# How many bytes of each web page we read for soft-404 detection.
# 5120 bytes = 5 KB, which is enough to contain any "page not found" message
# near the top of the page without downloading the entire page.
BODY_PREVIEW_BYTES = 5120
