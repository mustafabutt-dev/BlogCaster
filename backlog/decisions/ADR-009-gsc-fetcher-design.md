# ADR-009: GSC Fetcher MCP Server Design

## Status
Accepted

## Context
Auto Mode currently always picks the newest unpublished RSS entry. We want an additional selection strategy that uses real Google Search Console (GSC) performance data to find posts worth a social push — pages that already rank but are underperforming on clicks. RSS only exposes the latest ~10-20 posts, but GSC reports on the site's entire indexed history, so candidate selection for this strategy must not depend on the RSS feed at all. Content for whichever URL GSC surfaces is fetched directly via the existing `fetch_post_by_url` tool (already used by Manual Mode), which works on any live URL regardless of age.

## Decision
Build a GSC Fetcher as a FastMCP server with one tool, authenticating with a Google service account and calling the Search Analytics REST API directly via `httpx` (no `google-api-python-client` dependency — only `google-auth` for minting an access token from the service account key).

### Tool
**`get_page_stats(site_url: str, days: int = 180, lag_days: int = 3, row_limit: int = 25000) -> dict`**
- Queries `searchAnalytics.query` with `dimensions: ["page"]`, which has GSC aggregate clicks/impressions/CTR/position per page across all queries — no manual query-level aggregation needed.
- Date range: `[today - lag_days - days, today - lag_days]`. `lag_days` (default 3) accounts for GSC's reporting lag, where the most recent days are incomplete.
- Returns raw per-page stats only. Filtering (position ceiling, impression floor, recency exclusion) and ranking are orchestrator responsibilities, not this server's — matching how `rss-fetcher` returns raw feed data and `orchestrator.py` decides what to do with it.

### Auth
- Service account JSON key, path from `GSC_SERVICE_ACCOUNT_KEY_PATH` env var (same pattern as other credentials in ADR-007).
- Scope: `https://www.googleapis.com/auth/webmasters.readonly` (read-only — this server never writes to GSC).
- The service account must be added as a user in each Search Console property being queried; this is a manual one-time step in the GSC UI, done per-property outside of code.
- `keys/` directory (where the key file lives) added to `.gitignore` — a credential file must never be committed.

### Site URL Format
Properties are registered in Search Console as URL-prefix properties (e.g. `https://blog.aspose.cloud/`), matching each platform's `url` field in the registry (with a trailing slash appended, since GSC's URL-prefix property IDs always include it for the root).

## Consequences
- New dependency: `google-auth` (already installed locally for an unrelated Google Sheets integration, being reused here).
- GSC data has a reporting lag (2-3 days) and a 16-month history cap — both handled by `lag_days` and by callers choosing a `days` window within that cap.
- This server has no knowledge of `published_record.json` or blog content — it purely reports search performance. All decision logic (which page to actually post) lives in the orchestrator.
- GSC indexes locale-prefixed translations of posts (`/it/`, `/zh-tw/`, etc.) alongside the primary-language original. Discovered live: a raw ranking surfaced an Italian post, which the LLM then formatted (correctly) in Italian for an English-audience page. The orchestrator filters out any URL whose first path segment matches a language-code pattern (`^[a-z]{2}(-[a-z]{2})?$`) before ranking — see D-015.

## Implementation Notes
- Server file: `mcp-servers/gsc-fetcher/server.py`
- Dependencies: `mcp`, `httpx`, `google-auth`
- Credentials object is created lazily and cached at module scope; `google-auth`'s `Credentials.refresh()` handles token expiry internally, avoiding a token mint on every call
- Timeout: 30 seconds for HTTP requests, matching `rss-fetcher` convention

## References
- SPEC-007
