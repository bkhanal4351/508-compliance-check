# =============================================================================
# url_checker.py — The engine that actually visits URLs and checks if they work.
#
# Key ideas:
#   • "Async" means many URLs are checked at the same time (in parallel),
#     instead of one-by-one.  Think of it like having 20 staff members each
#     calling a different number simultaneously rather than one person making
#     20 calls in sequence.
#   • A "semaphore" is a counter that limits how many checks run at once,
#     so we don't accidentally overload a server or get banned.
#   • The function that Streamlit calls (check_urls) is synchronous (normal),
#     but internally it spins up the async engine in a separate thread to
#     avoid conflicting with Streamlit's own background machinery.
# =============================================================================

import asyncio                      # Python's built-in async / concurrency library
import concurrent.futures           # lets us run async code from synchronous code
import logging
import re
import time
from collections import defaultdict # a dict that creates a default value for missing keys
from typing import Callable, Dict, List, Optional, Tuple

import httpx   # the HTTP library — like requests but supports async

from extractors.base import CheckResult, ExtractedUrl, UrlLocation
from url_checker_utils.constants import (
    BODY_PREVIEW_BYTES,      # max bytes to read per page (5 KB)
    BROWSER_UA,              # the fake browser identity string
    DEFAULT_MAX_WORKERS,     # default number of parallel checks (20)
    DEFAULT_TIMEOUT,         # default seconds to wait per URL (10)
    MAX_RETRY_AFTER_SECS,    # max seconds to honour a Retry-After header (5)
)
from url_checker_utils.url_utils import classify_skip_reason, is_epa_internal, normalize_url
from validators.status_classifier import classify_url_result
from validators.wayback import fetch_wayback

logger = logging.getLogger(__name__)

# A compiled regex that extracts the <title>...</title> value from HTML.
# Used when the "fetch page titles" option is turned on.
_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)


# -----------------------------------------------------------------------------
# group_by_url — Deduplicate URLs before checking
# -----------------------------------------------------------------------------

def group_by_url(extracted):
    # type: (List[ExtractedUrl]) -> Dict[str, List[UrlLocation]]
    """
    Take the raw list of every URL found in every document (possibly with
    duplicates) and produce a dictionary:
        { canonical_url: [list of all locations where it appeared] }

    This way we check each unique URL only once, but still know every place
    it appeared so we can show staff all affected spots in their documents.
    """
    # defaultdict(list) is like a normal dict but automatically creates an empty
    # list for any key that doesn't exist yet, so we can .append() without checking first
    groups = defaultdict(list)  # type: Dict[str, List[UrlLocation]]

    # First pass: group every occurrence by its normalized (standardised) URL
    for e in extracted:
        key = normalize_url(e.url)       # e.g. both "HTTP://EPA.GOV/page" and
                                          # "http://epa.gov/page/" map to the same key
        groups[key].append(UrlLocation(
            source_file=e.source_file,
            location=e.location,
            context=e.context,
            link_type=e.link_type,
        ))

    # Second pass: build the final dict using the FIRST raw form of each URL
    # as the canonical key (so we preserve the original capitalisation/form)
    canonical = {}  # type: Dict[str, List[UrlLocation]]
    seen_norm = {}  # type: Dict[str, str]   — tracks which norms we've already seen
    for e in extracted:
        norm = normalize_url(e.url)
        if norm not in seen_norm:          # first time we see this normalized form
            seen_norm[norm] = e.url        # remember the raw form
            canonical[e.url] = groups[norm]  # map raw URL → all its locations
    return canonical


# -----------------------------------------------------------------------------
# _check_one — Handle one URL (skip it, or call _do_request)
# -----------------------------------------------------------------------------

async def _check_one(client, sem, url, locations, fetch_titles, retry, on_progress):
    """
    Entry point for checking a single URL.
    First decides if the URL should be skipped entirely (e.g. mailto: links).
    If not skipped, acquires a slot from the semaphore and runs the real request.
    After the check, if the URL is Dead, asks the Wayback Machine for a snapshot.
    """
    # Ask url_utils whether this URL should be skipped without checking
    skip_reason = classify_skip_reason(url)
    if skip_reason:
        # Build a "Skipped" result immediately, no HTTP request needed
        result = CheckResult(
            url=url,
            final_url=None,        # we never visited it so there's no final destination
            status_code=None,      # no HTTP response
            tier="Skipped",
            redirect_count=0,
            redirect_chain=[],
            response_time_ms=0.0,
            error_type=None,
            reason=skip_reason,    # e.g. "mailto: link" or "Relative URL"
            page_title=None,
            is_epa_internal=is_epa_internal(url),
            locations=locations,
        )
        if on_progress:
            on_progress(url, result)   # notify the progress tracker
        return result

    # "async with sem" acquires one concurrency slot.  If 20 checks are already
    # running and the limit is 20, this line PAUSES until one slot frees up.
    async with sem:
        result = await _do_request(client, url, locations, fetch_titles, retries=1 if retry else 0)

    # After releasing the semaphore slot, do the Wayback lookup for Dead URLs.
    # We do this OUTSIDE the semaphore so the Wayback request doesn't use up
    # one of the concurrency slots intended for main URL checks.
    if result.tier == "Dead":
        snap_url, snap_date = await fetch_wayback(client, url)
        result.wayback_url = snap_url                        # e.g. "https://web.archive.org/web/..."
        result.wayback_snapshot_date = snap_date             # e.g. "Apr 15, 2023"

    if on_progress:
        on_progress(url, result)   # tell the progress bar this URL is done
    return result


