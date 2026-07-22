# PROJECT CONTEXT — Social Media Agent

## Overview
A CLI-based agent that fetches blog posts from Hugo-based blog platforms via RSS feeds, formats them into professional social media posts using an LLM, and publishes them to LinkedIn and X (Twitter). The agent is platform-driven — each blog platform is registered in a JSON registry and the agent can operate independently per platform.

## Two Operating Modes
- **Manual Mode**: User provides a specific blog post URL. Agent auto-detects the platform, fetches content, formats, posts, and records.
- **Auto Mode**: User provides a platform ID. Agent fetches the RSS feed, picks the latest unpublished post, formats, posts, and records.

## Tech Stack
| Component | Technology |
|---|---|
| Language | Python |
| MCP Framework | FastMCP (stdio transport) |
| LLM | Self-hosted GPT-OSS via OpenAI Python SDK (AsyncOpenAI) |
| LinkedIn API | LinkedIn Personal Profile API (OAuth 2.0 pre-generated token) |
| X (Twitter) API | X API v2 via tweepy (OAuth 1.0a) |
| Dev.to API | Forem REST API v1 (API key auth) |
| Config | Pydantic BaseSettings + .env file |
| Data Source | Hugo RSS feeds |
| State Storage | JSON files (published_record.json) |
| Logging | Python logging → logs/logs.txt |

## Key Environment Variables
| Variable | Purpose |
|---|---|
| PROFESSIONALIZE_BASE_URL | GPT-OSS API endpoint |
| PROFESSIONALIZE_API_KEY_2 | GPT-OSS API key |
| PROFESSIONALIZE_LLM_MODEL | GPT-OSS model identifier |
| LINKEDIN_ACCESS_TOKEN | Pre-generated LinkedIn OAuth 2.0 token |
| X_API_KEY | X (Twitter) API consumer key |
| X_API_SECRET | X (Twitter) API consumer secret |
| X_ACCESS_TOKEN | X (Twitter) OAuth 1.0a access token |
| X_ACCESS_TOKEN_SECRET | X (Twitter) OAuth 1.0a access token secret |
| DEVTO_API_KEY | Dev.to personal API key |

## Architecture
Four FastMCP servers communicating via stdio, orchestrated by a central agent:
1. **rss-fetcher** — Fetches and parses Hugo RSS feeds and individual blog posts
2. **linkedin-poster** — Posts formatted content to LinkedIn personal profile
3. **x-poster** — Posts formatted tweets to X (Twitter) via tweepy
4. **devto-poster** — Publishes full markdown articles to Dev.to organization via Forem API
5. **record-keeper** — Tracks published posts in JSON, prevents duplicates
6. **gsc-fetcher** — Reads Google Search Console page performance (clicks/impressions/CTR/position) for the GSC-based selection strategy

## Directory Structure
```
social-media-agent/
├── agents/                          # Agent skill files
├── backlog/
│   ├── specs/                       # Atomic specifications
│   ├── tasks/                       # Task tracking
│   └── decisions/                   # Architecture Decision Records
├── agent_engine/
│   └── social_agent/
│       ├── main.py                  # CLI entry point
│       ├── config.py                # Pydantic BaseSettings config
│       ├── agent_logic/
│       │   └── orchestrator.py      # Core workflow for both modes
│       ├── tools/
│       │   └── mcp_tools.py         # MCP tool wrappers
│       └── utils/
│           ├── helpers.py           # Logger + utilities
│           └── prompts.py           # LLM prompt builders
├── mcp-servers/
│   ├── rss-fetcher/server.py
│   ├── linkedin-poster/server.py
│   ├── x-poster/server.py
│   └── record-keeper/server.py
├── registry/
│   └── platforms_registry.json
├── content/
│   └── records/
│       └── published_record.json
├── logs/
│   └── logs.txt
└── PROJECT_CONTEXT.md
```

## Platform Registry
Platforms registered in `registry/platforms_registry.json`:
- **aspose** — https://blog.aspose.com
- **groupdocs** — https://blog.groupdocs.com
- **conholdate** — https://blog.conholdate.com

Adding a new platform = new JSON entry only, no code change.

