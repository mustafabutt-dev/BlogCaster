# BlogCaster

A CLI-based agent that fetches blog posts from Hugo-based blog platforms via RSS feeds, formats them into platform-specific social media posts using an LLM, and publishes them to LinkedIn, X (Twitter), and Facebook.

The agent is platform-driven — each blog platform is registered in a JSON registry and the agent can operate independently per platform. Adding a new blog platform requires only a new entry in the registry file, no code changes.

## How It Works

```
RSS Feed ──> Record Check ──> Post Selection ──> LLM Formatting ──> LinkedIn + X + Facebook Post ──> Record Save
```

Five FastMCP servers handle the core operations, coordinated by a central orchestrator:

| MCP Server | Role |
|---|---|
| **rss-fetcher** | Fetches and parses Hugo RSS feeds and individual blog posts |
| **record-keeper** | Tracks published posts in JSON, prevents duplicates |
| **linkedin-poster** | Posts formatted content to LinkedIn personal profile |
| **x-poster** | Posts formatted tweets to X (Twitter) via tweepy |
| **facebook-poster** | Posts formatted content to a Facebook Page via Graph API |

## Two Operating Modes

### Manual Mode

Provide a specific blog post URL. The agent auto-detects the platform, fetches the content, formats it, posts it to LinkedIn, X, and Facebook, and records the result. Also used to retry failed platforms for a previously posted URL.

```bash
python -m agent_engine.social_agent.main --url "https://blog.aspose.com/some-post"
```

### Auto Mode

Specify a platform ID. The agent fetches the RSS feed, picks the latest unpublished post, formats it, posts it to LinkedIn, X, and Facebook, and records the result.

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
- A Facebook Page Access Token with `pages_read_engagement` and `pages_manage_posts` permissions

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

# Facebook Page Configuration
FACEBOOK_PAGE_ID=your-facebook-page-id
FACEBOOK_PAGE_ACCESS_TOKEN=your-facebook-page-access-token
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
| `FACEBOOK_PAGE_ID` | Facebook Page numeric ID |
| `FACEBOOK_PAGE_ACCESS_TOKEN` | Facebook Page Access Token (not User token) |

## Facebook Page Setup

Facebook requires a **Page Access Token** (not a User Access Token) to post to a Page. Follow these steps:

### Step 1: Create a Facebook App