# -----------------------------------------------------------------------------
# _do_request — Make the actual HTTP GET request and return a CheckResult
# -----------------------------------------------------------------------------

async def _do_request(client, url, locations, fetch_titles, retries):
    """
    Visit a URL and gather everything about the response:
    status code, redirect chain, a small body preview, and optionally the page title.
    Then passes all that data to the classifier to get a verdict.
    Retries once on server errors (5xx) or rate-limit responses (429).
    """
    # Record the start time so we can measure how long the request took
    start = time.monotonic()
    try:
        body_preview = b""          # will accumulate up to 5 KB of the response body
        redirect_chain = []         # will record each redirect hop: [(status, url), ...]
        status_code = None
        final_url = url             # may change if there are redirects
        page_title = None
        retry_after = None          # seconds to wait if the server sends a Retry-After header

        # "async with client.stream(...)" opens a streaming connection.
        # Unlike a normal GET, streaming lets us read just the first 5 KB
        # and then stop — instead of downloading the entire potentially large page.
        # follow_redirects=True means httpx automatically follows 301/302 redirects.
        async with client.stream("GET", url, follow_redirects=True) as resp:

            # resp.history is the list of all redirect responses before the final one.
            # We record each hop's status code and destination URL.
            redirect_chain = [(r.status_code, str(r.url)) for r in resp.history]

            # resp.status_code is the FINAL status (after all redirects)
            status_code = resp.status_code

            # resp.url is where we actually ended up (may differ from original url)
            final_url = str(resp.url)

            # Some servers respond to too-many-requests with a "Retry-After: 30"
            # header telling us to wait 30 seconds before trying again
            retry_after_hdr = resp.headers.get("Retry-After")

            # Read the response body in 1 KB chunks until we have 5 KB total.
            # aiter_bytes() yields chunks of bytes asynchronously.
            async for chunk in resp.aiter_bytes(chunk_size=1024):
                body_preview += chunk
                # Stop reading once we have enough for soft-404 detection
                if len(body_preview) >= BODY_PREVIEW_BYTES:
                    break

            # If the user asked for page titles, scan the body preview for <title>
            if fetch_titles and status_code == 200:
                text = body_preview.decode("utf-8", errors="replace")
                m = _TITLE_RE.search(text)
                if m:
                    # m.group(1) is the text between <title> and </title>
                    # [:200] caps it at 200 characters to avoid very long titles
                    page_title = m.group(1).strip()[:200]

            # Parse the Retry-After header if present; cap it at our maximum
            if retry_after_hdr:
                try:
                    retry_after = min(int(retry_after_hdr), MAX_RETRY_AFTER_SECS)
                except ValueError:
                    retry_after = 1   # default to 1 second if the header value is not a number

        # If the server is overloaded (429 = too many requests) or broken (5xx)
        # AND we have retries left, wait briefly then try the same URL again
        if retries > 0 and status_code is not None and (status_code == 429 or status_code >= 500):
            wait = retry_after if retry_after else 1   # wait at least 1 second
            await asyncio.sleep(wait)                  # pause this coroutine (not the whole app)
            # Recursive call with retries reduced by 1 — prevents infinite loops
            return await _do_request(client, url, locations, fetch_titles, retries - 1)

        # How many milliseconds the full request took
        elapsed_ms = (time.monotonic() - start) * 1000

        # Ask the classifier for the verdict given what we collected
        tier, reason = classify_url_result(url, status_code, final_url, redirect_chain, body_preview, None)

        return CheckResult(
            url=url,
            # If final_url is the same as the original, store None (no redirect happened)
            final_url=final_url if final_url != url else None,
            status_code=status_code,
            tier=tier,
            redirect_count=len(redirect_chain),   # number of hops
            redirect_chain=redirect_chain,
            response_time_ms=round(elapsed_ms, 1),
            error_type=None,                       # no connection error — we got a response
            reason=reason,
            page_title=page_title,
            is_epa_internal=is_epa_internal(url),
            locations=locations,
        )

    # ---- Error handling: the request failed before we got any response ----

    except httpx.TimeoutException:
        # The server took longer than `timeout` seconds to respond at all
        if retries > 0:
            await asyncio.sleep(1)
            return await _do_request(client, url, locations, fetch_titles, retries - 1)
        elapsed_ms = (time.monotonic() - start) * 1000
        return CheckResult(
            url=url, final_url=None, status_code=None, tier="Dead",
            redirect_count=0, redirect_chain=[],
            response_time_ms=round(elapsed_ms, 1),
            error_type="timeout", reason="Request timed out after retry",
            page_title=None, is_epa_internal=is_epa_internal(url), locations=locations,
        )

    except httpx.ConnectError as e:
        # A connection-level failure: DNS didn't resolve, SSL handshake failed,
        # or the server actively refused the connection.
        if retries > 0:
            await asyncio.sleep(1)
            return await _do_request(client, url, locations, fetch_titles, retries - 1)
        elapsed_ms = (time.monotonic() - start) * 1000

        # Inspect the error message to figure out which kind of failure it was
        err_str = str(e).lower()
        if "ssl" in err_str or "certificate" in err_str or "tls" in err_str:
            error_type = "ssl"       # HTTPS certificate problem
        elif any(k in err_str for k in ("name", "resolve", "nodename", "getaddrinfo")):
            error_type = "dns"       # domain name not found
        else:
            error_type = "connection_refused"   # server actively refused the connection

        # Get the appropriate reason text from the classifier
        tier, reason = classify_url_result(url, None, None, [], b"", error_type)
        return CheckResult(
            url=url, final_url=None, status_code=None, tier=tier,
            redirect_count=0, redirect_chain=[],
            response_time_ms=round(elapsed_ms, 1),
            error_type=error_type, reason=reason,
            page_title=None, is_epa_internal=is_epa_internal(url), locations=locations,
        )

    except Exception as e:
        # Catch-all for any unexpected error — mark Dead and show the error message
        elapsed_ms = (time.monotonic() - start) * 1000
        return CheckResult(
            url=url, final_url=None, status_code=None, tier="Dead",
            redirect_count=0, redirect_chain=[],
            response_time_ms=round(elapsed_ms, 1),
            error_type="unknown", reason=str(e)[:200],   # cap at 200 chars
            page_title=None, is_epa_internal=is_epa_internal(url), locations=locations,
        )


