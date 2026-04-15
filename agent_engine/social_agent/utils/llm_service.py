"""
LLM Service

Formats blog content into social media posts (LinkedIn, X) using the
company's GPT-OSS LLM via the OpenAI Python SDK (AsyncOpenAI).
"""

import logging
import re
from dataclasses import dataclass

from openai import AsyncOpenAI

from agent_engine.social_agent.config import settings
from agent_engine.social_agent.utils.prompts import (
    FACEBOOK_SYSTEM_PROMPT,
    LINKEDIN_SYSTEM_PROMPT,
    X_SYSTEM_PROMPT,
    build_facebook_prompt,
    build_linkedin_prompt,
    build_x_prompt,
)

logger = logging.getLogger("social_agent")


@dataclass
class LLMResult:
    """Result from an LLM format call, including token usage."""

    text: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    api_call_count: int  # number of LLM API calls (including retries)


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


async def format_for_linkedin(title: str, summary: str, blog_url: str) -> LLMResult:
    """Format blog post content into a professional LinkedIn post.

    Retries once if the model returns None content (common with reasoning
    models that exhaust output tokens on chain-of-thought).

    Args:
        title: Blog post title
        summary: Blog post summary (HTML already stripped)
        blog_url: URL of the blog post

    Returns:
        LLMResult with formatted text and token usage

    Raises:
        ValueError: If LLM returns empty response after retries
    """
    client = _get_client()
    user_prompt = build_linkedin_prompt(title, summary, blog_url)

    logger.debug(f"LLM prompt: {user_prompt[:200]}...")

    min_words = 80
    max_attempts = 3
    result = None
    total_input_tokens = 0
    total_output_tokens = 0
    total_tokens = 0
    api_call_count = 0

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
        api_call_count += 1

        if response.usage:
            total_input_tokens += response.usage.prompt_tokens
            total_output_tokens += response.usage.completion_tokens
            total_tokens += response.usage.total_tokens

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

    return LLMResult(
        text=result,
        input_tokens=total_input_tokens,
        output_tokens=total_output_tokens,
        total_tokens=total_tokens,
        api_call_count=api_call_count,
    )


