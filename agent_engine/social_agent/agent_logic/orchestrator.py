"""
Orchestrator

Core workflow engine for both Manual and Auto modes.
Coordinates MCP servers and LLM formatter to execute the full pipeline.
Posts to both LinkedIn and X (Twitter) independently.
Supports per-platform retries — if one platform failed, re-running the
same URL will only post to the platforms that haven't succeeded yet.
"""

import logging
from datetime import datetime
from urllib.parse import urlparse, urlunparse

from agent_engine.social_agent.config import settings
from agent_engine.social_agent.tools.mcp_tools import (
    MCPSessions,
    facebook_post,
    facebook_validate_token,
    linkedin_post,
    linkedin_validate_token,
    record_get_all,
    record_save,
    rss_fetch_post_by_url,
    rss_get_latest_posts,
    x_post,
    x_validate_credentials,
)
from agent_engine.social_agent.utils.helpers import (
    detect_platform_from_url,
    find_platform_by_id,
    get_active_platforms,
    load_registry,
)
from agent_engine.social_agent.utils.llm_service import LLMResult, format_for_facebook, format_for_linkedin, format_for_x
from agent_engine.social_agent.utils.metrics import MetricsRecorder

logger = logging.getLogger("social_agent")

ALL_PLATFORMS = ("linkedin", "x", "facebook")


def _normalize_url(url: str) -> str:
    """Normalize a URL for comparison (same logic as record-keeper)."""
    parsed = urlparse(url.strip())
    return urlunparse((
        parsed.scheme.lower(),
        parsed.netloc.lower(),
        parsed.path.rstrip("/").lower(),
        "", "", "",
    ))


async def _get_succeeded_platforms(sessions: MCPSessions, url: str) -> set:
    """Check which platforms have already successfully posted this URL.

    Returns a set of platform names (e.g. {"linkedin"}) that succeeded.
    """
    normalized = _normalize_url(url)
    records = await record_get_all(sessions)

    for record in records:
        if _normalize_url(record.get("blog_url", "")) == normalized:
            shared_on = record.get("shared_on", {})
            return {
                platform for platform, result in shared_on.items()
                if result.get("status") == "success"
            }

    return set()


async def _validate_platforms(sessions: MCPSessions, skip_platforms: set = None, target: str = "all") -> dict:
    """Validate credentials for all platforms. Returns dict of platform → bool.

    Platforms with empty credentials, in skip_platforms, or excluded by target are marked False.
    """
    skip_platforms = skip_platforms or set()
    results = {}

    # LinkedIn
    if target not in ("all", "linkedin"):
        logger.info(f"LinkedIn excluded by --target {target}")
        results["linkedin"] = False
    elif "linkedin" in skip_platforms:
        logger.info("LinkedIn already succeeded for this URL — skipping")
        results["linkedin"] = False
    elif settings.LINKEDIN_ACCESS_TOKEN:
        logger.info("Validating LinkedIn token...")
        results["linkedin"] = await linkedin_validate_token(sessions)
        if results["linkedin"]:
            logger.info("LinkedIn token is valid")
        else:
            logger.warning("LinkedIn token is invalid or expired")
    else:
        logger.info("LinkedIn credentials not configured — skipping")
        results["linkedin"] = False

    # X (Twitter)
    if target not in ("all", "x"):
        logger.info(f"X excluded by --target {target}")
        results["x"] = False
    elif "x" in skip_platforms:
        logger.info("X already succeeded for this URL — skipping")
        results["x"] = False
    elif all([settings.X_API_KEY, settings.X_API_SECRET, settings.X_ACCESS_TOKEN, settings.X_ACCESS_TOKEN_SECRET]):
        logger.info("Validating X credentials...")
        results["x"] = await x_validate_credentials(sessions)
        if results["x"]:
            logger.info("X credentials are valid")
        else:
            logger.warning("X credentials are invalid or expired")
    else:
        logger.info("X credentials not configured — skipping")
        results["x"] = False

    # Facebook
    if target not in ("all", "facebook"):
        logger.info(f"Facebook excluded by --target {target}")
        results["facebook"] = False
    elif "facebook" in skip_platforms:
        logger.info("Facebook already succeeded for this URL — skipping")
        results["facebook"] = False
    elif all([settings.FACEBOOK_PAGE_ID, settings.FACEBOOK_PAGE_ACCESS_TOKEN]):
        logger.info("Validating Facebook token...")
        results["facebook"] = await facebook_validate_token(sessions)
        if results["facebook"]:
            logger.info("Facebook token is valid")
        else:
            logger.warning("Facebook token is invalid or expired")
    else:
        logger.info("Facebook credentials not configured — skipping")
        results["facebook"] = False

    return results


