# BlogCaster

A CLI-based agent that fetches blog posts from Hugo-based blog platforms via RSS feeds, formats them into platform-specific social media posts using an LLM, and publishes them to LinkedIn and X (Twitter).

The agent is platform-driven — each blog platform is registered in a JSON registry and the agent can operate independently per platform. Adding a new blog platform requires only a new entry in the registry file, no code changes.

## How It Works

```
RSS Feed ──> Record Check ──> Post Selection ──> LLM Formatting ──> LinkedIn + X Post ──> Record Save
```

Four FastMCP servers handle the core operations, coordinated by a central orchestrator:

| MCP Server | Role |
|---|---|
| **rss-fetcher** | Fetches and parses Hugo RSS feeds and individual blog posts |
| **record-keeper** | Tracks published posts in JSON, prevents duplicates |
| **linkedin-poster** | Posts formatted content to LinkedIn personal profile |
| **x-poster** | Posts formatted tweets to X (Twitter) via tweepy |

## Two Operating Modes

### Manual Mode

Provide a specific blog post URL. The agent auto-detects the platform, fetches the content, formats it, posts it to LinkedIn and X, and records the result. Also used to retry failed platforms for a previously posted URL.

```bash
python -m agent_engine.social_agent.main --url "https://blog.aspose.com/some-post"
```

### Auto Mode

Specify a platform ID. The agent fetches the RSS feed, picks the latest unpublished post, formats it, posts it to LinkedIn and X, and records the result.

```bash
python -m agent_engine.social_agent.main --auto --platform aspose
python -m agent_engine.social_agent.main --auto --platform groupdocs
python -m agent_engine.social_agent.main --auto --platform conholdate
```

## Prerequisites

- Python 3.10+
- A self-hosted GPT-OSS LLM endpoint (OpenAI-compatible API)
- A LinkedIn OAuth 2.0 access token with `w_member_social` scope
- X (Twitter) OAuth 1.0a credentials with Read and Write permissions

## Setup

### 1. Clone and navigate to the project

```bash
cd socialAgent
```

### 2. Install dependencies

```bash
pip install mcp feedparser httpx beautifulsoup4 aiofiles pydantic-settings openai tweepy
```

### 3. Configure environment variables

Copy the example file and fill in your credentials:

```bash
cp .env.example .env
```

Edit `.env` with your values:

```
# LLM Configuration (GPT-OSS)
PROFESSIONALIZE_BASE_URL=https://your-gpt-oss-endpoint.com/v1
PROFESSIONALIZE_API_KEY_2=your-api-key
PROFESSIONALIZE_LLM_MODEL=your-model-name

# LinkedIn Configuration
LINKEDIN_ACCESS_TOKEN=your-linkedin-oauth-token

# X (Twitter) Configuration
X_API_KEY=your-x-api-key
X_API_SECRET=your-x-api-secret
X_ACCESS_TOKEN=your-x-access-token
X_ACCESS_TOKEN_SECRET=your-x-access-token-secret
```

| Variable | Description |
|---|---|
| `PROFESSIONALIZE_BASE_URL` | Base URL of your OpenAI-compatible LLM endpoint |
| `PROFESSIONALIZE_API_KEY_2` | API key for the LLM endpoint |
| `PROFESSIONALIZE_LLM_MODEL` | Model name to use for text generation |
| `LINKEDIN_ACCESS_TOKEN` | Pre-generated LinkedIn OAuth 2.0 access token |
| `X_API_KEY` | X (Twitter) API consumer key |
| `X_API_SECRET` | X (Twitter) API consumer secret |
| `X_ACCESS_TOKEN` | X (Twitter) OAuth 1.0a access token |
| `X_ACCESS_TOKEN_SECRET` | X (Twitter) OAuth 1.0a access token secret |

## Usage

All commands must be run from the project root directory.

### Post a specific blog URL (Manual Mode)

```bash
python -m agent_engine.social_agent.main --url "https://blog.aspose.com/some-post"
```

### Post the latest unposted blog from a platform (Auto Mode)

```bash
python -m agent_engine.social_agent.main --auto --platform aspose
```

### List available platforms

```bash
python -m agent_engine.social_agent.main --auto
```

Output:

```
Error: --platform is required with --auto

Available platforms:
  - aspose          (Aspose Blog)
  - groupdocs       (GroupDocs Blog)
  - conholdate      (Conholdate Blog)
```

### Show usage help

```bash
python -m agent_engine.social_agent.main
```

## Adding a New Blog Platform

Edit `registry/platforms_registry.json` and add a new entry:

```json
{
  "id": "your-platform",
  "name": "Your Platform Blog",
  "url": "https://blog.yourplatform.com",
  "rss_feed": "https://blog.yourplatform.com/index.xml",
  "active": true
}
```

No code changes required. The new platform is immediately available:

```bash
python -m agent_engine.social_agent.main --auto --platform your-platform
```

## Project Structure

