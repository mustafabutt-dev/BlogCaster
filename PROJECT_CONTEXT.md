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

## Architecture
Four FastMCP servers communicating via stdio, orchestrated by a central agent:
1. **rss-fetcher** — Fetches and parses Hugo RSS feeds and individual blog posts
2. **linkedin-poster** — Posts formatted content to LinkedIn personal profile
3. **x-poster** — Posts formatted tweets to X (Twitter) via tweepy
4. **record-keeper** — Tracks published posts in JSON, prevents duplicates

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

## Current State
- ALL STAGES COMPLETE
- Stage 1 COMPLETE — Foundation (PROJECT_CONTEXT, agents, specs, ADRs)
- Stage 2 COMPLETE — RSS Fetcher MCP Server (3 tools, tested live)
- Stage 3 COMPLETE — Record Keeper MCP Server (4 tools, 10 tests passed)
- Stage 4 COMPLETE — LinkedIn Poster MCP Server (2 tools, 6 tests passed)
- Stage 5 COMPLETE — Orchestrator + CLI (config, helpers, prompts, LLM service, MCP wrappers, orchestrator, CLI)
- Stage 6 COMPLETE — Integration tested end-to-end, 3 successful LinkedIn posts
- Stage 7 COMPLETE — X (Twitter) Poster MCP server + dual-platform orchestrator

## Integration Test Results
| Test | Post ID | Status |
|---|---|---|
| Auto Mode (aspose) — 1st run | urn:li:share:7439437595735961600 | SUCCESS |
| Auto Mode (aspose) — 2nd run (duplicate skip) | urn:li:share:7439437757216882688 | SUCCESS |
| Manual Mode (groupdocs) | urn:li:share:7439437862250405888 | SUCCESS |
| Manual Mode duplicate check | N/A — correctly skipped | SUCCESS |

## Last Updated
2026-04-01 — Stage 7 completed, X (Twitter) support added, dual-platform posting
