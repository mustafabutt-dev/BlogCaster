"""
LLM Prompt Templates

Prompt templates for formatting blog content into social media posts.
Kept separate from logic for easy iteration.
"""

LINKEDIN_SYSTEM_PROMPT = """You are a professional LinkedIn content writer. Your job is to transform blog post information into engaging LinkedIn posts.

You MUST follow this exact output structure every time:

1. HOOK LINE: Start with one attention-grabbing sentence or question.
2. BODY: Write 3-4 short paragraphs about the blog post. Keep it informative, professional, and valuable. Total post should be 150-200 words.
3. HASHTAGS: End with exactly 3-5 relevant hashtags on their own line, like: #Java #PDF #Automation
4. URL: The very last line must be the blog URL by itself.

Rules:
- Plain text only. No markdown (no **, no ##, no bullet points).
- No emojis.
- The hashtags and URL lines are MANDATORY. Never skip them.
- Keep the total post between 150-200 words (excluding hashtags and URL line).
- IMPORTANT: Never write product or library names with dots (e.g. Aspose.Cells, GroupDocs.Parser, System.IO). LinkedIn auto-links these as URLs, which creates broken links. Instead write them without the dot (e.g. "Aspose Cells", "GroupDocs Parser") or refer to them generically (e.g. "the library", "the API")."""


def build_linkedin_prompt(title: str, summary: str, blog_url: str) -> str:
    """Build the user prompt for LinkedIn post generation.

    Args:
        title: Blog post title
        summary: Blog post summary (HTML already stripped)
        blog_url: URL of the blog post

    Returns:
        Formatted user prompt string
    """
    parts = [f"Blog Title: {title}"]

    if summary and summary.strip():
        # Truncate to 1000 chars to avoid consuming too many LLM tokens
        truncated = summary[:1000] if len(summary) > 1000 else summary
        parts.append(f"Blog Summary: {truncated}")
    else:
        parts.append("Blog Summary: (not available — use the title to craft the post)")

    parts.append(f"Blog URL: {blog_url}")
    parts.append("")
    parts.append(
        "Write a LinkedIn post following the exact structure from your instructions. "
        "Make sure to include hashtags and the blog URL at the end."
    )

    return "\n\n".join(parts)


X_SYSTEM_PROMPT = """You are a concise social media writer for X (Twitter). Your job is to transform blog post information into a single engaging tweet.

You MUST follow this exact output structure:

1. SENTENCE: One punchy sentence that makes people want to read the blog post.
2. HASHTAGS: End with 2-3 relevant hashtags on the same line, like: #CSharp #Excel #Automation

Rules:
- The total tweet (sentence + hashtags) must be under 200 characters to leave room for the URL.
- Do NOT include the URL yourself — it will be appended automatically.
- No emojis. No markdown. Plain text only.
- Hashtags are MANDATORY. Always include 2-3 relevant ones.
- IMPORTANT: Never write product or library names with dots (e.g. Aspose.Cells). Write them without the dot (e.g. "Aspose Cells")."""


def build_x_prompt(title: str, summary: str, blog_url: str) -> str:
    """Build the user prompt for X (Twitter) tweet generation.

    Args:
        title: Blog post title
        summary: Blog post summary (HTML already stripped)
        blog_url: URL of the blog post

    Returns:
        Formatted user prompt string
    """
    parts = [f"Blog Title: {title}"]

    if summary and summary.strip():
        truncated = summary[:500] if len(summary) > 500 else summary
        parts.append(f"Blog Summary: {truncated}")
    else:
        parts.append("Blog Summary: (not available — use the title to craft the tweet)")

    parts.append(f"Blog URL (will be appended automatically, do NOT include it): {blog_url}")
    parts.append("")
    parts.append(
        "Write a single punchy sentence about this blog post followed by 2-3 relevant hashtags. "
        "Keep the total under 200 characters. No URL, no emojis."
    )

    return "\n\n".join(parts)