```
socialAgent/
├── agent_engine/
│   └── social_agent/
│       ├── main.py                  # CLI entry point
│       ├── config.py                # Pydantic BaseSettings config
│       ├── agent_logic/
│       │   └── orchestrator.py      # Core workflow (manual + auto modes)
│       ├── tools/
│       │   └── mcp_tools.py         # MCP server wrappers
│       └── utils/
│           ├── helpers.py           # Logger setup + registry helpers
│           ├── llm_service.py       # LLM formatting via OpenAI SDK
│           └── prompts.py           # Platform-specific prompt templates
├── mcp-servers/
│   ├── rss-fetcher/server.py        # RSS feed parsing (feedparser + httpx + bs4)
│   ├── linkedin-poster/server.py    # LinkedIn API posting (httpx)
│   ├── x-poster/server.py           # X (Twitter) API posting (tweepy)
│   └── record-keeper/server.py      # JSON-based record storage (aiofiles)
├── registry/
│   └── platforms_registry.json      # Blog platform registry
├── content/
│   └── records/
│       └── published_record.json    # Published post records
├── logs/
│   └── logs.txt                     # Application logs
├── .env                             # Credentials (not committed)
├── .env.example                     # Credential template
└── .gitignore
```

## Logs

All operations are logged to `logs/logs.txt` with timestamps. Console output shows INFO-level messages, the log file captures DEBUG-level detail.

```
2026-03-17 03:28:49 | INFO     | social_agent | Starting Auto Mode for platform: aspose
2026-03-17 03:28:50 | INFO     | social_agent | Fetched 10 posts from RSS feed
2026-03-17 03:28:51 | INFO     | social_agent | Selected unpublished post: "Convert OneNote..." — https://...
2026-03-17 03:28:58 | INFO     | social_agent | LLM formatted post (102 words)
2026-03-17 03:29:01 | INFO     | social_agent | LinkedIn post successful: post_id=urn:li:share:...
2026-03-17 03:29:01 | INFO     | social_agent | Record saved for https://...
```

## Duplicate Prevention & Per-Platform Retry

The agent tracks posting results per platform. In **Auto Mode**, any URL with an existing record is skipped — it always picks a fresh post. In **Manual Mode** (`--url`), if a URL was previously posted to some platforms but not all, the agent retries only the failed platforms.

URLs are normalized (lowercased, trailing slashes stripped, query parameters removed) to catch variations like:

- `https://blog.aspose.com/post/` vs `https://blog.aspose.com/post`
- `https://blog.aspose.com/post?utm=123` vs `https://blog.aspose.com/post`

Records are only saved when at least one platform succeeds. If all platforms fail, no record is written so the URL can be retried on the next run.

## Post Formats

### LinkedIn
- Professional tone, 150-200 words
- Hook line that grabs attention
- 3-5 relevant hashtags
- Blog URL at the end

### X (Twitter)
- One punchy sentence + 2-3 relevant hashtags
- Blog URL appended automatically
- Total tweet fits within 280 characters

## Troubleshooting

| Issue | Solution |
|---|---|
| `PROFESSIONALIZE_BASE_URL is not set` | Create `.env` file from `.env.example` and fill in LLM credentials |
| `LinkedIn token is expired or invalid (401)` | Generate a new LinkedIn OAuth token and update `.env` |
| `Insufficient permissions (403)` | Ensure your LinkedIn token has `w_member_social` scope |
| `All recent posts have already been shared` | All RSS feed posts are already in the record — wait for new blog posts |
| `X credentials have insufficient permissions (403)` | Regenerate X Access Token & Secret after enabling Read and Write permissions |
| `X API rate limit exceeded (429)` | Wait a few minutes and try again |
| `Platform 'xxx' not found` | Check `registry/platforms_registry.json` for available platform IDs |

## Future Developments

### Additional Social Media Platforms
- **Facebook** — Community-focused posts with casual tone and call-to-action
- **Medium / Dev.to** — Full article republishing (not just social snippets) for stronger SEO backlinks
- **Blogger / WordPress** — Cross-post full articles to blogging platforms for wider reach and backlink injection

### Performance Improvements
- **Parallel LLM calls** — Run `format_for_linkedin()` and `format_for_x()` concurrently via `asyncio.gather()` instead of sequentially, reducing total formatting time as more platforms are added
- **Content quality validation** — Pre-validate scraped content quality before sending to LLM, preventing wasted LLM calls on low-quality or garbage pages

### Architecture Enhancements
- **YAML-based prompt configuration** — Move platform prompts from code to YAML config files, enabling non-developers to tweak tone, length, and style without code changes
- **REST API wrapper** — Expose the orchestrator as HTTP endpoints via FastAPI, enabling integration with web interfaces and workflow automation tools
- **Lightweight connector pattern** — As platform count grows beyond 5+, evaluate a plugin-based connector architecture as an alternative to spinning up one MCP subprocess per platform

### Extensibility (No Code Changes)
| Goal | Change Required |
|---|---|
| Add a new blog platform | New entry in `registry/platforms_registry.json` |
| Add a web UI | FastAPI layer wrapping the existing MCP tools |
| Switch to a database | Replace `record-keeper/server.py` internals (same MCP interface) |
