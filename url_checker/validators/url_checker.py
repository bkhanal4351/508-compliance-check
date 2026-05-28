import asyncio
import concurrent.futures
import logging
import re
import time
from collections import defaultdict
from typing import Callable, Dict, List, Optional, Tuple

import httpx

from extractors.base import CheckResult, ExtractedUrl, UrlLocation
from utils.constants import (
    BODY_PREVIEW_BYTES,
    BROWSER_UA,
    DEFAULT_MAX_WORKERS,
    DEFAULT_TIMEOUT,
    MAX_RETRY_AFTER_SECS,
)
from utils.url_utils import classify_skip_reason, is_epa_internal, normalize_url
from validators.status_classifier import classify_url_result
from validators.wayback import fetch_wayback

logger = logging.getLogger(__name__)

_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)


def group_by_url(extracted):
    # type: (List[ExtractedUrl]) -> Dict[str, List[UrlLocation]]
    """Deduplicate URLs and collect all locations for each unique URL."""
    groups = defaultdict(list)  # type: Dict[str, List[UrlLocation]]
    for e in extracted:
        key = normalize_url(e.url)
        groups[key].append(UrlLocation(
            source_file=e.source_file,
            location=e.location,
            context=e.context,
            link_type=e.link_type,
        ))

    canonical = {}  # type: Dict[str, List[UrlLocation]]
    seen_norm = {}  # type: Dict[str, str]
    for e in extracted:
        norm = normalize_url(e.url)
        if norm not in seen_norm:
            seen_norm[norm] = e.url
            canonical[e.url] = groups[norm]
    return canonical


async def _check_one(client, sem, url, locations, fetch_titles, retry, on_progress):
    skip_reason = classify_skip_reason(url)
    if skip_reason:
        result = CheckResult(
            url=url,
            final_url=None,
            status_code=None,
            tier="Skipped",
            redirect_count=0,
            redirect_chain=[],
            response_time_ms=0.0,
            error_type=None,
            reason=skip_reason,
            page_title=None,
            is_epa_internal=is_epa_internal(url),
            locations=locations,
        )
        if on_progress:
            on_progress(url, result)
        return result

    async with sem:
        result = await _do_request(client, url, locations, fetch_titles, retries=1 if retry else 0)

    # For Dead URLs, look up the most recent Wayback Machine snapshot.
    # Done outside the semaphore so wayback calls don't consume concurrency slots.
    if result.tier == "Dead":
        snap_url, snap_date = await fetch_wayback(client, url)
        result.wayback_url = snap_url
        result.wayback_snapshot_date = snap_date

    if on_progress:
        on_progress(url, result)
    return result


async def _do_request(client, url, locations, fetch_titles, retries):
    start = time.monotonic()
    try:
        body_preview = b""
        redirect_chain = []  # type: List[Tuple[int, str]]
        status_code = None   # type: Optional[int]
        final_url = url
        page_title = None    # type: Optional[str]
        retry_after = None   # type: Optional[int]

        async with client.stream("GET", url, follow_redirects=True) as resp:
            redirect_chain = [(r.status_code, str(r.url)) for r in resp.history]
            status_code = resp.status_code
            final_url = str(resp.url)
            retry_after_hdr = resp.headers.get("Retry-After")

            async for chunk in resp.aiter_bytes(chunk_size=1024):
                body_preview += chunk
                if len(body_preview) >= BODY_PREVIEW_BYTES:
                    break

            if fetch_titles and status_code == 200:
                text = body_preview.decode("utf-8", errors="replace")
                m = _TITLE_RE.search(text)
                if m:
                    page_title = m.group(1).strip()[:200]

            if retry_after_hdr:
                try:
                    retry_after = min(int(retry_after_hdr), MAX_RETRY_AFTER_SECS)
                except ValueError:
                    retry_after = 1

        # Retry on 429 or 5xx
        if retries > 0 and status_code is not None and (status_code == 429 or status_code >= 500):
            wait = retry_after if retry_after else 1
            await asyncio.sleep(wait)
            return await _do_request(client, url, locations, fetch_titles, retries - 1)

        elapsed_ms = (time.monotonic() - start) * 1000
        tier, reason = classify_url_result(url, status_code, final_url, redirect_chain, body_preview, None)

        return CheckResult(
            url=url,
            final_url=final_url if final_url != url else None,
            status_code=status_code,
            tier=tier,
            redirect_count=len(redirect_chain),
            redirect_chain=redirect_chain,
            response_time_ms=round(elapsed_ms, 1),
            error_type=None,
            reason=reason,
            page_title=page_title,
            is_epa_internal=is_epa_internal(url),
            locations=locations,
        )

    except httpx.TimeoutException:
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
        if retries > 0:
            await asyncio.sleep(1)
            return await _do_request(client, url, locations, fetch_titles, retries - 1)
        elapsed_ms = (time.monotonic() - start) * 1000
        err_str = str(e).lower()
        if "ssl" in err_str or "certificate" in err_str or "tls" in err_str:
            error_type = "ssl"
        elif any(k in err_str for k in ("name", "resolve", "nodename", "getaddrinfo")):
            error_type = "dns"
        else:
            error_type = "connection_refused"
        tier, reason = classify_url_result(url, None, None, [], b"", error_type)
        return CheckResult(
            url=url, final_url=None, status_code=None, tier=tier,
            redirect_count=0, redirect_chain=[],
            response_time_ms=round(elapsed_ms, 1),
            error_type=error_type, reason=reason,
            page_title=None, is_epa_internal=is_epa_internal(url), locations=locations,
        )

    except Exception as e:
        elapsed_ms = (time.monotonic() - start) * 1000
        return CheckResult(
            url=url, final_url=None, status_code=None, tier="Dead",
            redirect_count=0, redirect_chain=[],
            response_time_ms=round(elapsed_ms, 1),
            error_type="unknown", reason=str(e)[:200],
            page_title=None, is_epa_internal=is_epa_internal(url), locations=locations,
        )


async def _check_all_async(url_groups, timeout, max_workers, fetch_titles, retry, on_progress):
    sem = asyncio.Semaphore(max_workers)
    limits = httpx.Limits(max_connections=max_workers, max_keepalive_connections=max_workers)
    headers = {"User-Agent": BROWSER_UA}

    async with httpx.AsyncClient(
        headers=headers,
        timeout=httpx.Timeout(timeout),
        limits=limits,
        follow_redirects=True,
    ) as client:
        tasks = [
            _check_one(client, sem, url, locs, fetch_titles, retry, on_progress)
            for url, locs in url_groups.items()
        ]
        return await asyncio.gather(*tasks)


def check_urls(
    url_groups,             # type: Dict[str, List[UrlLocation]]
    timeout=DEFAULT_TIMEOUT,
    max_workers=DEFAULT_MAX_WORKERS,
    fetch_titles=False,
    retry=True,
    on_progress=None,       # type: Optional[Callable]
):
    # type: (...) -> List[CheckResult]
    """
    Synchronous entry point for Streamlit. Runs async checks in a dedicated thread
    to avoid event-loop conflicts with Streamlit's runtime.
    """
    async def _run():
        return await _check_all_async(url_groups, timeout, max_workers, fetch_titles, retry, on_progress)

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, _run()).result()
