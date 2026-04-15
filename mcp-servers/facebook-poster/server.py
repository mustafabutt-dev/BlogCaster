"""
Facebook Page Poster MCP Server

FastMCP server that posts formatted content to a Facebook Page.
Provides two tools:
  - validate_token: Check if the Page Access Token is still valid
  - post_to_facebook: Create a post on the Facebook Page

Uses the Facebook Graph API v21.0 with a pre-generated Page Access Token.
"""

import logging
import os

import httpx
from mcp.server.fastmcp import FastMCP

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger("facebook-poster")
logger.setLevel(logging.WARNING)

mcp = FastMCP("facebook-poster")

HTTP_TIMEOUT = 30.0
GRAPH_API_BASE = "https://graph.facebook.com/v21.0"


def _get_page_id() -> str:
    """Read Facebook Page ID from environment variable."""
    page_id = os.environ.get("FACEBOOK_PAGE_ID", "")
    if not page_id:
        raise ValueError("FACEBOOK_PAGE_ID environment variable is not set")
    return page_id


def _get_token() -> str:
    """Read Facebook Page Access Token from environment variable."""
    token = os.environ.get("FACEBOOK_PAGE_ACCESS_TOKEN", "")
    if not token:
        raise ValueError("FACEBOOK_PAGE_ACCESS_TOKEN environment variable is not set")
    return token


@mcp.tool()
async def validate_token() -> bool:
    """Check if the Facebook Page Access Token is still valid.

    Makes a lightweight call to GET /me on the Graph API.

    Returns:
        True if the token is valid, False if expired or invalid.
    """
    logger.info("Validating Facebook Page Access Token")

    try:
        token = _get_token()
    except ValueError as e:
        logger.error(str(e))
        return False

    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            response = await client.get(
                f"{GRAPH_API_BASE}/me",
                params={"access_token": token},
            )

        if response.status_code == 200:
            logger.info("Facebook token is valid")
            return True
        elif response.status_code == 401:
            logger.warning("Facebook token is expired or invalid (401)")
            return False
        elif response.status_code == 403:
            logger.warning("Facebook token has insufficient permissions (403)")
            return False
        else:
            # Graph API returns 400 for invalid tokens with error JSON
            data = response.json() if response.status_code == 400 else {}
            error_msg = data.get("error", {}).get("message", response.text[:200])
            logger.warning(f"Facebook token validation failed: {error_msg}")
            return False

    except httpx.RequestError as e:
        logger.error(f"Network error validating token: {e}")
        return False


@mcp.tool()
async def post_to_facebook(content: str, blog_url: str) -> dict:
    """Post formatted content to the configured Facebook Page.

    Args:
        content: The LLM-formatted Facebook post text
        blog_url: The original blog URL (attached as a link)

    Returns:
        Dict with status ("success" or "failure"), post_id, and error fields.
    """
    logger.info(f"Posting to Facebook Page for blog: {blog_url}")

    if not content or not content.strip():
        logger.error("Empty content provided")
        return {"status": "failure", "post_id": None, "error": "Content is empty"}

    try:
        page_id = _get_page_id()
        token = _get_token()
    except ValueError as e:
        logger.error(str(e))
        return {"status": "failure", "post_id": None, "error": str(e)}

    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            response = await client.post(
                f"{GRAPH_API_BASE}/{page_id}/feed",
                data={
                    "message": content,
                    "link": blog_url,
                    "access_token": token,
                },
            )

            logger.debug(f"Facebook API response status: {response.status_code}")
            logger.debug(f"Facebook API response body: {response.text}")

            if response.status_code == 200:
                data = response.json()
                post_id = data.get("id", "")
                logger.info(f"Facebook post successful: post_id={post_id}")
                return {"status": "success", "post_id": post_id, "error": None}

            # Graph API error responses
            try:
                error_data = response.json().get("error", {})
            except Exception:
                error_data = {}

            error_code = error_data.get("code", 0)
            error_msg = error_data.get("message", response.text[:500])

            if response.status_code == 400 and error_code == 190:
                error = f"Facebook token is expired or invalid: {error_msg}"
                logger.error(error)
                return {"status": "failure", "post_id": None, "error": error}

            if response.status_code == 403 or error_code in (10, 200):
                error = f"Insufficient permissions to post: {error_msg}"
                logger.error(error)
                return {"status": "failure", "post_id": None, "error": error}

            if response.status_code == 429 or error_code == 32:
                error = f"Facebook API rate limit exceeded. Try again later. {error_msg}"
                logger.warning(error)
                return {"status": "failure", "post_id": None, "error": error}

            error = f"Facebook API error: HTTP {response.status_code} — {error_msg}"
            logger.error(error)
            return {"status": "failure", "post_id": None, "error": error}

    except httpx.RequestError as e:
        error = f"Network error posting to Facebook: {e}"
        logger.error(error)
        return {"status": "failure", "post_id": None, "error": error}


if __name__ == "__main__":
    mcp.run(transport="stdio")
