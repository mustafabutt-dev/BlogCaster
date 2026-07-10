"""
LinkedIn Poster MCP Server

FastMCP server that posts formatted content to a LinkedIn personal profile.
Provides two tools:
  - post_to_linkedin: Create a text post on personal profile
  - validate_token: Check if the OAuth access token is still valid

Uses the LinkedIn REST API with a pre-generated OAuth 2.0 access token.
"""

import logging
import os

import httpx
from mcp.server.fastmcp import FastMCP

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger("linkedin-poster")
logger.setLevel(logging.WARNING)

mcp = FastMCP("linkedin-poster")

HTTP_TIMEOUT = 30.0
LINKEDIN_API_BASE = "https://api.linkedin.com"

# Cache for member ID to avoid repeated /userinfo calls
_cached_member_id: str | None = None


def _get_token() -> str:
    """Read LinkedIn access token from environment variable."""
    token = os.environ.get("LINKEDIN_ACCESS_TOKEN", "")
    if not token:
        raise ValueError("LINKEDIN_ACCESS_TOKEN environment variable is not set")
    return token


def _auth_headers(token: str) -> dict:
    """Build common authentication headers."""
    return {
        "Authorization": f"Bearer {token}",
    }


async def _get_member_id(client: httpx.AsyncClient, token: str) -> str:
    """Fetch the authenticated user's member ID. Caches after first call."""
    global _cached_member_id
    if _cached_member_id:
        return _cached_member_id

    response = await client.get(
        f"{LINKEDIN_API_BASE}/v2/userinfo",
        headers=_auth_headers(token),
    )
    response.raise_for_status()
    data = response.json()
    member_id = data.get("sub", "")
    if not member_id:
        raise ValueError("Could not extract member ID (sub) from /v2/userinfo response")

    _cached_member_id = member_id
    logger.info(f"Fetched member ID: {member_id}")
    return member_id


@mcp.tool()
async def validate_token() -> bool:
    """Check if the LinkedIn OAuth access token is still valid.

    Makes a lightweight call to the LinkedIn /v2/userinfo endpoint.

    Returns:
        True if the token is valid, False if expired or invalid.
    """
    logger.info("Validating LinkedIn access token")

    try:
        token = _get_token()
    except ValueError as e:
        logger.error(str(e))
        return False

    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            response = await client.get(
                f"{LINKEDIN_API_BASE}/v2/userinfo",
                headers=_auth_headers(token),
            )

        if response.status_code == 200:
            logger.info("LinkedIn token is valid")
            return True
        elif response.status_code == 401:
            logger.warning("LinkedIn token is expired or invalid (401)")
            return False
        elif response.status_code == 403:
            logger.warning("LinkedIn token has insufficient permissions (403)")
            return False
        else:
            logger.warning(f"Unexpected status from LinkedIn: {response.status_code}")
            logger.debug(f"Response body: {response.text}")
            return False

    except httpx.RequestError as e:
        logger.error(f"Network error validating token: {e}")
        return False


def _rest_headers(token: str) -> dict:
    """Headers for LinkedIn versioned REST API calls."""
    return {
        **_auth_headers(token),
        "Content-Type": "application/json",
        "LinkedIn-Version": "202604",
        "X-Restli-Protocol-Version": "2.0.0",
    }


async def _upload_thumbnail(
    client: httpx.AsyncClient, token: str, member_id: str, image_url: str
) -> str | None:
    """Download the blog's featured image and upload it to LinkedIn.

    LinkedIn does not scrape article URLs for previews — the thumbnail must be
    uploaded via the Images API and referenced by URN in the article block.

    Returns the image URN (urn:li:image:...) or None if any step fails —
    the post is still created, just without a thumbnail.
    """
    try:
        image_response = await client.get(image_url, follow_redirects=True)
        image_response.raise_for_status()
        content_type = image_response.headers.get("content-type", "")
        if not content_type.startswith("image/"):
            logger.warning(f"Featured image URL is not an image (content-type: {content_type})")
            return None

        init_response = await client.post(
            f"{LINKEDIN_API_BASE}/rest/images?action=initializeUpload",
            json={"initializeUploadRequest": {"owner": f"urn:li:person:{member_id}"}},
            headers=_rest_headers(token),
        )
        init_response.raise_for_status()
        value = init_response.json().get("value", {})
        upload_url = value.get("uploadUrl", "")
        image_urn = value.get("image", "")
        if not upload_url or not image_urn:
            logger.warning("Images API initializeUpload response missing uploadUrl/image")
            return None

        upload_response = await client.put(
            upload_url,
            content=image_response.content,
            headers={**_auth_headers(token), "Content-Type": "application/octet-stream"},
        )
        upload_response.raise_for_status()
        logger.info(f"Uploaded article thumbnail: {image_urn}")
        return image_urn

    except (httpx.HTTPStatusError, httpx.RequestError) as e:
        logger.warning(f"Thumbnail upload failed, posting without image: {e}")
        return None


