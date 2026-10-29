"""
Mastodon Poster MCP Server

FastMCP server that posts formatted content to a Mastodon account.
Provides two tools:
  - validate_credentials: Check the access token is valid
  - post_to_mastodon: Publish a public status

Uses the Mastodon REST API with a non-expiring access token from
Preferences → Development → New application (scopes: read:accounts,
write:statuses, write:media). The post text must include the blog URL.

With image_url set, the blog's featured image is attached to the post. This
is used because the blogs' og:image tags often 404, so the link card Mastodon
builds from the URL would have no image. Mastodon hides the link card when a
post has media, but the URL in the text stays clickable.
"""

import asyncio
import logging
import os
import uuid

import httpx
from mcp.server.fastmcp import FastMCP

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger("mastodon-poster")
logger.setLevel(logging.WARNING)

mcp = FastMCP("mastodon-poster")

HTTP_TIMEOUT = 30.0
DEFAULT_INSTANCE_URL = "https://mastodon.social"
MAX_POST_LENGTH = 500  # mastodon.social limit; every URL counts as 23 characters
MAX_ALT_TEXT = 1500


def _get_instance_url() -> str:
    """Read the Mastodon server URL (defaults to mastodon.social)."""
    return (os.environ.get("MASTODON_INSTANCE_URL") or DEFAULT_INSTANCE_URL).rstrip("/")


def _get_token() -> str:
    """Read the Mastodon access token from environment variable."""
    token = os.environ.get("MASTODON_ACCESS_TOKEN", "")
    if not token:
        raise ValueError("MASTODON_ACCESS_TOKEN environment variable is not set")
    return token


async def _upload_image(client: httpx.AsyncClient, token: str, image_url: str, alt_text: str) -> str | None:
    """Download the featured image and upload it as a media attachment.

    Returns the media ID, or None if any step fails — the post is still
    created, just without the image (Mastodon then shows its link card).
    """
    try:
        image_response = await client.get(image_url, follow_redirects=True)
        image_response.raise_for_status()
        content_type = image_response.headers.get("content-type", "").split(";")[0]
        if not content_type.startswith("image/"):
            logger.warning(f"Featured image URL is not an image (content-type: {content_type})")
            return None

        filename = image_url.rsplit("/", 1)[-1].split("?")[0] or "image"
        upload = await client.post(
            f"{_get_instance_url()}/api/v2/media",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": (filename, image_response.content, content_type)},
            data={"description": alt_text[:MAX_ALT_TEXT]},
        )
        if upload.status_code not in (200, 202):
            logger.warning(f"Media upload failed: HTTP {upload.status_code} — {upload.text[:200]}")
            return None

        media = upload.json()
        # 202 = still processing; the media can't be attached until it has a url
        for _ in range(10):
            if media.get("url"):
                return media["id"]
            await asyncio.sleep(1)
            check = await client.get(
                f"{_get_instance_url()}/api/v1/media/{media['id']}",
                headers={"Authorization": f"Bearer {token}"},
            )
            media = check.json() if check.status_code in (200, 206) else media
        logger.warning("Media still processing after 10s, posting without image")
        return None

    except (httpx.HTTPError, KeyError, ValueError) as e:
        logger.warning(f"Image upload failed, posting without image: {e}")
        return None


@mcp.tool()
async def validate_credentials() -> bool:
    """Check if the Mastodon access token is valid.

    Calls GET /api/v1/accounts/verify_credentials.

    Returns:
        True if the token is valid, False otherwise.
    """
    try:
        token = _get_token()
    except ValueError as e:
        logger.error(str(e))
        return False

    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            response = await client.get(
                f"{_get_instance_url()}/api/v1/accounts/verify_credentials",
                headers={"Authorization": f"Bearer {token}"},
            )
        if response.status_code == 200:
            return True
        logger.warning(f"Mastodon token validation failed: HTTP {response.status_code} — {response.text[:200]}")
        return False

    except httpx.RequestError as e:
        logger.error(f"Network error validating Mastodon token: {e}")
        return False


@mcp.tool()
async def post_to_mastodon(content: str, blog_url: str, image_url: str = "", image_alt: str = "") -> dict:
    """Publish a public status to the configured Mastodon account.

    Args:
        content: The LLM-formatted post text, including the blog URL
        blog_url: The blog URL (used for logging only — it is already in content)
        image_url: URL of the blog's featured image to attach (optional)
        image_alt: Alt text for the image (e.g. the blog title)

    Returns:
        Dict with status ("success" or "failure"), post_id, url, and error fields.
    """
    logger.info(f"Posting to Mastodon for blog: {blog_url}")

    if not content or not content.strip():
        return {"status": "failure", "post_id": None, "url": None, "error": "Content is empty"}

    try:
        token = _get_token()
    except ValueError as e:
        logger.error(str(e))
        return {"status": "failure", "post_id": None, "url": None, "error": str(e)}

    headers = {
        "Authorization": f"Bearer {token}",
        # Mastodon de-duplicates requests with the same key for an hour,
        # so a retried request can never create a second post
        "Idempotency-Key": str(uuid.uuid4()),
    }
    payload = {"status": content, "visibility": "public", "language": "en"}

    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            if image_url:
                media_id = await _upload_image(client, token, image_url, image_alt or "Featured image of the blog post")
                if media_id:
                    payload["media_ids[]"] = media_id

            response = await client.post(
                f"{_get_instance_url()}/api/v1/statuses", headers=headers, data=payload,
            )

        if response.status_code == 200:
            data = response.json()
            post_id = data.get("id", "")
            post_url = data.get("url", "")
            logger.info(f"Mastodon post successful: {post_url}")
            return {"status": "success", "post_id": post_id, "url": post_url, "error": None}

        try:
            error_msg = response.json().get("error", response.text[:300])
        except ValueError:
            error_msg = response.text[:300]

        if response.status_code == 401:
            error = f"Mastodon token is invalid or revoked: {error_msg}"
        elif response.status_code == 403:
            error = f"Mastodon token lacks write:statuses permission: {error_msg}"
        elif response.status_code == 422:
            error = f"Mastodon rejected the post (e.g. over {MAX_POST_LENGTH} characters): {error_msg}"
        elif response.status_code == 429:
            error = "Mastodon API rate limit exceeded. Try again later."
        else:
            error = f"Mastodon API error: HTTP {response.status_code} — {error_msg}"
        logger.error(error)
        return {"status": "failure", "post_id": None, "url": None, "error": error}

    except httpx.RequestError as e:
        error = f"Network error posting to Mastodon: {e}"
        logger.error(error)
        return {"status": "failure", "post_id": None, "url": None, "error": error}


if __name__ == "__main__":
    mcp.run(transport="stdio")