async def _format_for_platforms(
    valid_platforms: dict, title: str, content: str, blog_url: str
) -> dict:
    """Format content for each valid platform via LLM. Returns dict of platform → formatted text."""
    formatted = {}

    if valid_platforms.get("linkedin"):
        logger.info("Formatting post for LinkedIn via LLM...")
        try:
            formatted["linkedin"] = await format_for_linkedin(title, content, blog_url)
        except Exception as e:
            logger.error(f"LLM formatting for LinkedIn failed: {e}")
            print(f"Error formatting for LinkedIn: {e}")

    if valid_platforms.get("x"):
        logger.info("Formatting tweet for X via LLM...")
        try:
            formatted["x"] = await format_for_x(title, content, blog_url)
        except Exception as e:
            logger.error(f"LLM formatting for X failed: {e}")
            print(f"Error formatting for X: {e}")

    if valid_platforms.get("facebook"):
        logger.info("Formatting post for Facebook via LLM...")
        try:
            formatted["facebook"] = await format_for_facebook(title, content, blog_url)
        except Exception as e:
            logger.error(f"LLM formatting for Facebook failed: {e}")
            print(f"Error formatting for Facebook: {e}")

    return formatted


async def _post_to_platforms(
    sessions: MCPSessions, formatted: dict, blog_url: str
) -> dict:
    """Post formatted content to each platform. Returns dict of platform → result dict.

    Values in `formatted` may be LLMResult objects or plain strings.
    """
    results = {}

    if "linkedin" in formatted:
        logger.info("Posting to LinkedIn...")
        text = formatted["linkedin"].text if isinstance(formatted["linkedin"], LLMResult) else formatted["linkedin"]
        linkedin_result = await linkedin_post(sessions, text, blog_url)
        results["linkedin"] = linkedin_result
        if linkedin_result.get("status") == "success":
            post_id = linkedin_result.get("post_id", "")
            logger.info(f"LinkedIn post successful: post_id={post_id}")
            print(f"Successfully posted to LinkedIn! Post ID: {post_id}")
        else:
            logger.error(f"LinkedIn posting failed: {linkedin_result.get('error')}")
            print(f"Error posting to LinkedIn: {linkedin_result.get('error')}")

    if "x" in formatted:
        logger.info("Posting to X...")
        text = formatted["x"].text if isinstance(formatted["x"], LLMResult) else formatted["x"]
        x_result = await x_post(sessions, text, blog_url)
        results["x"] = x_result
        if x_result.get("status") == "success":
            post_id = x_result.get("post_id", "")
            logger.info(f"X post successful: post_id={post_id}")
            print(f"Successfully posted to X! Post ID: {post_id}")
        else:
            logger.error(f"X posting failed: {x_result.get('error')}")
            print(f"Error posting to X: {x_result.get('error')}")

    if "facebook" in formatted:
        logger.info("Posting to Facebook...")
        text = formatted["facebook"].text if isinstance(formatted["facebook"], LLMResult) else formatted["facebook"]
        facebook_result = await facebook_post(sessions, text, blog_url)
        results["facebook"] = facebook_result
        if facebook_result.get("status") == "success":
            post_id = facebook_result.get("post_id", "")
            logger.info(f"Facebook post successful: post_id={post_id}")
            print(f"Successfully posted to Facebook! Post ID: {post_id}")
        else:
            logger.error(f"Facebook posting failed: {facebook_result.get('error')}")
            print(f"Error posting to Facebook: {facebook_result.get('error')}")

    return results