@mcp.tool()
async def post_to_linkedin(
    content: str,
    blog_url: str,
    article_title: str = "",
    article_description: str = "",
    image_url: str = "",
) -> dict:
    """Post formatted content to the authenticated user's LinkedIn personal profile.

    When article_title is provided, the post carries a clickable article card
    (link preview) pointing at blog_url, with an optional thumbnail uploaded
    from image_url. Otherwise a plain text post is created.

    Args:
        content: The LLM-formatted LinkedIn post text
        blog_url: The blog URL (article card target, or just logging for text posts)
        article_title: Blog title shown on the article card (enables article mode)
        article_description: Short description shown on the article card
        image_url: URL of the blog's featured image for the card thumbnail

    Returns:
        Dict with status ("success" or "failure"), post_id, and error fields.
    """
    logger.info(f"Posting to LinkedIn for blog: {blog_url}")

    # Validate content
    if not content or not content.strip():
        logger.error("Empty content provided")
        return {"status": "failure", "post_id": None, "error": "Content is empty"}

    try:
        token = _get_token()
    except ValueError as e:
        logger.error(str(e))
        return {"status": "failure", "post_id": None, "error": str(e)}

    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            # Get member ID for the author URN
            member_id = await _get_member_id(client, token)

            # Create the post
            post_body = {
                "author": f"urn:li:person:{member_id}",
                "lifecycleState": "PUBLISHED",
                "visibility": "PUBLIC",
                "commentary": content,
                "distribution": {
                    "feedDistribution": "MAIN_FEED",
                    "targetEntities": [],
                    "thirdPartyDistributionChannels": [],
                },
            }

            if article_title:
                article = {
                    "source": blog_url,
                    "title": article_title[:400],
                }
                if article_description:
                    article["description"] = article_description[:256]
                if image_url:
                    thumbnail_urn = await _upload_thumbnail(client, token, member_id, image_url)
                    if thumbnail_urn:
                        article["thumbnail"] = thumbnail_urn
                post_body["content"] = {"article": article}

            response = await client.post(
                f"{LINKEDIN_API_BASE}/rest/posts",
                json=post_body,
                headers=_rest_headers(token),
            )

            logger.debug(f"LinkedIn API response status: {response.status_code}")
            logger.debug(f"LinkedIn API response body: {response.text}")

            if response.status_code == 201:
                post_id = response.headers.get("x-restli-id", "")
                logger.info(f"LinkedIn post successful: post_id={post_id}")
                return {"status": "success", "post_id": post_id, "error": None}

            elif response.status_code == 401:
                error = "LinkedIn token is expired or invalid (401)"
                logger.error(error)
                return {"status": "failure", "post_id": None, "error": error}

            elif response.status_code == 403:
                error = "Insufficient permissions to post (403). Ensure token has w_member_social scope."
                logger.error(error)
                return {"status": "failure", "post_id": None, "error": error}

            elif response.status_code == 429:
                error = "LinkedIn API rate limit exceeded (429). Try again later."
                logger.warning(error)
                return {"status": "failure", "post_id": None, "error": error}

            else:
                error = f"LinkedIn API error: HTTP {response.status_code} — {response.text[:500]}"
                logger.error(error)
                return {"status": "failure", "post_id": None, "error": error}

    except httpx.HTTPStatusError as e:
        status_code = e.response.status_code
        if status_code == 401:
            error = "LinkedIn token is expired or invalid (401)"
        elif status_code == 403:
            error = "Insufficient permissions (403). Ensure token has w_member_social scope."
        else:
            error = f"LinkedIn API error: HTTP {status_code}"
        logger.error(error)
        return {"status": "failure", "post_id": None, "error": error}
    except httpx.RequestError as e:
        error = f"Network error posting to LinkedIn: {e}"
        logger.error(error)
        return {"status": "failure", "post_id": None, "error": error}
    except ValueError as e:
        error = f"Error getting member ID: {e}"
        logger.error(error)
        return {"status": "failure", "post_id": None, "error": error}


if __name__ == "__main__":
    mcp.run(transport="stdio")
