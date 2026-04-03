"""
X (Twitter) Poster MCP Server

FastMCP server that posts formatted content to X (Twitter).
Provides two tools:
  - post_to_x: Create a tweet on the authenticated user's profile
  - validate_credentials: Check if the OAuth 1.0a credentials are valid

Uses the X API v2 via tweepy with OAuth 1.0a user context authentication.
"""

import logging
import os

import tweepy
from mcp.server.fastmcp import FastMCP

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger("x-poster")
logger.setLevel(logging.WARNING)

mcp = FastMCP("x-poster")

MAX_TWEET_LENGTH = 280


def _get_client() -> tweepy.Client:
    """Create an authenticated tweepy Client using OAuth 1.0a credentials."""
    api_key = os.environ.get("X_API_KEY", "")
    api_secret = os.environ.get("X_API_SECRET", "")
    access_token = os.environ.get("X_ACCESS_TOKEN", "")
    access_token_secret = os.environ.get("X_ACCESS_TOKEN_SECRET", "")

    if not all([api_key, api_secret, access_token, access_token_secret]):
        raise ValueError(
            "X credentials not fully set. Need: X_API_KEY, X_API_SECRET, "
            "X_ACCESS_TOKEN, X_ACCESS_TOKEN_SECRET"
        )

    return tweepy.Client(
        consumer_key=api_key,
        consumer_secret=api_secret,
        access_token=access_token,
        access_token_secret=access_token_secret,
    )


@mcp.tool()
def validate_credentials() -> bool:
    """Check if the X (Twitter) OAuth 1.0a credentials are valid.

    Makes a lightweight call to GET /2/users/me.

    Returns:
        True if credentials are valid, False otherwise.
    """
    logger.info("Validating X credentials")

    try:
        client = _get_client()
    except ValueError as e:
        logger.error(str(e))
        return False

    try:
        response = client.get_me()
        if response and response.data:
            logger.info(f"X credentials valid — user: @{response.data.username}")
            return True
        logger.warning("X credentials validation returned no user data")
        return False

    except tweepy.Unauthorized:
        logger.warning("X credentials are invalid (401 Unauthorized)")
        return False
    except tweepy.Forbidden:
        # Free tier doesn't allow GET /2/users/me — credentials may still
        # be valid for posting. Return True and let post_to_x fail if not.
        logger.info("GET /2/users/me returned 403 (Free tier). Assuming credentials are valid.")
        return True
    except tweepy.TweepyException as e:
        logger.error(f"Error validating X credentials: {e}")
        return False


@mcp.tool()
def post_to_x(content: str, blog_url: str) -> dict:
    """Post a tweet to the authenticated user's X (Twitter) profile.

    Args:
        content: The LLM-formatted tweet text (must be <= 280 characters)
        blog_url: The original blog URL (for logging/tracking)

    Returns:
        Dict with status ("success" or "failure"), post_id, and error fields.
    """
    logger.info(f"Posting to X for blog: {blog_url}")

    # Validate content
    if not content or not content.strip():
        logger.error("Empty content provided")
        return {"status": "failure", "post_id": None, "error": "Content is empty"}

    if len(content) > MAX_TWEET_LENGTH:
        error = f"Tweet exceeds {MAX_TWEET_LENGTH} chars ({len(content)} chars)"
        logger.error(error)
        return {"status": "failure", "post_id": None, "error": error}

    try:
        client = _get_client()
    except ValueError as e:
        logger.error(str(e))
        return {"status": "failure", "post_id": None, "error": str(e)}

    try:
        response = client.create_tweet(text=content)

        if response and response.data:
            post_id = response.data.get("id", "")
            logger.info(f"X post successful: post_id={post_id}")
            return {"status": "success", "post_id": post_id, "error": None}

        error = "X API returned no data for the created tweet"
        logger.error(error)
        return {"status": "failure", "post_id": None, "error": error}

    except tweepy.Unauthorized:
        error = "X credentials are invalid or expired (401)"
        logger.error(error)
        return {"status": "failure", "post_id": None, "error": error}

    except tweepy.Forbidden as e:
        error = f"Insufficient permissions or duplicate tweet (403): {e}"
        logger.error(error)
        return {"status": "failure", "post_id": None, "error": error}

    except tweepy.TooManyRequests:
        error = "X API rate limit exceeded (429). Try again later."
        logger.warning(error)
        return {"status": "failure", "post_id": None, "error": error}

    except tweepy.TweepyException as e:
        error = f"X API error: {e}"
        logger.error(error)
        return {"status": "failure", "post_id": None, "error": error}


if __name__ == "__main__":
    mcp.run(transport="stdio")
