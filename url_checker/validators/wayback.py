# =============================================================================
# wayback.py — Looks up whether a dead URL has an archived copy on the
# Wayback Machine (web.archive.org).
#
# When a URL is confirmed Dead, we ask the Internet Archive: "Did you ever
# save a copy of this page?"  If yes, we give staff a link to the last known
# good version so they have a starting point to find where the content moved.
# =============================================================================

import logging
from datetime import datetime
from typing import Optional, Tuple

# logger sends diagnostic messages to the terminal (not shown to end users)
logger = logging.getLogger(__name__)

# The Internet Archive's public API endpoint for checking snapshot availability.
# You pass it a URL and it tells you whether an archived copy exists.
WAYBACK_API = "https://archive.org/wayback/available"

# How many seconds we wait for the Wayback API to respond before giving up.
# We use a separate timeout from the main URL checks because archive.org
# can sometimes be slow independently of the target website.
WAYBACK_TIMEOUT = 8.0


def _format_timestamp(ts):
    # type: (str) -> str
    """
    Convert the Wayback Machine's compact timestamp format into a readable date.
    The API returns timestamps like "20230415120000" (YYYYMMDDHHmmss).
    We convert that to "Apr 15, 2023" for display.
    """
    try:
        # strptime parses the string according to the format pattern
        # strftime then reformats it as "Month DD, YYYY"
        return datetime.strptime(ts, "%Y%m%d%H%M%S").strftime("%b %d, %Y")
    except Exception:
        # If parsing fails for any reason, just return the raw string
        return ts


async def fetch_wayback(client, url):
    # type: (...) -> Tuple[Optional[str], Optional[str]]
    """
    Ask the Wayback Machine whether it has an archived snapshot of `url`.

    `client` is the shared httpx HTTP client — we reuse it instead of creating
    a new connection, which is faster.

    Returns a pair: (snapshot_url, formatted_date)
      snapshot_url   — the full archive.org URL to view the snapshot, or None
      formatted_date — human-readable date like "Apr 15, 2023", or None
    """
    try:
        # Make a GET request to the Wayback API.
        # params={"url": url} appends "?url=https://example.com" to the API address.
        # follow_redirects=True lets us follow any redirects the API itself makes.
        resp = await client.get(
            WAYBACK_API,
            params={"url": url},
            timeout=WAYBACK_TIMEOUT,
            follow_redirects=True,
        )

        # Parse the JSON response body into a Python dictionary
        data = resp.json()

        # Dig into the nested dictionary to find the closest snapshot.
        # The API response looks like:
        # { "archived_snapshots": { "closest": { "available": true,
        #     "url": "https://web.archive.org/web/20230415...", "timestamp": "20230415120000" } } }
        # .get() with a default of {} means we won't crash if a key is missing
        closest = data.get("archived_snapshots", {}).get("closest", {})

        # Only proceed if the API confirmed a snapshot is available
        if closest.get("available"):
            snap_url = closest.get("url")           # the full archive.org link
            snap_date = _format_timestamp(closest.get("timestamp", ""))  # convert to readable date
            logger.debug("Wayback snapshot found for %s: %s (%s)", url, snap_url, snap_date)
            return snap_url, snap_date              # success — return both pieces

    except Exception as e:
        # Network errors, timeouts, bad JSON — just log quietly and move on.
        # Wayback lookup is a best-effort bonus; a failure here should not
        # affect the main URL check result.
        logger.debug("Wayback lookup failed for %s: %s", url, e)

    # No snapshot found, or the lookup failed — return two Nones
    return None, None