async def run_manual_mode(
    sessions: MCPSessions, url: str, target: str = "all", metrics: MetricsRecorder | None = None
) -> bool:
    """Execute Manual Mode: post a specific blog URL to LinkedIn and/or X.

    If the URL was previously posted to some platforms but not all,
    this will only post to the platforms that haven't succeeded yet.

    Args:
        sessions: Active MCP server sessions
        url: The blog post URL to share
        target: Social media target — "all", "linkedin", or "x"
        metrics: Optional MetricsRecorder to track run metrics

    Returns:
        True if at least one platform posted successfully, False otherwise
    """
    logger.info(f"Starting Manual Mode for URL: {url}")

    # 1. Load registry and detect platform
    registry_path = settings.resolve_path(settings.REGISTRY_PATH)
    registry = load_registry(registry_path)
    platform = detect_platform_from_url(registry, url)

    if platform:
        platform_id = platform["id"]
        logger.info(f"Platform detected: {platform_id}")
        if metrics:
            metrics.product = platform_id
            metrics.website = urlparse(platform.get("url", "")).netloc
    else:
        platform_id = "unknown"
        logger.warning(f"URL does not match any registered platform, using platform_id='unknown'")
        if metrics:
            metrics.product = "unknown"

    # 2. Check which platforms already succeeded for this URL
    logger.info("Checking published status per platform...")
    succeeded_platforms = await _get_succeeded_platforms(sessions, url)

    if succeeded_platforms >= set(ALL_PLATFORMS):
        logger.info(f"Already posted to all platforms: {url} — skipping")
        print(f"This URL has already been posted to all platforms: {url}")
        return False

    if succeeded_platforms:
        logger.info(f"Already succeeded on: {succeeded_platforms}. Will retry remaining platforms.")
        print(f"Already posted to: {', '.join(succeeded_platforms)}. Retrying remaining platforms...")

    # 3. Fetch post content
    logger.info("Fetching post content...")
    post_data = await rss_fetch_post_by_url(sessions, url)

    if post_data.get("status") == "failed":
        logger.error(f"Failed to fetch post: {post_data.get('error')}")
        print(f"Error fetching post: {post_data.get('error')}")
        return False

    title = post_data.get("title", "Unknown")
    content = post_data.get("content", "")
    logger.info(f"Fetched post: \"{title}\" ({len(content)} chars)")

    if metrics:
        metrics.items_discovered = 1

    # 4. Validate credentials (skip platforms that already succeeded)
    valid_platforms = await _validate_platforms(sessions, skip_platforms=succeeded_platforms, target=target)

    if not any(valid_platforms.values()):
        logger.error("No valid platform credentials found for remaining platforms")
        print("Error: No valid credentials for any remaining platform.")
        return False

    # 5. Format via LLM for each valid platform
    formatted = await _format_for_platforms(valid_platforms, title, content, url)

    if not formatted:
        logger.error("Failed to format content for any platform")
        print("Error: LLM failed to format content for any platform")
        return False

    # Record LLM usage from each platform's formatting result
    if metrics:
        for plat, llm_result in formatted.items():
            if isinstance(llm_result, LLMResult):
                metrics.record_llm_usage(
                    llm_result.input_tokens, llm_result.output_tokens,
                    llm_result.total_tokens, llm_result.api_call_count,
                )

    # 6. Post to each platform independently
    post_results = await _post_to_platforms(sessions, formatted, url)

    # Track posting results in metrics
    if metrics:
        for plat, result in post_results.items():
            if result.get("status") == "success":
                metrics.record_success()
            else:
                metrics.record_failure()

    # 7. Save record only if at least one platform succeeded
    any_success = any(r.get("status") == "success" for r in post_results.values())
    if any_success:
        # Only save successful results — record-keeper merges with existing record
        successful_results = {
            k: v for k, v in post_results.items() if v.get("status") == "success"
        }
        await _save_record(sessions, url, title, platform_id, successful_results)
    else:
        logger.warning("All platforms failed — not saving record so it can be retried")

    logger.info(f"Manual Mode complete for: {url}")
    return any_success


