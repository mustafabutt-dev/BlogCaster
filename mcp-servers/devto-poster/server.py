"""
Dev.to Poster MCP Server

FastMCP server that publishes articles to Dev.to via the Forem REST API.
Provides two tools:
  - validate_credentials: Verify the API key is valid
  - post_to_devto: Publish a markdown article to a Dev.to organization
"""

import logging
import os

import httpx
from mcp.server.fastmcp import FastMCP

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger("devto-poster")
logger.setLevel(logging.WARNING)

mcp = FastMCP("devto-poster")

DEVTO_API_BASE = "https://dev.to/api"


def _get_api_key() -> str:
    api_key = os.environ.get("DEVTO_API_KEY", "")
    if not api_key:
        raise ValueError("DEVTO_API_KEY is not set")
    return api_key


@mcp.tool()
def validate_credentials() -> bool:
    """Check if the Dev.to API key is valid.

    Makes a lightweight call to GET /api/users/me.

    Returns:
        True if the API key is valid, False otherwise.
    """
    logger.info("Validating Dev.to credentials")

    try:
        api_key = _get_api_key()
    except ValueError as e:
        logger.error(str(e))
        return False

    try:
        resp = httpx.get(
            f"{DEVTO_API_BASE}/users/me",
            headers={"api-key": api_key},
            timeout=15,
        )
        if resp.status_code == 200:
            username = resp.json().get("username", "")
            logger.info(f"Dev.to credentials valid — user: @{username}")
            return True
        logger.warning(f"Dev.to credentials invalid: HTTP {resp.status_code}")
        return False
    except httpx.RequestError as e:
        logger.error(f"Network error validating Dev.to credentials: {e}")
        return False


@mcp.tool()
def post_to_devto(
    title: str,
    body_markdown: str,
    canonical_url: str,
    tags: list,
    org_id: int | None = None,
) -> dict:
    """Publish a markdown article to Dev.to.

    Args:
        title: Article title
        body_markdown: Article body in Markdown format
        canonical_url: Original blog URL (set as canonical for SEO)
        tags: List of up to 4 tags (lowercase, no spaces)
        org_id: Dev.to organization ID to publish under (optional)

    Returns:
        Dict with status ("success" or "failure"), post_id, url, and error fields.
    """
    logger.info(f"Posting to Dev.to: {title!r}")

    if not title or not title.strip():
        return {"status": "failure", "post_id": None, "url": None, "error": "Title is empty"}

    if not body_markdown or not body_markdown.strip():
        return {"status": "failure", "post_id": None, "url": None, "error": "Body markdown is empty"}

    try:
        api_key = _get_api_key()
    except ValueError as e:
        return {"status": "failure", "post_id": None, "url": None, "error": str(e)}

    article_payload: dict = {
        "title": title,
        "body_markdown": body_markdown,
        "published": True,
        "canonical_url": canonical_url,
        "tags": tags[:4],
    }
    if org_id:
        article_payload["organization_id"] = org_id

    try:
        resp = httpx.post(
            f"{DEVTO_API_BASE}/articles",
            json={"article": article_payload},
            headers={
                "api-key": api_key,
                "Content-Type": "application/json",
            },
            timeout=30,
        )

        if resp.status_code == 201:
            data = resp.json()
            post_id = str(data.get("id", ""))
            url = data.get("url", "")
            logger.info(f"Dev.to post successful: post_id={post_id} url={url}")
            return {"status": "success", "post_id": post_id, "url": url, "error": None}

        if resp.status_code == 401:
            error = "Dev.to API key is invalid or expired (401)"
            logger.error(error)
            return {"status": "failure", "post_id": None, "url": None, "error": error}

        if resp.status_code == 422:
            error = f"Dev.to rejected the article (422): {resp.text[:300]}"
            logger.error(error)
            return {"status": "failure", "post_id": None, "url": None, "error": error}

        if resp.status_code == 429:
            error = "Dev.to API rate limit exceeded (429). Try again later."
            logger.warning(error)
            return {"status": "failure", "post_id": None, "url": None, "error": error}

        error = f"Dev.to API error HTTP {resp.status_code}: {resp.text[:200]}"
        logger.error(error)
        return {"status": "failure", "post_id": None, "url": None, "error": error}

    except httpx.RequestError as e:
        error = f"Network error posting to Dev.to: {e}"
        logger.error(error)
        return {"status": "failure", "post_id": None, "url": None, "error": error}


if __name__ == "__main__":
    mcp.run(transport="stdio")
