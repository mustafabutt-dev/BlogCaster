"""
Bluesky Poster MCP Server

FastMCP server that posts formatted content to a Bluesky account.
Provides two tools:
  - validate_credentials: Check the handle + app password can log in
  - post_to_bluesky: Create a post with a link card (title/description/thumbnail)

Uses the AT Protocol XRPC API on bsky.social with an app password
(Settings → Privacy and security → App passwords), never the account password.
"""

import logging
import os
import re
from datetime import datetime, timezone

import httpx
from mcp.server.fastmcp import FastMCP

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger("bluesky-poster")
logger.setLevel(logging.WARNING)

mcp = FastMCP("bluesky-poster")

HTTP_TIMEOUT = 30.0
XRPC_BASE = "https://bsky.social/xrpc"
MAX_POST_LENGTH = 300  # Bluesky limit, counted in graphemes
MAX_THUMB_BYTES = 1_000_000  # uploadBlob rejects images over ~1 MB
MAX_CARD_DESCRIPTION = 300

# Hashtags: "#" preceded by start/whitespace, not purely numeric
_HASHTAG_RE = re.compile(r"(?:^|\s)(#[^\d\s#][^\s#]*)")
_URL_RE = re.compile(r"https?://[^\s]+")


def _get_credentials() -> tuple[str, str]:
    """Read Bluesky handle and app password from environment variables."""
    handle = os.environ.get("BLUESKY_HANDLE", "")
    password = os.environ.get("BLUESKY_APP_PASSWORD", "")
    if not handle or not password:
        raise ValueError("BLUESKY_HANDLE / BLUESKY_APP_PASSWORD environment variables are not set")
    return handle, password


async def _create_session(client: httpx.AsyncClient) -> dict:
    """Log in and return the session (accessJwt, did, handle).

    Raises ValueError with a readable message on auth failure.
    """
    handle, password = _get_credentials()
    response = await client.post(
        f"{XRPC_BASE}/com.atproto.server.createSession",
        json={"identifier": handle, "password": password},
    )
    if response.status_code == 200:
        return response.json()
    if response.status_code == 401:
        raise ValueError("Bluesky login failed — handle or app password is invalid (401)")
    if response.status_code == 429:
        raise ValueError("Bluesky login rate limit exceeded (429). Try again later.")
    raise ValueError(f"Bluesky login failed: HTTP {response.status_code} — {response.text[:200]}")


def _build_facets(text: str) -> list:
    """Build rich-text facets so hashtags and URLs are clickable.

    Bluesky does not auto-detect links or tags — each needs a facet with
    UTF-8 byte offsets into the post text.
    """
    facets = []

    def byte_range(start: int, end: int) -> dict:
        return {
            "byteStart": len(text[:start].encode("utf-8")),
            "byteEnd": len(text[:end].encode("utf-8")),
        }

    for match in _URL_RE.finditer(text):
        url = match.group(0).rstrip(".,;:!?)")
        facets.append({
            "index": byte_range(match.start(), match.start() + len(url)),
            "features": [{"$type": "app.bsky.richtext.facet#link", "uri": url}],
        })

    for match in _HASHTAG_RE.finditer(text):
        tag = match.group(1).rstrip(".,;:!?)")
        start = match.start(1)
        facets.append({
            "index": byte_range(start, start + len(tag)),
            "features": [{"$type": "app.bsky.richtext.facet#tag", "tag": tag[1:]}],
        })

    return facets


async def _upload_thumbnail(client: httpx.AsyncClient, access_jwt: str, image_url: str) -> dict | None:
    """Download the blog's featured image and upload it as a blob.

    Returns the blob reference, or None if any step fails — the post is
    still created, just with a card that has no thumbnail.
    """
    try:
        image_response = await client.get(image_url, follow_redirects=True)
        image_response.raise_for_status()
        content_type = image_response.headers.get("content-type", "").split(";")[0]
        if not content_type.startswith("image/"):
            logger.warning(f"Featured image URL is not an image (content-type: {content_type})")
            return None
        if len(image_response.content) > MAX_THUMB_BYTES:
            logger.warning(f"Featured image too large for Bluesky ({len(image_response.content)} bytes)")
            return None

        upload = await client.post(
            f"{XRPC_BASE}/com.atproto.repo.uploadBlob",
            content=image_response.content,
            headers={"Authorization": f"Bearer {access_jwt}", "Content-Type": content_type},
        )
        upload.raise_for_status()
        return upload.json()["blob"]

    except (httpx.HTTPError, KeyError) as e:
        logger.warning(f"Thumbnail upload failed, posting without image: {e}")
        return None


