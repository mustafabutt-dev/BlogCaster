# SPEC-007: GSC Fetcher MCP Server

## Title
GSC Fetcher — FastMCP server for reading Google Search Console page performance

## Description
A FastMCP server that authenticates with a Google service account and queries the Search Console Search Analytics API for a site's per-page performance (clicks, impressions, CTR, average position) over a trailing date window. Returns raw data only — no filtering, ranking, or business logic. This feeds the future GSC-based Auto Mode selection strategy (candidate filtering and ranking happen in the orchestrator, not here).

## Tools to Expose

### 1. `get_page_stats(site_url: str, days: int = 180, lag_days: int = 3, row_limit: int = 25000) -> dict`
- Authenticates via service account, calls `searchAnalytics.query` with `dimensions: ["page"]`
- Date range: ends `lag_days` days ago (GSC reporting lag), spans `days` days before that
- Returns `{"status": "ok", "site_url", "start_date", "end_date", "row_count", "pages": [{"url", "clicks", "impressions", "ctr", "position"}, ...]}`
- On auth failure, HTTP error, or network error: `{"status": "failed", "error": "..."}`

## Acceptance Criteria
- [ ] Tool registered and callable via FastMCP stdio
- [ ] Service account credentials loaded from `GSC_SERVICE_ACCOUNT_KEY_PATH`, readonly scope
- [ ] Date range correctly excludes the last `lag_days` days
- [ ] Returns empty `pages` list (not an error) when GSC has no data for the range
- [ ] Auth errors (missing/invalid key, service account not added to property) return a clear `status: "failed"` with a descriptive error, not a raw exception
- [ ] Live-tested against at least one real registered property before being marked complete

## Dependencies
- None (standalone MCP server)

## Edge Cases
- Service account key file missing or malformed
- Service account not granted access to the requested property (403)
- Property URL format mismatch (trailing slash, domain vs URL-prefix) causing a 403/404
- Site with zero search traffic in the window (empty rows, not an error)
- `row_limit` exceeded (more indexed pages than the limit — truncated, not an error)

## Out of Scope
- Filtering by position/impressions (orchestrator's job)
- Cross-referencing against `published_record.json` (orchestrator's job)
- Query-level (keyword-level) data — page-level aggregation only
- Any write operations to Search Console