1. Go to [Facebook Developers](https://developers.facebook.com/) and create an app (type: Business)
2. Add the "Facebook Login for Business" product to your app

### Step 2: Get a User Access Token

1. Go to the [Graph API Explorer](https://developers.facebook.com/tools/explorer/)
2. Select your app from the dropdown
3. Click "Generate Access Token"
4. Grant these permissions: `pages_read_engagement`, `pages_manage_posts`

### Step 3: Exchange for a Page Access Token

The User token gives you access to your Pages, but you need the **Page's own token** to post. Run:

```bash
curl "https://graph.facebook.com/v21.0/me/accounts?access_token=YOUR_USER_TOKEN"
```

This returns a list of Pages you manage:

```json
{
  "data": [
    {
      "access_token": "EAAxxxxx_PAGE_TOKEN_xxxxx",
      "name": "Your Page Name",
      "id": "123456789012345"
    }
  ]
}
```

Copy the `access_token` and `id` from the Page entry.

### Step 4: Verify the Page Token

```bash
curl "https://graph.facebook.com/v21.0/me?access_token=YOUR_PAGE_TOKEN"
```

This should return the **Page's** name and ID (not your personal name). If it shows the Page name, the token is correct.

### Step 5: Update `.env`

```
FACEBOOK_PAGE_ID=123456789012345
FACEBOOK_PAGE_ACCESS_TOKEN=EAAxxxxx_PAGE_TOKEN_xxxxx
```

### Step 6: Test

```bash
python -m agent_engine.social_agent.main --url "https://blog.aspose.com/some-post" --target facebook
```

### Common Mistake: Using a User Token Instead of a Page Token

If you see this error:

```
Insufficient permissions to post: (#200) If posting to a group, requires app being
installed in the group...
```

You are using a **User Access Token** instead of a **Page Access Token**. Go back to Step 3 and use the `me/accounts` endpoint to get the Page's own token.

### Token Expiration & Long-Lived Tokens

Tokens from the Graph API Explorer expire in ~1 hour. For production use, exchange for a **long-lived token** (~60 days):

**1. Exchange short-lived User Token for a long-lived User Token:**

```bash
curl -G "https://graph.facebook.com/v19.0/oauth/access_token" \
  --data-urlencode "grant_type=fb_exchange_token" \
  --data-urlencode "client_id=YOUR_APP_ID" \
  --data-urlencode "client_secret=YOUR_APP_SECRET" \
  --data-urlencode "fb_exchange_token=YOUR_SHORT_LIVED_USER_TOKEN"
```

Response:

```json
{
  "access_token": "LONG_LIVED_USER_TOKEN",
  "token_type": "bearer",
  "expires_in": 5183423
}
```

`expires_in` is in seconds (~60 days).

**2. Exchange long-lived User Token for a Page Token:**

```bash
curl "https://graph.facebook.com/v19.0/me/accounts?access_token=LONG_LIVED_USER_TOKEN"
```

The Page Access Token returned from a long-lived User Token **does not expire**. Copy the `access_token` and `id` from your Page entry and update `.env` / GitHub Actions secrets.

**3. Verify your token:**

```bash
curl "https://graph.facebook.com/v19.0/debug_token?input_token=YOUR_PAGE_TOKEN&access_token=YOUR_APP_ID|YOUR_APP_SECRET"
```

Check `expires_at` — a value of `0` means the token never expires.

**Security notes:**
- Never expose `client_secret` in frontend code
- Store tokens in environment variables or GitHub Actions secrets
- Rotate credentials immediately if exposed

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

### Target a specific social media platform

```bash
# Post to Facebook only
python -m agent_engine.social_agent.main --url "https://blog.aspose.com/some-post" --target facebook

# Post to LinkedIn only
python -m agent_engine.social_agent.main --url "https://blog.aspose.com/some-post" --target linkedin

# Post to X only
python -m agent_engine.social_agent.main --url "https://blog.aspose.com/some-post" --target x

# Post to all platforms (default)
python -m agent_engine.social_agent.main --url "https://blog.aspose.com/some-post" --target all
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
│   ├── facebook-poster/server.py    # Facebook Page posting (httpx + Graph API)
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

### Facebook
- Community-focused, friendly conversational tone, 150-200 words
- Curiosity-driven hook line
- Clear call-to-action (read the article, share thoughts, tag someone)
- 3-5 relevant hashtags
- Blog URL attached as a link

## Troubleshooting

| Issue | Solution |
|---|---|
| `PROFESSIONALIZE_BASE_URL is not set` | Create `.env` file from `.env.example` and fill in LLM credentials |
| `LinkedIn token is expired or invalid (401)` | Generate a new LinkedIn OAuth token and update `.env` |
| `Insufficient permissions (403)` | Ensure your LinkedIn token has `w_member_social` scope |
| `All recent posts have already been shared` | All RSS feed posts are already in the record — wait for new blog posts |
| `X credentials have insufficient permissions (403)` | Regenerate X Access Token & Secret after enabling Read and Write permissions |
| `X API rate limit exceeded (429)` | Wait a few minutes and try again |
| `Facebook token is expired or invalid` | Get a new Page Access Token (see Facebook Page Setup above) |
| `Insufficient permissions to post: (#200)` | You are using a User token instead of a Page token — use `me/accounts` to get the Page token |
| `Facebook API rate limit exceeded` | Wait a few minutes and try again |
| `Platform 'xxx' not found` | Check `registry/platforms_registry.json` for available platform IDs |

## Future Developments

### Additional Social Media Platforms
- **Medium / Dev.to** — Full article republishing (not just social snippets) for stronger SEO backlinks
- **Blogger / WordPress** — Cross-post full articles to blogging platforms for wider reach and backlink injection

### Performance Improvements
- **Parallel LLM calls** — Run `format_for_linkedin()`, `format_for_x()`, and `format_for_facebook()` concurrently via `asyncio.gather()` instead of sequentially, reducing total formatting time as more platforms are added
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
