# BlogCaster — Agent Overview

## What is BlogCaster?

BlogCaster is an MCP-based intelligent agent that automatically fetches blog posts via RSS feeds, transforms them into professional social media content using an LLM, and publishes them across multiple platforms including LinkedIn, X (Twitter), and Facebook. It runs autonomously on a daily schedule via GitHub Actions, systematically working through the entire blog catalog from newest to oldest — ensuring no post is ever shared twice.

---

## Architecture

BlogCaster follows the **Model Context Protocol (MCP)** architecture with independent MCP servers coordinated by a central orchestrator.

### Architecture Diagram

```
+------------------------------------------------------------------+
|                        GitHub Actions                            |
|                  (Scheduled: Weekdays 10 AM PKT)                 |
+----------------------------------+-------------------------------+
                                   |
                                   v
+------------------------------------------------------------------+
|                            CLI                                   |
|              Manual Mode  |  Auto Mode                           |
+----------------------------------+-------------------------------+
                                   |
                                   v
+------------------------------------------------------------------+
|                         Orchestrator                             |
|                                                                  |
|  Fetches blog content, formats via LLM, publishes to social      |
|  platforms, and tracks published history                         |
+---------+----------------+----------------+----------------------+
          |                |                |
          v                v                v
+-----------------+ +--------------+ +---------------------+
|   RSS Fetcher   | | Record Keeper| |   Social Posters    |
|   MCP Server    | | MCP Server   | |   MCP Servers       |
|                 | |              | |                     |
| Fetches and     | | Tracks all   | | +---------------+   |
| parses blog     | | published    | | |   LinkedIn    |   |
| posts from any  | | records to   | | +---------------+   |
| RSS/Atom feed   | | prevent      | | |   X (Twitter) |   |
|                 | | duplicates   | | +---------------+   |
|                 | |              | | |   Facebook    |   |
|                 | |              | | +---------------+   |
+--------+--------+ +------+------+ +---------+-----------+
         |                 |                   |
         v                 v                   v
   +-----------+    +--------------+    +----------------+
   | RSS Feeds |    | JSON Storage |    | Platform APIs  |
   +-----------+    +--------------+    +----------------+

               +---------------------+
               |     LLM Service     |
               |                     |
               | Transforms blog     |
               | content into        |
               | platform-specific   |
               | social media posts  |
               +---------------------+
```

### Component Breakdown

| Component | Role | Technology |
|---|---|---|
| **CLI** | Entry point with manual and auto modes | Python |
| **Orchestrator** | Workflow engine, coordinates all components | Python async |
| **RSS Fetcher MCP** | Parses RSS feeds, fetches blog post content | feedparser, httpx, BeautifulSoup |
| **Record Keeper MCP** | Tracks published posts, prevents duplicates | JSON storage |
| **LinkedIn Poster MCP** | Posts content to LinkedIn | httpx, LinkedIn REST API |
| **X Poster MCP** | Posts content to X (Twitter) | Planned |
| **Facebook Poster MCP** | Posts content to Facebook | Planned |
| **LLM Service** | Transforms blog content into social media posts | OpenAI-compatible SDK |
| **GitHub Actions** | Scheduled daily execution | Cron |

---

## How It Works

### Auto Mode (Daily Scheduled Run)

```
1. Fetch all posts from the RSS feed (newest first)
2. Load all published records into memory
3. Walk through posts newest-to-oldest:
   - Skip already published posts
   - Validate each candidate URL is a real blog post
   - Select first valid unpublished post
4. Send blog content to LLM for formatting
   - Produces: hook line + body + hashtags + blog URL
   - Validates output quality and retries if needed
5. Validate platform OAuth token
6. Publish formatted content to social platform
7. Save record to prevent future duplicates
8. Commit updated records back to repository
```

### Manual Mode

Accepts a specific blog URL, fetches its content, formats it via LLM, and publishes to the target platform. Auto-detects the blog platform from the URL.

---

## MCP Compliance

Each server follows the MCP specification:
- Built with **FastMCP** from the official MCP Python SDK
- Uses **stdio transport** (JSON-RPC over stdin/stdout)
- Tools are registered with typed parameters and structured returns
- Servers are **stateless and reusable** — any MCP client can connect to them independently

---

## Supported Blog Platforms

| Platform | Blog URL | Status |
|---|---|---|
| Aspose | blog.aspose.com | Active |
| GroupDocs | blog.groupdocs.com | Active |
| Conholdate | blog.conholdate.com | Active |

New blog platforms can be added via the platform registry configuration.

---

## Deployment

- **GitHub Actions**: Runs automatically on weekdays at 10:00 AM PKT
- **Manual Trigger**: Can be triggered from GitHub Actions UI
- **Local**: Can be run directly via CLI

---

## Key Safeguards

- **Duplicate prevention**: Never posts the same blog URL twice
- **URL validation**: Skips broken or template URLs by verifying page content before posting
- **LLM quality check**: Rejects truncated or low-quality outputs and retries automatically
- **Thinking tag handling**: Properly handles reasoning model outputs
- **Platform-safe formatting**: Avoids content patterns that cause rendering issues on social platforms

---

## Repository

https://github.com/mustafabutt/BlogCaster
