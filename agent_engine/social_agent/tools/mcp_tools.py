"""
MCP Tool Wrappers

Provides clean async functions that wrap MCP server tool calls.
Each server is started once per run via MCPSessions context manager.
"""

import json
import logging
import os
import sys
from contextlib import asynccontextmanager
from dataclasses import dataclass

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from agent_engine.social_agent.config import settings

logger = logging.getLogger("social_agent")

# ANSI colors for MCP server startup messages
_MAGENTA = "\033[35m"
_BOLD = "\033[1m"
_RESET = "\033[0m"


def _parse_result(result) -> any:
    """Parse an MCP tool result into a Python object.

    FastMCP serializes list results as multiple TextContent elements,
    and single results (dict, bool, str) as a single TextContent element.
    """
    if not result.content:
        return None

    if len(result.content) == 1:
        text = result.content[0].text
        try:
            return json.loads(text)
        except (json.JSONDecodeError, TypeError):
            return text

    items = []
    for content in result.content:
        try:
            items.append(json.loads(content.text))
        except (json.JSONDecodeError, TypeError):
            items.append(content.text)
    return items


@dataclass
class MCPSessions:
    """Holds active MCP client sessions for all servers."""
    rss_fetcher: ClientSession
    record_keeper: ClientSession
    linkedin_poster: ClientSession
    x_poster: ClientSession
    facebook_poster: ClientSession


@asynccontextmanager
async def open_mcp_sessions(platform: str = ""):
    """Open all MCP server sessions. Use as an async context manager.

    Starts each server subprocess once and yields an MCPSessions object.
    All sessions are closed when the context exits.

    Args:
        platform: Platform ID used to select platform-specific credentials.

    Usage:
        async with open_mcp_sessions(platform) as sessions:
            result = await rss_get_latest_posts(sessions, ...)
    """
    rss_path = settings.resolve_path(settings.RSS_FETCHER_PATH)
    record_path = settings.resolve_path(settings.RECORD_KEEPER_PATH)
    linkedin_path = settings.resolve_path(settings.LINKEDIN_POSTER_PATH)
    x_path = settings.resolve_path(settings.X_POSTER_PATH)
    facebook_path = settings.resolve_path(settings.FACEBOOK_POSTER_PATH)

    record_env = os.environ.copy()
    record_env["RECORDS_PATH"] = settings.resolve_path(settings.RECORDS_PATH)

    linkedin_env = os.environ.copy()
    linkedin_env["LINKEDIN_ACCESS_TOKEN"] = settings.LINKEDIN_ACCESS_TOKEN

    x_env = os.environ.copy()
    x_env["X_API_KEY"] = settings.X_API_KEY
    x_env["X_API_SECRET"] = settings.X_API_SECRET
    x_env["X_ACCESS_TOKEN"] = settings.X_ACCESS_TOKEN
    x_env["X_ACCESS_TOKEN_SECRET"] = settings.X_ACCESS_TOKEN_SECRET

    facebook_env = os.environ.copy()
    # Resolve platform-specific Facebook credentials.
    # Convention: FACEBOOK_{BRAND}_PAGE_ID / FACEBOOK_{BRAND}_PAGE_ACCESS_TOKEN
    # e.g. groupdocs-cloud → FACEBOOK_GROUPDOCS_PAGE_ID
    # Fallback: FACEBOOK_PAGE_ID (default, used by aspose-cloud)
    fb_page_id = settings.FACEBOOK_PAGE_ID
    fb_token = settings.FACEBOOK_PAGE_ACCESS_TOKEN
    if platform:
        brand = platform.split("-")[0].upper()  # groupdocs-cloud → GROUPDOCS
        brand_page_id = os.environ.get(f"FACEBOOK_{brand}_PAGE_ID", "")
        brand_token = os.environ.get(f"FACEBOOK_{brand}_PAGE_ACCESS_TOKEN", "")
        if brand_page_id and brand_token:
            fb_page_id = brand_page_id
            fb_token = brand_token
    facebook_env["FACEBOOK_PAGE_ID"] = fb_page_id
    facebook_env["FACEBOOK_PAGE_ACCESS_TOKEN"] = fb_token

    rss_params = StdioServerParameters(command=sys.executable, args=[rss_path])
    record_params = StdioServerParameters(command=sys.executable, args=[record_path], env=record_env)
    linkedin_params = StdioServerParameters(command=sys.executable, args=[linkedin_path], env=linkedin_env)
    x_params = StdioServerParameters(command=sys.executable, args=[x_path], env=x_env)
    facebook_params = StdioServerParameters(command=sys.executable, args=[facebook_path], env=facebook_env)

    logger.info(f"{_MAGENTA}{_BOLD}Starting RSS Fetcher MCP server...{_RESET}")
    async with stdio_client(rss_params) as (rss_read, rss_write):
        async with ClientSession(rss_read, rss_write) as rss_session:
            await rss_session.initialize()

            logger.info(f"{_MAGENTA}{_BOLD}Starting Record Keeper MCP server...{_RESET}")
            async with stdio_client(record_params) as (rec_read, rec_write):
                async with ClientSession(rec_read, rec_write) as record_session:
                    await record_session.initialize()

                    logger.info(f"{_MAGENTA}{_BOLD}Starting LinkedIn Poster MCP server...{_RESET}")
                    async with stdio_client(linkedin_params) as (li_read, li_write):
                        async with ClientSession(li_read, li_write) as linkedin_session:
                            await linkedin_session.initialize()

                            logger.info(f"{_MAGENTA}{_BOLD}Starting X Poster MCP server...{_RESET}")
                            async with stdio_client(x_params) as (x_read, x_write):
                                async with ClientSession(x_read, x_write) as x_session:
                                    await x_session.initialize()

                                    logger.info(f"{_MAGENTA}{_BOLD}Starting Facebook Poster MCP server...{_RESET}")
                                    async with stdio_client(facebook_params) as (fb_read, fb_write):
                                        async with ClientSession(fb_read, fb_write) as facebook_session:
                                            await facebook_session.initialize()

                                            logger.info("All MCP servers started")
                                            yield MCPSessions(
                                                rss_fetcher=rss_session,
                                                record_keeper=record_session,
                                                linkedin_poster=linkedin_session,
                                                x_poster=x_session,
                                                facebook_poster=facebook_session,
                                            )


