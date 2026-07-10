"""
RSS Fetcher MCP Server

FastMCP server that fetches and parses Hugo RSS feeds and individual blog posts.
Provides three tools:
  - fetch_rss: Full feed parse with metadata
  - get_latest_posts: Clean list of recent posts
  - fetch_post_by_url: Single post fetch by URL

All HTML tags are stripped from returned content.
"""

import logging
from datetime import datetime
from time import mktime
from typing import Any
from urllib.parse import urljoin

import feedparser
import httpx
from bs4 import BeautifulSoup
from mcp.server.fastmcp import FastMCP

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger("rss-fetcher")
logger.setLevel(logging.WARNING)

mcp = FastMCP("rss-fetcher")

HTTP_TIMEOUT = 30.0
USER_AGENT = "Mozilla/5.0 (compatible; BlogCaster/1.0; +https://github.com/mustafabutt/BlogCaster)"


def strip_html(html: str) -> str:
    """Strip all HTML tags and return clean plain text."""
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    return soup.get_text(separator=" ", strip=True)


def parse_published_date(entry: dict) -> str:
    """Extract and format the published date from a feed entry."""
    date_fields = ["published_parsed", "updated_parsed"]
    for field in date_fields:
        parsed = entry.get(field)
        if parsed:
            try:
                return datetime.fromtimestamp(mktime(parsed)).strftime("%Y-%m-%d %H:%M:%S")
            except (ValueError, OverflowError, OSError):
                continue

    # Fallback to raw string fields
    for field in ["published", "updated"]:
        raw = entry.get(field)
        if raw:
            return raw

    return ""


def parse_entry(entry: dict) -> dict:
    """Parse a single feed entry into a clean post dict."""
    # Get summary from content or summary field
    summary = ""
    if entry.get("content"):
        summary = entry["content"][0].get("value", "")
    elif entry.get("summary"):
        summary = entry.get("summary", "")
    elif entry.get("description"):
        summary = entry.get("description", "")

    return {
        "title": entry.get("title", "Unknown"),
        "link": entry.get("link", ""),
        "summary": strip_html(summary),
        "published_date": parse_published_date(entry),
    }


async def fetch_feed_data(platform_url: str) -> dict[str, Any]:
    """Fetch and parse an RSS feed URL. Returns parsed feed or error dict."""
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            response = await client.get(
                platform_url,
                headers={"User-Agent": USER_AGENT},
                follow_redirects=True,
            )
            response.raise_for_status()
    except httpx.HTTPStatusError as e:
        return {"error": f"HTTP {e.response.status_code} fetching {platform_url}", "status": "failed"}
    except httpx.RequestError as e:
        return {"error": f"Network error fetching {platform_url}: {e}", "status": "failed"}

    feed = feedparser.parse(response.text)

    if feed.bozo and not feed.entries:
        return {"error": f"Malformed feed at {platform_url}: {feed.bozo_exception}", "status": "failed"}

    return {"feed": feed, "status": "ok"}


@mcp.tool()
async def fetch_rss(platform_url: str) -> dict:
    """Fetch and parse a Hugo RSS feed. Returns full feed metadata and list of posts.

    Args:
        platform_url: The RSS feed URL to fetch (e.g. https://blog.aspose.com/feed)

    Returns:
        Dict with feed_title, feed_link, post_count, and posts list.
        Each post has title, link, summary (HTML-stripped), and published_date.
        On error, returns dict with error message and status="failed".
    """
    logger.info(f"Fetching RSS feed: {platform_url}")
    result = await fetch_feed_data(platform_url)

    if result.get("status") == "failed":
        logger.error(f"Feed fetch failed: {result['error']}")
        return result

    feed = result["feed"]
    posts = [parse_entry(entry) for entry in feed.entries]

    return {
        "status": "ok",
        "feed_title": feed.feed.get("title", "Unknown"),
        "feed_link": feed.feed.get("link", ""),
        "post_count": len(posts),
        "posts": posts,
    }