async def format_for_facebook(title: str, summary: str, blog_url: str) -> LLMResult:
    """Format blog post content into a Facebook Page post.

    Same retry pattern as LinkedIn — retries up to 3 times if the model
    returns None content or output under 80 words.

    Args:
        title: Blog post title
        summary: Blog post summary (HTML already stripped)
        blog_url: URL of the blog post

    Returns:
        LLMResult with formatted text and token usage

    Raises:
        ValueError: If LLM returns empty response after retries
    """
    client = _get_client()
    user_prompt = build_facebook_prompt(title, summary, blog_url)

    logger.debug(f"Facebook LLM prompt: {user_prompt[:200]}...")

    min_words = 80
    max_attempts = 3
    result = None
    total_input_tokens = 0
    total_output_tokens = 0
    total_tokens = 0
    api_call_count = 0

    for attempt in range(1, max_attempts + 1):
        response = await client.chat.completions.create(
            model=settings.PROFESSIONALIZE_LLM_MODEL,
            messages=[
                {"role": "system", "content": FACEBOOK_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.7,
            max_tokens=4000,
        )
        api_call_count += 1

        if response.usage:
            total_input_tokens += response.usage.prompt_tokens
            total_output_tokens += response.usage.completion_tokens
            total_tokens += response.usage.total_tokens

        if not response or not response.choices:
            raise ValueError("LLM returned empty response")

        content = response.choices[0].message.content

        if not content or not content.strip():
            logger.warning(
                f"LLM returned None/empty content for Facebook (attempt {attempt}/{max_attempts}). "
                "Reasoning model likely spent all tokens on chain-of-thought."
            )
            continue

        # Strip thinking tags and markdown
        cleaned = _strip_thinking_tags(content)
        cleaned = _strip_markdown(cleaned)
        word_count = len(cleaned.split())

        if word_count >= min_words:
            result = cleaned
            logger.info(f"LLM returned valid Facebook post on attempt {attempt} ({word_count} words)")
            break

        logger.warning(
            f"LLM output too short for Facebook (attempt {attempt}/{max_attempts}): "
            f"{word_count} words, need {min_words}+. Retrying..."
        )

    if not result:
        raise ValueError(
            f"LLM failed to produce a valid Facebook post after {max_attempts} attempts. "
            "Output was None, empty, or under 80 words each time."
        )

    # Ensure hashtags and URL are always present
    result = _ensure_hashtags_and_url(result, blog_url)

    word_count = len(result.split())
    logger.info(f"Facebook formatted post ({word_count} words)")
    logger.debug(f"Facebook LLM output: {result}")

    return LLMResult(
        text=result,
        input_tokens=total_input_tokens,
        output_tokens=total_output_tokens,
        total_tokens=total_tokens,
        api_call_count=api_call_count,
    )


MAX_TWEET_LENGTH = 280


def _truncate_to_char_limit(text: str, max_chars: int) -> str:
    """Truncate text to fit within a character limit, breaking at word boundary."""
    if len(text) <= max_chars:
        return text
    truncated = text[:max_chars]
    # Break at last space to avoid cutting mid-word
    last_space = truncated.rfind(" ")
    if last_space > 0:
        truncated = truncated[:last_space]
    return truncated.rstrip(".,;:!? ")


def _ensure_url(text: str, blog_url: str) -> str:
    """Ensure the blog URL is appended to the tweet text."""
    if blog_url in text:
        return text
    # Calculate available space: total - url - space separator
    url_with_space = " " + blog_url
    max_text_chars = MAX_TWEET_LENGTH - len(url_with_space)
    text = _truncate_to_char_limit(text.rstrip(), max_text_chars)
    return text + url_with_space


async def format_for_x(title: str, summary: str, blog_url: str) -> LLMResult:
    """Format blog post content into a tweet for X (Twitter).

    Generates a single punchy sentence + URL that fits within 280 characters.

    Args:
        title: Blog post title
        summary: Blog post summary (HTML already stripped)
        blog_url: URL of the blog post

    Returns:
        LLMResult with formatted text and token usage

    Raises:
        ValueError: If LLM returns empty response after retries
    """
    client = _get_client()
    user_prompt = build_x_prompt(title, summary, blog_url)

    logger.debug(f"X LLM prompt: {user_prompt[:200]}...")

    max_attempts = 3
    result = None
    total_input_tokens = 0
    total_output_tokens = 0
    total_tokens = 0
    api_call_count = 0

    for attempt in range(1, max_attempts + 1):
        response = await client.chat.completions.create(
            model=settings.PROFESSIONALIZE_LLM_MODEL,
            messages=[
                {"role": "system", "content": X_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.7,
            max_tokens=4000,
        )
        api_call_count += 1

        if response.usage:
            total_input_tokens += response.usage.prompt_tokens
            total_output_tokens += response.usage.completion_tokens
            total_tokens += response.usage.total_tokens

        if not response or not response.choices:
            raise ValueError("LLM returned empty response")

        content = response.choices[0].message.content

        if not content or not content.strip():
            logger.warning(
                f"LLM returned None/empty content for X (attempt {attempt}/{max_attempts}). "
                "Reasoning model likely spent all tokens on chain-of-thought."
            )
            continue

        # Strip thinking tags and markdown
        cleaned = _strip_thinking_tags(content)
        cleaned = _strip_markdown(cleaned)
        # Remove URL if the LLM included it (we append it ourselves)
        cleaned = cleaned.replace(blog_url, "").strip()

        if len(cleaned) > 0:
            result = cleaned
            logger.info(f"LLM returned valid tweet on attempt {attempt} ({len(cleaned)} chars)")
            break

        logger.warning(f"LLM output empty after cleaning (attempt {attempt}/{max_attempts}). Retrying...")

    if not result:
        raise ValueError(
            f"LLM failed to produce a valid tweet after {max_attempts} attempts. "
            "Output was None or empty each time."
        )

    # Ensure URL is present and total length fits in 280 chars
    result = _ensure_url(result, blog_url)

    logger.info(f"X formatted tweet ({len(result)} chars)")
    logger.debug(f"X LLM output: {result}")

    return LLMResult(
        text=result,
        input_tokens=total_input_tokens,
        output_tokens=total_output_tokens,
        total_tokens=total_tokens,
        api_call_count=api_call_count,
    )
