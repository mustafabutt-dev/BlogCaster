"""
LLM Service

Formats blog content into LinkedIn posts using the company's GPT-OSS LLM
via the OpenAI Python SDK (AsyncOpenAI).
"""

import logging
import re

from openai import AsyncOpenAI

from agent_engine.social_agent.config import settings
from agent_engine.social_agent.utils.prompts import LINKEDIN_SYSTEM_PROMPT, build_linkedin_prompt

logger = logging.getLogger("social_agent")

# Singleton client — initialized once
_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    """Get or create the singleton AsyncOpenAI client."""
    global _client
    if _client is None:
        if not settings.PROFESSIONALIZE_BASE_URL:
            raise ValueError("PROFESSIONALIZE_BASE_URL is not set")
        if not settings.PROFESSIONALIZE_API_KEY_2:
            raise ValueError("PROFESSIONALIZE_API_KEY_2 is not set")
        _client = AsyncOpenAI(
            base_url=settings.PROFESSIONALIZE_BASE_URL,
            api_key=settings.PROFESSIONALIZE_API_KEY_2,
        )
        logger.info("LLM client initialized")
    return _client


def _strip_thinking_tags(text: str) -> str:
    """Strip reasoning/thinking tags that some models embed in output.

    Reasoning models (e.g. DeepSeek R1) may wrap chain-of-thought in
    <think>...</think> tags within the content field. We only want the
    text that comes after the thinking block.
    """
    # Remove <think>...</think> blocks (greedy within block, across lines)
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    cleaned = cleaned.strip()
    # If stripping removed everything, return original (the model may not use tags)
    return cleaned if cleaned else text


def _strip_markdown(text: str) -> str:
    """Remove common markdown artifacts from LLM output."""
    # Remove bold markers
    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)
    # Remove italic markers
    text = re.sub(r"\*(.*?)\*", r"\1", text)
    # Remove heading markers
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    # Remove bullet point markers at line start
    text = re.sub(r"^[-*]\s+", "", text, flags=re.MULTILINE)
    return text.strip()


def _has_hashtags(text: str) -> bool:
    """Check if the text contains hashtags."""
    return bool(re.search(r"#\w+", text))


def _has_url(text: str, blog_url: str) -> bool:
    """Check if the text contains the blog URL."""
    return blog_url in text


def _ensure_hashtags_and_url(text: str, blog_url: str) -> str:
    """Append hashtags and/or blog URL if missing from the LLM output."""
    if not _has_hashtags(text):
        logger.warning("LLM output missing hashtags — appending defaults")
        text = text.rstrip() + "\n\n#TechBlog #Developer #Programming"

    if not _has_url(text, blog_url):
        logger.warning("LLM output missing blog URL — appending")
        text = text.rstrip() + "\n\n" + blog_url

    return text


async def format_for_linkedin(title: str, summary: str, blog_url: str) -> str:
    """Format blog post content into a professional LinkedIn post.

    Retries once if the model returns None content (common with reasoning
    models that exhaust output tokens on chain-of-thought).

    Args:
        title: Blog post title
        summary: Blog post summary (HTML already stripped)
        blog_url: URL of the blog post

    Returns:
        Formatted LinkedIn post text ready to publish

    Raises:
        ValueError: If LLM returns empty response after retries
    """
    client = _get_client()
    user_prompt = build_linkedin_prompt(title, summary, blog_url)

    logger.debug(f"LLM prompt: {user_prompt[:200]}...")

    min_words = 80
    max_attempts = 3
    result = None

    for attempt in range(1, max_attempts + 1):
        response = await client.chat.completions.create(
            model=settings.PROFESSIONALIZE_LLM_MODEL,
            messages=[
                {"role": "system", "content": LINKEDIN_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.7,
            max_tokens=4000,
        )

        if not response or not response.choices:
            raise ValueError("LLM returned empty response")

        content = response.choices[0].message.content

        if not content or not content.strip():
            logger.warning(
                f"LLM returned None/empty content (attempt {attempt}/{max_attempts}). "
                "Reasoning model likely spent all tokens on chain-of-thought."
            )
            continue

        # Strip thinking tags and markdown
        cleaned = _strip_thinking_tags(content)
        cleaned = _strip_markdown(cleaned)
        word_count = len(cleaned.split())

        if word_count >= min_words:
            result = cleaned
            logger.info(f"LLM returned valid post on attempt {attempt} ({word_count} words)")
            break

        logger.warning(
            f"LLM output too short (attempt {attempt}/{max_attempts}): "
            f"{word_count} words, need {min_words}+. Retrying..."
        )

    if not result:
        raise ValueError(
            f"LLM failed to produce a valid post after {max_attempts} attempts. "
            "Output was None, empty, or under 80 words each time."
        )

    # Ensure hashtags and URL are always present
    result = _ensure_hashtags_and_url(result, blog_url)

    word_count = len(result.split())
    logger.info(f"LLM formatted post ({word_count} words)")
    logger.debug(f"LLM output: {result}")

    return result