@mcp.tool()
async def get_latest_posts(platform_url: str, limit: int = 10) -> list:
    """Fetch RSS feed and return a clean list of recent posts in feed order (newest first).

    Args:
        platform_url: The RSS feed URL to fetch
        limit: Maximum number of posts to return (default 10, 0 = all)

    Returns:
        List of post dicts with title, link, summary, published_date.
        Preserves the feed's natural order (newest first). Returns empty list on error.
    """
    logger.info(f"Getting latest {limit} posts from: {platform_url}")
    result = await fetch_feed_data(platform_url)

    if result.get("status") == "failed":
        logger.error(f"Feed fetch failed: {result['error']}")
        return []

    feed = result["feed"]
    posts = [parse_entry(entry) for entry in feed.entries]

    # Feed's natural order is already newest-first (standard for RSS/Atom).
    # Do NOT re-sort: entries with unparseable dates (e.g. year 0001) produce
    # raw date strings that break string-based sort ordering.

    if limit > 0:
        return posts[:limit]
    return posts


@mcp.tool()
async def fetch_post_by_url(url: str) -> dict:
    """Fetch a single blog post by its URL and extract content.

    Args:
        url: The direct URL of the blog post

    Returns:
        Dict with title, content (HTML-stripped), published_date, author, and url.
        On error, returns dict with error message and status="failed".
    """
    logger.info(f"Fetching post by URL: {url}")

    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            response = await client.get(
                url,
                headers={"User-Agent": USER_AGENT},
                follow_redirects=True,
            )
            response.raise_for_status()
    except httpx.HTTPStatusError as e:
        error = f"HTTP {e.response.status_code} fetching {url}"
        logger.error(error)
        return {"error": error, "status": "failed"}
    except httpx.RequestError as e:
        error = f"Network error fetching {url}: {e}"
        logger.error(error)
        return {"error": error, "status": "failed"}

    soup = BeautifulSoup(response.text, "html.parser")

    # Extract title
    title = "Unknown"
    title_tag = soup.find("h1")
    if title_tag:
        title = title_tag.get_text(strip=True)
    elif soup.find("title"):
        title = soup.find("title").get_text(strip=True)

    # Extract content — try Hugo-standard selectors
    content = ""
    content_element = None
    content_selectors = [
        ("article", {}),
        ("div", {"class": "content"}),
        ("div", {"class": "post-content"}),
        ("div", {"class": "entry-content"}),
        ("div", {"class": "article-content"}),
        ("main", {}),
    ]
    for tag, attrs in content_selectors:
        element = soup.find(tag, attrs) if attrs else soup.find(tag)
        if element:
            content = element.get_text(separator=" ", strip=True)
            content_element = element
            break

    # Fallback: use meta description
    if not content:
        meta_desc = soup.find("meta", attrs={"name": "description"})
        if meta_desc and meta_desc.get("content"):
            content = meta_desc["content"]

    # Extract published date
    published_date = ""
    time_tag = soup.find("time")
    if time_tag:
        published_date = time_tag.get("datetime", time_tag.get_text(strip=True))
    else:
        meta_date = soup.find("meta", attrs={"property": "article:published_time"})
        if meta_date and meta_date.get("content"):
            published_date = meta_date["content"]

    # Extract author
    author = ""
    author_meta = soup.find("meta", attrs={"name": "author"})
    if author_meta and author_meta.get("content"):
        author = author_meta["content"]
    else:
        author_tag = soup.find("a", attrs={"rel": "author"})
        if author_tag:
            author = author_tag.get_text(strip=True)

    # Extract featured image: og:image / twitter:image, verified with a HEAD
    # request — some Hugo themes emit og:image URLs that 404. Fall back to the
    # first image inside the article body.
    image_url = ""
    candidates = []
    og_image = soup.find("meta", attrs={"property": "og:image"})
    if og_image and og_image.get("content"):
        candidates.append(og_image["content"])
    tw_image = soup.find("meta", attrs={"name": "twitter:image"})
    if tw_image and tw_image.get("content"):
        candidates.append(tw_image["content"])
    if content_element:
        body_img = content_element.find("img")
        if body_img and body_img.get("src"):
            candidates.append(urljoin(url, body_img["src"]))

    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        for candidate in candidates:
            try:
                head = await client.head(
                    candidate,
                    headers={"User-Agent": USER_AGENT},
                    follow_redirects=True,
                )
                if head.status_code == 200 and head.headers.get("content-type", "").startswith("image/"):
                    image_url = candidate
                    break
                logger.warning(f"Skipping broken featured image candidate: {candidate} (HTTP {head.status_code})")
            except httpx.RequestError as e:
                logger.warning(f"Error checking featured image candidate {candidate}: {e}")

    return {
        "status": "ok",
        "title": title,
        "content": content,
        "published_date": published_date,
        "author": author,
        "url": url,
        "image_url": image_url,
    }


if __name__ == "__main__":
    mcp.run(transport="stdio")