@mcp.tool()
async def validate_credentials() -> bool:
    """Check if the Bluesky handle and app password can log in.

    Returns:
        True if login succeeds, False otherwise.
    """
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            await _create_session(client)
        return True
    except ValueError as e:
        logger.warning(str(e))
        return False
    except httpx.RequestError as e:
        logger.error(f"Network error validating Bluesky credentials: {e}")
        return False


@mcp.tool()
async def post_to_bluesky(
    content: str,
    blog_url: str,
    article_title: str = "",
    article_description: str = "",
    image_url: str = "",
) -> dict:
    """Post formatted content to the configured Bluesky account.

    The post carries an external link card (title, description, thumbnail)
    pointing at blog_url, so the text itself does not need the URL.

    Args:
        content: The LLM-formatted post text (max 300 characters)
        blog_url: The blog URL the link card points at (may carry UTM params)
        article_title: Title shown on the link card
        article_description: Description shown on the link card
        image_url: URL of the blog's featured image for the card thumbnail

    Returns:
        Dict with status ("success" or "failure"), post_id (AT URI), url, and error.
    """
    logger.info(f"Posting to Bluesky for blog: {blog_url}")

    if not content or not content.strip():
        return {"status": "failure", "post_id": None, "url": None, "error": "Content is empty"}

    if len(content) > MAX_POST_LENGTH:
        return {
            "status": "failure", "post_id": None, "url": None,
            "error": f"Content is {len(content)} characters, over Bluesky's {MAX_POST_LENGTH} limit",
        }

    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            try:
                session = await _create_session(client)
            except ValueError as e:
                logger.error(str(e))
                return {"status": "failure", "post_id": None, "url": None, "error": str(e)}

            access_jwt = session["accessJwt"]
            external = {
                "uri": blog_url,
                "title": article_title or blog_url,
                "description": article_description[:MAX_CARD_DESCRIPTION],
            }
            if image_url:
                thumb = await _upload_thumbnail(client, access_jwt, image_url)
                if thumb:
                    external["thumb"] = thumb

            record = {
                "$type": "app.bsky.feed.post",
                "text": content,
                "langs": ["en"],
                "createdAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "embed": {"$type": "app.bsky.embed.external", "external": external},
            }
            facets = _build_facets(content)
            if facets:
                record["facets"] = facets

            response = await client.post(
                f"{XRPC_BASE}/com.atproto.repo.createRecord",
                json={"repo": session["did"], "collection": "app.bsky.feed.post", "record": record},
                headers={"Authorization": f"Bearer {access_jwt}"},
            )

            if response.status_code == 200:
                post_uri = response.json().get("uri", "")
                rkey = post_uri.rsplit("/", 1)[-1]
                post_url = f"https://bsky.app/profile/{session['handle']}/post/{rkey}"
                logger.info(f"Bluesky post successful: {post_url}")
                return {"status": "success", "post_id": post_uri, "url": post_url, "error": None}

            if response.status_code == 429:
                error = "Bluesky API rate limit exceeded. Try again later."
            elif response.status_code in (401, 403):
                error = f"Bluesky rejected the session (HTTP {response.status_code}): {response.text[:200]}"
            else:
                error = f"Bluesky API error: HTTP {response.status_code} — {response.text[:300]}"
            logger.error(error)
            return {"status": "failure", "post_id": None, "url": None, "error": error}

    except httpx.RequestError as e:
        error = f"Network error posting to Bluesky: {e}"
        logger.error(error)
        return {"status": "failure", "post_id": None, "url": None, "error": error}


if __name__ == "__main__":
    mcp.run(transport="stdio")
