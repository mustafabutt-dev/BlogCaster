# SPEC-008: GSC-Based Auto Mode Selection Strategy

## Title
GSC Selection Strategy — Auto Mode candidate selection using Search Console performance

## Description
A second Auto Mode candidate-selection strategy, alongside the existing "latest unpublished RSS post." Uses `gsc-fetcher`'s page stats to find posts that rank in search but underperform on clicks, anywhere in the site's history — not limited to the RSS feed's recent-posts window.

## CLI Interface
```
python main.py --auto --platform aspose-cloud --strategy gsc
python main.py --auto --platform aspose-cloud --strategy latest   # default, unchanged
```

## Selection Flow
1. Query `gsc-fetcher` for the platform's site URL, trailing 180 days (3-day lag)
2. Filter: position ≤ 30, impressions ≥ 20, primary-language path only (exclude `/it/`, `/zh-tw/`, etc.)
3. Rank: CTR ≤ 3% bucket first (sorted by impressions desc), then everything else (sorted by impressions desc)
4. Walk ranked list, skipping: already-published URLs, unreachable/thin pages, posts published within the last 28 days
5. First survivor's content fetched via `fetch_post_by_url` (not RSS) → same downstream pipeline as "latest" (format, post, record)

## Acceptance Criteria
- [x] `--strategy` flag added, default `latest`, `gsc` opts into the new path
- [x] `_select_latest_candidate` behavior-identical to the pre-refactor RSS logic (regression-checked via live dry-run)
- [x] `_select_gsc_candidate` returns the same shape as `_select_latest_candidate` so downstream code is strategy-agnostic
- [x] Locale-prefixed paths excluded from candidates
- [x] Already-published URLs skipped
- [x] Posts younger than 28 days skipped
- [x] Live-tested against `blog.aspose.cloud` — correctly selected and formatted an English candidate

## Dependencies
- SPEC-007 (GSC Fetcher MCP)
- SPEC-004 (Orchestrator and CLI)

## Edge Cases
- GSC returns zero pages (no data for the window) — falls through to "no valid candidate" like an empty RSS feed does today
- Every ranked candidate is already published or too new — returns None, run exits with failure, same as the latest strategy's "no unpublished posts" case
- `published_date` unparseable — candidate is not excluded on recency grounds (fails open rather than blocking a potentially valid pick on a parsing gap)

## Out of Scope
- Workflow schedule changes (which days run which strategy) — separate stage
- Per-platform tuning of the filter constants (currently global)
- A feedback loop measuring whether GSC-selected posts actually improved CTR/ranking afterward
