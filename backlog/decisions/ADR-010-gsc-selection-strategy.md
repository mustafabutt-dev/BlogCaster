# ADR-010: GSC-Based Auto Mode Selection Strategy

## Status
Accepted

## Context
ADR-009 built a server that reports raw Search Console performance data. Auto Mode needs a second candidate-selection strategy (alongside the existing "latest unpublished RSS post") that uses this data to find posts worth a social push — visible in search but underperforming on clicks.

## Decision
Add a `strategy` parameter to `run_auto_mode` (`"latest"` default, `"gsc"` new), exposed via `--strategy` on the CLI. The existing RSS-based selection logic was extracted unchanged into `_select_latest_candidate`; the new logic lives in `_select_gsc_candidate`. Both return the same shape (`url`, `title`, `content`, `image_url`) so the rest of the pipeline (credential validation, LLM formatting, posting, record saving) doesn't need to know which strategy picked the candidate.

### Filtering and Ranking (`_rank_gsc_candidates`)
Applied to every page GSC returns, before ranking:
- **Position ≤ 30** — below roughly page 3, no realistic amount of social traffic changes the outcome.
- **Impressions ≥ 20** — filters out one-off query noise.
- **Primary-language paths only** — see D-015 below.

Remaining pages are split into two buckets: CTR ≤ 3% ("underperforming" — ranks fine, barely clicked) sorted by impressions descending, then everything else sorted the same way as a fallback. The underperforming bucket is tried first.

### Recency and Dedup
`_select_gsc_candidate` walks the ranked list and, for each candidate:
1. Skips it if already in `published_record.json`.
2. Fetches content via `fetch_post_by_url` (not RSS — GSC can surface pages from anywhere in the site's history, so content-fetching must not depend on the RSS feed's ~10-20 post window).
3. Skips it if the fetch fails or content is too thin (mirrors the existing latest-strategy validity check).
4. Skips it if published within the last 28 days (`GSC_MIN_AGE_DAYS`) — GSC hasn't had time to judge it fairly yet.
5. Returns the first candidate that survives all of the above.

### D-015: Locale Path Filtering
Discovered live during testing: `blog.aspose.cloud` serves translated post copies under locale-prefixed paths (`/it/`, `/zh-tw/`, `/fa/`, etc.), and GSC indexes these alongside the primary-language original. An unfiltered ranking surfaced an Italian post, which the LLM (correctly) formatted in Italian — not appropriate for an English-audience LinkedIn/Facebook page. Fixed by excluding any URL whose first path segment matches `^[a-z]{2}(-[a-z]{2})?$` before ranking. Verified against real data (`blog.aspose.cloud`'s ~20 known locale prefixes all match; category paths like `pdf`, `cells`, `3d`, `html` do not).

## Consequences
- The "latest" strategy path is behavior-identical to before this change — verified via a live dry-run regression check.
- GSC strategy runs are slower than "latest" runs (one GSC API call plus a `fetch_post_by_url` call per skipped candidate) but this only matters for the scheduled 1x/week GSC run per brand, not every run.
- The regex-based locale filter is a heuristic, not a lookup against the blog's actual configured locales — a future non-English category slug that happens to be 2 letters could be wrongly excluded (none currently exist).

## Implementation Notes
- File: `agent_engine/social_agent/agent_logic/orchestrator.py`
- Tuning constants (`GSC_LOOKBACK_DAYS`, `GSC_LAG_DAYS`, `GSC_MAX_POSITION`, `GSC_MIN_IMPRESSIONS`, `GSC_CTR_CEILING`, `GSC_MIN_AGE_DAYS`) are module-level, not config-driven — adjust in code if the strategy needs retuning.
- `python-dateutil` used for parsing `published_date`, which comes from Hugo `<time>` tags or `article:published_time` meta in varying formats.

## References
- ADR-009, SPEC-007, SPEC-008