## Stage Tracker
| Stage | Description | Status |
|---|---|---|
| Stage 1 | Foundation — PROJECT_CONTEXT, agents, specs, ADRs | COMPLETE |
| Stage 2 | RSS Fetcher MCP Server | COMPLETE |
| Stage 3 | Record Keeper MCP Server | COMPLETE |
| Stage 4 | LinkedIn Poster MCP Server | COMPLETE |
| Stage 5 | Orchestrator + CLI | COMPLETE |
| Stage 6 | Integration + Docs | COMPLETE |
| Stage 7 | X (Twitter) Poster Integration | COMPLETE |
| Stage 8 | Dev.to Poster Integration | COMPLETE |
| Stage 9 | GSC Fetcher MCP Server | COMPLETE (live-tested against blog.aspose.cloud, 12,784 pages) |
| Stage 10 | GSC Selection Strategy (orchestrator + CLI) | COMPLETE (live-tested; `--strategy latest` regression-checked) |

## Decision Log
| ID | Decision | Rationale |
|---|---|---|
| D-001 | FastMCP with stdio transport | CLI tool, subprocess communication is simplest |
| D-002 | OpenAI Python SDK for LLM | Company's GPT-OSS is OpenAI-compatible |
| D-003 | Pydantic BaseSettings + .env | Matches existing agent patterns, type-safe config |
| D-004 | Pre-generated LinkedIn token | Simplest auth approach for CLI tool |
| D-005 | JSON file storage | Simple, no DB dependency, future web UI can read same files |
| D-006 | tweepy for X API | OAuth 1.0a signing required for X API v2 posting |
| D-007 | Independent platform failures | LinkedIn failure doesn't block X and vice versa |
| D-008 | Dev.to publishes full articles | Dev.to is a content platform — LLM generates a 400-600 word markdown article (not a social snippet), with canonical_url pointing to the original blog for SEO |
| D-009 | devto_org_id per platform in registry | Each blog platform can map to its own Dev.to org; null means Dev.to skipped for that platform |
| D-010 | LinkedIn posts carry an article card | Clickable link-preview card (title + description + thumbnail) drives more blog clicks than a raw URL line and guarantees the link is always visible. LinkedIn doesn't scrape URLs, so the thumbnail is uploaded via the Images API; og:image is HEAD-verified with fallback to the first in-article image (some Hugo themes emit broken og:image). The raw URL line is stripped from LinkedIn commentary since the card carries the (UTM-tagged) link |
| D-011 | Facebook posts are photo posts when an image is available | The blogs' broken og:image means Facebook's link-card scraper finds no image, so link posts render without one. Photo posts (/photos with url+caption) show the verified featured image; the UTM blog URL stays in the caption as a clickable link. Falls back to a link post when no image is found. Proper long-term fix is repairing og:image in the Hugo theme (helps all platforms) |
| D-012 | Dev.to articles carry main_image + clean canonical_url | Cover image (same verified featured image) shows in the Dev.to feed. Bug fix: canonical_url was accepted but never sent in the payload — all pre-2026-07-10 articles lack it (backfill possible via PUT /articles/{id}). Canonical uses the clean blog URL, never the UTM-tagged one, so search engines index the true article location; the teaser CTA link keeps UTM for analytics |
| D-013 | Shorter social post targets: LinkedIn 60-100 words, Facebook 30-60 words | Since D-010/D-011 the article card/photo already carries title+image, so long commentary duplicated it. LinkedIn folds text after ~210 chars, Facebook after ~125 — hook must be front-loaded, and prompts now forbid restating the title. Validation floors in llm_service.py lowered to match (LinkedIn 40, Facebook 20; old 80-word floor would have rejected every valid Facebook post). Dev.to (400-600 words) and X unchanged |
| D-014 | GSC Fetcher queries page-level stats via direct REST + google-auth (no google-api-python-client) | RSS only exposes ~10-20 latest posts, but a GSC-driven "pick underperforming content" strategy needs the site's entire indexed history, so RSS is bypassed entirely for this strategy — `fetch_post_by_url` (already used by Manual Mode) fetches content for whichever URL GSC surfaces, regardless of age. Querying with `dimensions: ["page"]` gets GSC's own per-page aggregation for free, avoiding manual query-level rollups. Reused the existing `sheet-reader` service account (already granted GSC property access) rather than provisioning a new one. Filtering (position/impressions/recency) and ranking are intentionally left to the orchestrator, not this server — mirrors the rss-fetcher/orchestrator split |
| D-015 | GSC selection strategy excludes locale-prefixed paths (`/it/`, `/zh-tw/`, `/fa/`, etc.) | Live-testing surfaced an Italian-language post as the top GSC candidate — the blog indexes translated copies of posts under locale-prefixed paths, and GSC ranks them alongside the English original. The LLM correctly formatted the post in Italian, which is wrong for an English-audience LinkedIn/Facebook page. Fixed with a regex filter (`^[a-z]{2}(-[a-z]{2})?$` on the first path segment) validated against real `blog.aspose.cloud` data (~20 locale prefixes match, category paths like `pdf`/`cells`/`3d` don't) |

## Current State
- ALL STAGES COMPLETE
- Stage 1 COMPLETE — Foundation (PROJECT_CONTEXT, agents, specs, ADRs)
- Stage 2 COMPLETE — RSS Fetcher MCP Server (3 tools, tested live)
- Stage 3 COMPLETE — Record Keeper MCP Server (4 tools, 10 tests passed)
- Stage 4 COMPLETE — LinkedIn Poster MCP Server (2 tools, 6 tests passed)
- Stage 5 COMPLETE — Orchestrator + CLI (config, helpers, prompts, LLM service, MCP wrappers, orchestrator, CLI)
- Stage 6 COMPLETE — Integration tested end-to-end, 3 successful LinkedIn posts
- Stage 7 COMPLETE — X (Twitter) Poster MCP server + dual-platform orchestrator
- Stage 8 COMPLETE — Dev.to Poster MCP server; asposecloud org (ID 13759) wired to aspose-cloud platform
- LinkedIn article cards (D-010) implemented — dry-run verified, NOT yet committed/pushed or tested live

## Integration Test Results
| Test | Post ID | Status |
|---|---|---|
| Auto Mode (aspose) — 1st run | urn:li:share:7439437595735961600 | SUCCESS |
| Auto Mode (aspose) — 2nd run (duplicate skip) | urn:li:share:7439437757216882688 | SUCCESS |
| Manual Mode (groupdocs) | urn:li:share:7439437862250405888 | SUCCESS |
| Manual Mode duplicate check | N/A — correctly skipped | SUCCESS |

## Last Updated
2026-07-23 — Stage 10 complete: GSC selection strategy wired into the orchestrator (D-014, D-015). `--strategy gsc` on `--auto` ranks GSC pages by impressions/CTR/position, filters out already-published/too-new/non-English-locale pages, and feeds the same downstream pipeline as `--strategy latest` (which was regression-tested unchanged after the refactor). Live-tested end-to-end against blog.aspose.cloud, including catching and fixing the locale-path issue (D-015) mid-test.
Adds new dependency `python-dateutil` (already present locally; not yet added to the CI workflows' pip install line — needed before `--strategy gsc` can run in GitHub Actions).
Not yet built: workflow schedule change (2nd weekly run per active brand uses GSC strategy instead of latest) — everything currently must be triggered manually with `--strategy gsc`.
All Stage 9/10 changes are uncommitted — user asked not to commit until explicitly told to.
2026-07-16 — Shorter post lengths (D-013): LinkedIn 60-100 words, Facebook 30-60 words; prompts rewritten to front-load the hook and not restate the title; llm_service.py validation floors lowered (LinkedIn 40, Facebook 20). Dry-run verified on aspose for both platforms. NOT committed or pushed.
2026-07-10 — LinkedIn article cards (D-010), Facebook photo posts (D-011), and Dev.to cover image + canonical fix (D-012) all live-tested OK. --no-metrics CLI flag added. All changes local only — NOT committed or pushed.
X posting is ON HOLD: X API now demands paid credits, so X posts stopped (explains missing X entries in recent records). No X work planned until that changes.
Open items: (1) optional per-platform default banner for imageless posts; (2) backfill canonical_url on ~40 old Dev.to articles
