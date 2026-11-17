"""
Pre-share health check for blog post pages.

Finds problems the blog team should fix (broken featured image, missing
link-preview tags, broken images/links in the article). Never blocks sharing —
the orchestrator logs each issue on its own HEALTH_CHECK line for the
BlogCaster dashboard to read.
"""

import asyncio
from urllib.parse import urljoin, urlparse, urlunparse

import httpx
from bs4 import BeautifulSoup

from markdown_converter import find_article_body

TIMEOUT = 10.0
MAX_LINKS = 30
MAX_IMAGES = 30
CONCURRENCY = 8
META_DESC_MIN, META_DESC_MAX = 50, 160

# Status codes that mean "the target is genuinely broken". 401/403/429 and
# similar usually mean a bot block or rate limit, not a dead link — ignored.
_BROKEN_STATUSES = {404, 410} | set(range(500, 600))


def _norm(url: str) -> str:
    p = urlparse(url.strip())
    return urlunparse((p.scheme.lower(), p.netloc.lower(), p.path.rstrip("/").lower(), "", "", ""))


def _meta(soup: BeautifulSoup, *, prop: str = "", name: str = "") -> str:
    tag = soup.find("meta", attrs={"property": prop}) if prop else soup.find("meta", attrs={"name": name})
    return (tag.get("content") or "").strip() if tag else ""


async def _probe(client: httpx.AsyncClient, sem: asyncio.Semaphore, url: str, want_image: bool = False) -> str | None:
    """Return a problem description, or None if the URL is fine (or only bot-blocked)."""
    async with sem:
        try:
            resp = await client.head(url, follow_redirects=True)
            if resp.status_code in (405, 501) or (resp.status_code >= 400 and resp.status_code not in _BROKEN_STATUSES):
                # Some servers reject HEAD — confirm with a GET before judging
                resp = await client.get(url, follow_redirects=True)
        except httpx.TimeoutException:
            return "timed out"
        except httpx.RequestError as e:
            return f"unreachable ({type(e).__name__})"
    if resp.status_code in _BROKEN_STATUSES:
        return f"HTTP {resp.status_code}"
    if want_image and resp.status_code == 200:
        ctype = resp.headers.get("content-type", "")
        if not ctype.startswith("image/"):
            return f"not an image (content-type: {ctype or 'none'})"
    return None


async def check_page_health(html: str, page_url: str, user_agent: str) -> list[dict]:
    """Run all checks. Returns a list of {"type", "detail"} issues (empty = healthy)."""
    soup = BeautifulSoup(html, "html.parser")
    issues: list[dict] = []

    def add(kind: str, detail: str) -> None:
        issues.append({"type": kind, "detail": detail})

    # ── Link-preview metadata (drives LinkedIn / Facebook / Bluesky cards) ──
    og_image = _meta(soup, prop="og:image")
    for prop in ("og:title", "og:description", "og:image"):
        if not _meta(soup, prop=prop):
            add("missing_og_tag", f"{prop} is missing")

    desc = _meta(soup, name="description")
    if not desc:
        add("meta_description", "meta description is missing")
    elif len(desc) < META_DESC_MIN:
        add("meta_description", f"meta description is too short ({len(desc)} chars, aim for {META_DESC_MIN}-{META_DESC_MAX})")
    elif len(desc) > META_DESC_MAX:
        add("meta_description", f"meta description is too long ({len(desc)} chars, aim for {META_DESC_MIN}-{META_DESC_MAX})")

    canonical = soup.find("link", attrs={"rel": "canonical"})
    canonical_href = (canonical.get("href") or "").strip() if canonical else ""
    if not canonical_href:
        add("canonical", "canonical tag is missing")
    elif _norm(urljoin(page_url, canonical_href)) != _norm(page_url):
        add("canonical", f"canonical points elsewhere: {canonical_href}")

    # ── Collect URLs to probe ──
    body = find_article_body(soup)
    images, links = [], []
    if body is not None:
        for img in body.find_all("img"):
            src = img.get("src") or img.get("data-src")
            if src and not src.startswith("data:"):
                images.append(urljoin(page_url, src))
        for a in body.find_all("a", href=True):
            href = a["href"].strip()
            if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
                continue
            links.append(urljoin(page_url, href))
    images = list(dict.fromkeys(images))[:MAX_IMAGES]
    links = [l for l in dict.fromkeys(links) if l not in images][:MAX_LINKS]

    sem = asyncio.Semaphore(CONCURRENCY)
    async with httpx.AsyncClient(timeout=TIMEOUT, headers={"User-Agent": user_agent}) as client:
        tasks = []
        if og_image:
            tasks.append(("featured_image", urljoin(page_url, og_image), True))
        tasks += [("broken_image", u, True) for u in images]
        tasks += [("broken_link", u, False) for u in links]
        results = await asyncio.gather(*(_probe(client, sem, u, img) for _, u, img in tasks))

    for (kind, url, _), problem in zip(tasks, results):
        if problem:
            add(kind, f"{url} — {problem}")

    return issues
