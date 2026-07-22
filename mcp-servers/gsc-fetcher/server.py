"""
GSC Fetcher MCP Server

FastMCP server that reads Google Search Console performance data.
Provides one tool:
  - get_page_stats: Per-page clicks/impressions/CTR/position over a trailing window

Returns raw data only — filtering and ranking are the orchestrator's job.
"""

import logging
import os
from datetime import date, timedelta
from urllib.parse import quote

import httpx
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2 import service_account
from mcp.server.fastmcp import FastMCP

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger("gsc-fetcher")
logger.setLevel(logging.WARNING)

mcp = FastMCP("gsc-fetcher")

HTTP_TIMEOUT = 30.0
SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]

_credentials = None


def _get_credentials():
    """Load and cache service account credentials, refreshing the token when needed."""
    global _credentials

    key_path = os.environ.get("GSC_SERVICE_ACCOUNT_KEY_PATH", "")
    if not key_path or not os.path.exists(key_path):
        raise FileNotFoundError(f"GSC service account key not found at: {key_path or '(not set)'}")

    if _credentials is None:
        _credentials = service_account.Credentials.from_service_account_file(key_path, scopes=SCOPES)

    if not _credentials.valid:
        _credentials.refresh(GoogleAuthRequest())

    return _credentials


@mcp.tool()
async def get_page_stats(
    site_url: str, days: int = 180, lag_days: int = 3, row_limit: int = 25000
) -> dict:
    """Fetch per-page Search Console performance for a site over a trailing window.

    Args:
        site_url: URL-prefix property exactly as registered in Search Console
            (e.g. "https://blog.aspose.cloud/")
        days: Size of the trailing date window in days (default 180, ~6 months)
        lag_days: Days to exclude from the window's end to account for GSC's
            reporting lag (default 3 — recent days aren't fully finalized yet)
        row_limit: Maximum number of page rows to return (default 25000)

    Returns:
        Dict with status, site_url, start_date, end_date, row_count, and a
        pages list of {url, clicks, impressions, ctr, position}.
        On error, returns dict with error message and status="failed".
    """
    logger.info(f"Fetching GSC page stats for: {site_url} (days={days}, lag_days={lag_days})")

    try:
        credentials = _get_credentials()
    except FileNotFoundError as e:
        logger.error(str(e))
        return {"error": str(e), "status": "failed"}
    except Exception as e:
        logger.error(f"Failed to load GSC credentials: {e}")
        return {"error": f"Failed to load GSC credentials: {e}", "status": "failed"}

    end_date = date.today() - timedelta(days=lag_days)
    start_date = end_date - timedelta(days=days)

    encoded_site = quote(site_url, safe="")
    endpoint = f"https://www.googleapis.com/webmasters/v3/sites/{encoded_site}/searchAnalytics/query"
    payload = {
        "startDate": start_date.isoformat(),
        "endDate": end_date.isoformat(),
        "dimensions": ["page"],
        "rowLimit": row_limit,
    }

    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            response = await client.post(
                endpoint,
                json=payload,
                headers={"Authorization": f"Bearer {credentials.token}"},
            )
            response.raise_for_status()
    except httpx.HTTPStatusError as e:
        error = f"HTTP {e.response.status_code} querying GSC for {site_url}: {e.response.text[:300]}"
        logger.error(error)
        return {"error": error, "status": "failed"}
    except httpx.RequestError as e:
        error = f"Network error querying GSC for {site_url}: {e}"
        logger.error(error)
        return {"error": error, "status": "failed"}

    data = response.json()
    rows = data.get("rows", [])

    pages = [
        {
            "url": row["keys"][0],
            "clicks": row.get("clicks", 0),
            "impressions": row.get("impressions", 0),
            "ctr": row.get("ctr", 0.0),
            "position": row.get("position", 0.0),
        }
        for row in rows
    ]

    return {
        "status": "ok",
        "site_url": site_url,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "row_count": len(pages),
        "pages": pages,
    }


if __name__ == "__main__":
    mcp.run(transport="stdio")