async def run_auto_mode(
    sessions: MCPSessions, platform_id: str, target: str = "all", metrics: MetricsRecorder | None = None
) -> bool:
    """Execute Auto Mode: find and post the latest unpublished blog for a platform.

    Fetches ALL posts from the RSS feed and ALL published records, then
    does in-memory matching to find the first unpublished post. Any URL
    with an existing record is skipped (use --url to retry failed platforms).

    Args:
        sessions: Active MCP server sessions
        platform_id: The platform ID from the registry
        target: Social media target — "all", "linkedin", or "x"
        metrics: Optional MetricsRecorder to track run metrics

    Returns:
        True if at least one platform posted successfully, False otherwise
    """
    logger.info(f"Starting Auto Mode for platform: {platform_id}")

    # 1. Load registry and validate platform
    registry_path = settings.resolve_path(settings.REGISTRY_PATH)
    registry = load_registry(registry_path)
    platform = find_platform_by_id(registry, platform_id)

    if not platform:
        available = [p["id"] for p in get_active_platforms(registry)]
        logger.error(f"Platform '{platform_id}' not found in registry")
        print(f"Error: Platform '{platform_id}' not found.")
        print(f"Available platforms: {', '.join(available)}")
        return False

    if not platform.get("active", False):
        logger.warning(f"Platform '{platform_id}' is inactive")
        print(f"Error: Platform '{platform_id}' is inactive.")
        return False

    rss_url = platform["rss_feed"]
    logger.info(f"Platform '{platform_id}' found: {platform['name']} (RSS: {rss_url})")

    if metrics:
        metrics.product = platform_id
        metrics.website = urlparse(platform.get("url", "")).netloc

    # 2. Fetch ALL posts from RSS feed (limit=0 means no limit)
    logger.info("Fetching all posts from RSS feed...")
    posts = await rss_get_latest_posts(sessions, rss_url, limit=0)

    if not posts:
        logger.warning("No posts found in RSS feed")
        print(f"No posts found in the RSS feed for {platform['name']}.")
        return False

    logger.info(f"Fetched {len(posts)} posts from RSS feed")

    # 3. Load all published records and build a set of normalized URLs
    logger.info("Loading published records...")
    records = await record_get_all(sessions)
    published_urls = {_normalize_url(r["blog_url"]) for r in records if r.get("blog_url")}
    logger.info(f"Found {len(published_urls)} published records")

    # 4. Find first unpublished post with a valid URL (newest first)
    unpublished_post = None
    skipped_published = 0
    skipped_broken = 0
    for post in posts:
        post_url = post.get("link", "")
        if not post_url:
            continue
        if _normalize_url(post_url) in published_urls:
            skipped_published += 1
            continue

        # Validate URL points to a real blog post (not a listing/404 page)
        logger.info(f"Validating candidate URL: {post_url}")
        post_data = await rss_fetch_post_by_url(sessions, post_url)

        if post_data.get("status") == "failed":
            logger.warning(f"Skipping unreachable URL: {post_url} — {post_data.get('error')}")
            skipped_broken += 1
            continue

        fetched_title = post_data.get("title", "")
        fetched_content = post_data.get("content", "")

        if not fetched_title or fetched_title == "Unknown" or len(fetched_content) < 200:
            logger.warning(
                f"Skipping invalid page: {post_url} "
                f"(title='{fetched_title[:50]}', content_len={len(fetched_content)})"
            )
            skipped_broken += 1
            continue

        unpublished_post = post
        unpublished_post["_fetched_content"] = fetched_content
        unpublished_post["_fetched_title"] = fetched_title
        break

    if not unpublished_post:
        logger.warning(f"No valid unpublished posts found (published: {skipped_published}, broken: {skipped_broken})")
        print(f"No valid unpublished posts found from {platform['name']}.")
        return False

    post_url = unpublished_post["link"]
    title = unpublished_post.get("_fetched_title") or unpublished_post.get("title", "Unknown")
    summary = unpublished_post.get("summary", "")
    fetched_content = unpublished_post.get("_fetched_content", "")
    logger.info(f"Skipped {skipped_published} already-published, {skipped_broken} broken URLs")
    logger.info(f"Selected unpublished post: \"{title}\" — {post_url}")

    if metrics:
        metrics.items_discovered = 1

    # 5. Validate credentials for targeted platforms
    valid_platforms = await _validate_platforms(sessions, target=target)

    if not any(valid_platforms.values()):
        logger.error("No valid platform credentials found")
        print("Error: No valid credentials for any platform. Check LinkedIn token and X credentials.")
        return False

    # 6. Format via LLM for each valid platform (prefer fetched page content over RSS summary)
    content_for_llm = fetched_content if fetched_content else summary
    formatted = await _format_for_platforms(valid_platforms, title, content_for_llm, post_url)

    if not formatted:
        logger.error("Failed to format content for any platform")
        print("Error: LLM failed to format content for any platform")
        return False

    # Record LLM usage from each platform's formatting result
    if metrics:
        for plat, llm_result in formatted.items():
            if isinstance(llm_result, LLMResult):
                metrics.record_llm_usage(
                    llm_result.input_tokens, llm_result.output_tokens,
                    llm_result.total_tokens, llm_result.api_call_count,
                )

    # 7. Post to each platform independently
    post_results = await _post_to_platforms(sessions, formatted, post_url)

    # Track posting results in metrics
    if metrics:
        for plat, result in post_results.items():
            if result.get("status") == "success":
                metrics.record_success()
            else:
                metrics.record_failure()

    # 8. Save record only if at least one platform succeeded
    any_success = any(r.get("status") == "success" for r in post_results.values())
    if any_success:
        successful_results = {
            k: v for k, v in post_results.items() if v.get("status") == "success"
        }
        await _save_record(sessions, post_url, title, platform_id, successful_results)
    else:
        logger.warning("All platforms failed — not saving record so it can be retried")

    logger.info(f"Auto Mode complete for platform: {platform_id}")
    return any_success


async def _save_record(
    sessions: MCPSessions, blog_url: str, title: str, platform_id: str, post_results: dict
) -> None:
    """Save a posting record with results from successful platforms only.

    The record-keeper merges results into existing records, so calling this
    with only the newly-succeeded platforms will add them alongside any
    previously-succeeded ones.

    Args:
        sessions: Active MCP server sessions
        blog_url: Blog post URL
        title: Blog post title
        platform_id: Platform ID
        post_results: Dict of platform_name → result dict (only successful ones)
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    results = {}

    for platform_name, result in post_results.items():
        results[platform_name] = {
            "status": result.get("status", "failure"),
            "post_id": result.get("post_id", ""),
            "shared_at": timestamp,
        }

    saved = await record_save(sessions, blog_url, title, platform_id, results)
    if saved:
        logger.info(f"Record saved for {blog_url}")
    else:
        logger.error(f"Failed to save record for {blog_url}")