# ─────────────────────────────────────────────────────────────────────────────
# RSS Fetcher Tools
# ─────────────────────────────────────────────────────────────────────────────

async def rss_get_latest_posts(sessions: MCPSessions, platform_url: str, limit: int = 10) -> list:
    """Fetch latest posts from an RSS feed."""
    result = await sessions.rss_fetcher.call_tool(
        "get_latest_posts",
        {"platform_url": platform_url, "limit": limit},
    )
    return _parse_result(result) or []


async def rss_fetch_post_by_url(sessions: MCPSessions, url: str) -> dict:
    """Fetch a single blog post by URL."""
    result = await sessions.rss_fetcher.call_tool("fetch_post_by_url", {"url": url})
    return _parse_result(result) or {"error": "Empty response", "status": "failed"}


# ─────────────────────────────────────────────────────────────────────────────
# Record Keeper Tools
# ─────────────────────────────────────────────────────────────────────────────

async def record_is_published(sessions: MCPSessions, blog_url: str) -> bool:
    """Check if a blog URL has already been posted."""
    result = await sessions.record_keeper.call_tool("is_published", {"blog_url": blog_url})
    return _parse_result(result) or False


async def record_get_all(sessions: MCPSessions) -> list:
    """Retrieve all published records."""
    result = await sessions.record_keeper.call_tool("get_records", {})
    return _parse_result(result) or []


async def record_save(sessions: MCPSessions, blog_url: str, title: str, platform_id: str, results: dict) -> bool:
    """Save a posting record."""
    result = await sessions.record_keeper.call_tool(
        "save_record",
        {
            "blog_url": blog_url,
            "title": title,
            "platform_id": platform_id,
            "results": results,
        },
    )
    return _parse_result(result) or False


# ─────────────────────────────────────────────────────────────────────────────
# LinkedIn Poster Tools
# ─────────────────────────────────────────────────────────────────────────────

async def linkedin_validate_token(sessions: MCPSessions) -> bool:
    """Validate the LinkedIn access token."""
    result = await sessions.linkedin_poster.call_tool("validate_token", {})
    return _parse_result(result) or False


async def linkedin_post(sessions: MCPSessions, content: str, blog_url: str) -> dict:
    """Post content to LinkedIn."""
    result = await sessions.linkedin_poster.call_tool(
        "post_to_linkedin",
        {"content": content, "blog_url": blog_url},
    )
    return _parse_result(result) or {"status": "failure", "post_id": None, "error": "Empty response"}


# ─────────────────────────────────────────────────────────────────────────────
# X (Twitter) Poster Tools
# ─────────────────────────────────────────────────────────────────────────────

async def x_validate_credentials(sessions: MCPSessions) -> bool:
    """Validate the X (Twitter) OAuth 1.0a credentials."""
    result = await sessions.x_poster.call_tool("validate_credentials", {})
    return _parse_result(result) or False


async def x_post(sessions: MCPSessions, content: str, blog_url: str) -> dict:
    """Post content to X (Twitter)."""
    result = await sessions.x_poster.call_tool(
        "post_to_x",
        {"content": content, "blog_url": blog_url},
    )
    return _parse_result(result) or {"status": "failure", "post_id": None, "error": "Empty response"}


# ─────────────────────────────────────────────────────────────────────────────
# Facebook Page Poster Tools
# ─────────────────────────────────────────────────────────────────────────────

async def facebook_validate_token(sessions: MCPSessions) -> bool:
    """Validate the Facebook Page Access Token."""
    result = await sessions.facebook_poster.call_tool("validate_token", {})
    return _parse_result(result) or False


async def facebook_post(sessions: MCPSessions, content: str, blog_url: str) -> dict:
    """Post content to a Facebook Page."""
    result = await sessions.facebook_poster.call_tool(
        "post_to_facebook",
        {"content": content, "blog_url": blog_url},
    )
    return _parse_result(result) or {"status": "failure", "post_id": None, "error": "Empty response"}