# -----------------------------------------------------------------------------
# _check_all_async — Orchestrate all checks running at the same time
# -----------------------------------------------------------------------------

async def _check_all_async(url_groups, timeout, max_workers, fetch_titles, retry, on_progress):
    """
    Creates the shared HTTP client and semaphore, then fires off all URL checks
    concurrently (at the same time), up to max_workers simultaneously.
    """
    # Semaphore = a counting lock.  asyncio.Semaphore(20) means at most 20
    # checks can be active simultaneously.  When a check finishes, it releases
    # its slot and the next waiting check can start.
    sem = asyncio.Semaphore(max_workers)

    # Tell httpx the maximum number of open connections to allow at once
    limits = httpx.Limits(max_connections=max_workers, max_keepalive_connections=max_workers)

    # The User-Agent header tells servers what "browser" is making the request
    headers = {"User-Agent": BROWSER_UA}

    # "async with httpx.AsyncClient(...) as client" creates one shared connection
    # pool for all checks.  Reusing connections (keep-alive) is faster than
    # opening a brand new TCP connection for every single URL.
    async with httpx.AsyncClient(
        headers=headers,
        timeout=httpx.Timeout(timeout),   # applies to every individual request
        limits=limits,
        follow_redirects=True,
    ) as client:
        # Build one coroutine ("task") per unique URL
        tasks = [
            _check_one(client, sem, url, locs, fetch_titles, retry, on_progress)
            for url, locs in url_groups.items()
        ]
        # asyncio.gather() runs ALL tasks concurrently and waits for all to finish.
        # Results come back in the same order as the tasks list.
        return await asyncio.gather(*tasks)


# -----------------------------------------------------------------------------
# check_urls — The public function called by the Streamlit app
# -----------------------------------------------------------------------------

def check_urls(
    url_groups,              # type: Dict[str, List[UrlLocation]]
    timeout=DEFAULT_TIMEOUT,
    max_workers=DEFAULT_MAX_WORKERS,
    fetch_titles=False,
    retry=True,
    on_progress=None,        # type: Optional[Callable]
):
    # type: (...) -> List[CheckResult]
    """
    The only function that Streamlit calls.  It is synchronous (normal Python),
    but internally runs the async checking engine inside a separate thread.

    Why a separate thread?  Streamlit itself has its own async event loop running.
    If we tried to run our async code in the same loop, they would conflict.
    Starting a fresh thread gives us a clean environment for asyncio.run().
    """
    # Define an inner async function that wraps the full async pipeline.
    # We'll pass this to asyncio.run() which creates a brand-new event loop,
    # runs our code inside it until everything finishes, then shuts it down.
    async def _run():
        return await _check_all_async(url_groups, timeout, max_workers, fetch_titles, retry, on_progress)

    # ThreadPoolExecutor(max_workers=1) creates exactly one background thread.
    # pool.submit(asyncio.run, _run()) tells that thread to call asyncio.run(_run()).
    # .result() blocks the main thread here until the background thread is done,
    # then hands back the list of CheckResult objects.
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, _run()).result()
