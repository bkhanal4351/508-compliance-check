"""
Wayback Machine availability API client.

For Dead URLs, queries https://archive.org/wayback/available to find the
most recent archived snapshot. Returns the snapshot URL and a human-readable
date so staff know when the content was last captured.
"""
import logging
from datetime import datetime
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

WAYBACK_API = "https://archive.org/wayback/available"
WAYBACK_TIMEOUT = 8.0


def _format_timestamp(ts):
    # type: (str) -> str
    """Convert Wayback timestamp '20230415120000' → 'Apr 15, 2023'."""
    try:
        return datetime.strptime(ts, "%Y%m%d%H%M%S").strftime("%b %d, %Y")
    except Exception:
        return ts


async def fetch_wayback(client, url):
    # type: (...) -> Tuple[Optional[str], Optional[str]]
    """
    Query the Wayback Machine for the closest available snapshot of `url`.

    Returns (snapshot_url, formatted_date) or (None, None) if no snapshot exists
    or the API is unreachable.
    """
    try:
        resp = await client.get(
            WAYBACK_API,
            params={"url": url},
            timeout=WAYBACK_TIMEOUT,
            follow_redirects=True,
        )
        data = resp.json()
        closest = data.get("archived_snapshots", {}).get("closest", {})
        if closest.get("available"):
            snap_url = closest.get("url")
            snap_date = _format_timestamp(closest.get("timestamp", ""))
            logger.debug("Wayback snapshot found for %s: %s (%s)", url, snap_url, snap_date)
            return snap_url, snap_date
    except Exception as e:
        logger.debug("Wayback lookup failed for %s: %s", url, e)

    return None, None
