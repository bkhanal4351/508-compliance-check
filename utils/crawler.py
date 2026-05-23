import logging
import time
from collections import deque
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import requests

logger = logging.getLogger(__name__)


def _same_scope(start: str, candidate: str) -> bool:
    s = urlparse(start)
    c = urlparse(candidate)
    if s.scheme != c.scheme or s.netloc != c.netloc:
        return False
    # candidate path must start with start path prefix
    start_path = s.path.rstrip("/") + "/"
    cand_path  = c.path if c.path.endswith("/") else c.path + "/"
    return cand_path.startswith(start_path) or c.path == s.path


def _load_robots(base_url: str) -> RobotFileParser:
    rp = RobotFileParser()
    # file:// URLs have no robots.txt; allow everything
    if urlparse(base_url).scheme == "file":
        rp.allow_all = True
        return rp
    robots_url = urljoin(base_url, "/robots.txt")
    try:
        rp.set_url(robots_url)
        rp.read()
    except Exception:
        rp.allow_all = True  # permissive on failure
    return rp


def discover_urls(start_url: str, max_depth: int, max_pages: int) -> list[str]:
    visited: set[str] = set()
    queue: deque[tuple[str, int]] = deque([(start_url, 0)])
    result: list[str] = []

    rp = _load_robots(start_url)

    while queue and len(result) < max_pages:
        url, depth = queue.popleft()
        # Normalise fragment away
        clean = urlparse(url)._replace(fragment="").geturl()
        if clean in visited:
            continue
        visited.add(clean)

        if not rp.can_fetch("*", clean):
            logger.info("robots.txt disallows %s", clean)
            continue

        result.append(clean)
        logger.info("Discovered %s (depth=%d)", clean, depth)

        if depth >= max_depth:
            continue

        try:
            resp = requests.get(clean, timeout=10, headers={"User-Agent": "508-Scanner/1.0"})
            resp.raise_for_status()
        except Exception as e:
            logger.warning("Could not fetch %s: %s", clean, e)
            continue

        ct = resp.headers.get("Content-Type", "")
        if "text/html" not in ct:
            continue

        from bs4 import BeautifulSoup
        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup.find_all("a", href=True):
            href = tag["href"].strip()
            if href.startswith(("mailto:", "javascript:", "#", "tel:")):
                continue
            abs_url = urljoin(clean, href)
            abs_clean = urlparse(abs_url)._replace(fragment="").geturl()
            if abs_clean not in visited and _same_scope(start_url, abs_clean):
                queue.append((abs_clean, depth + 1))

        time.sleep(0.2)  # polite crawl delay

    return result
