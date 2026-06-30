"""
Logger Setup and Utilities

Centralized logger configuration for the Social Media Agent.
Logs to both file (DEBUG) and console (INFO) with colored output.
"""

import json
import logging
import os


# ANSI color codes
class _Colors:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    GRAY = "\033[90m"


_LEVEL_COLORS = {
    logging.DEBUG: _Colors.GRAY,
    logging.INFO: _Colors.GREEN,
    logging.WARNING: _Colors.YELLOW,
    logging.ERROR: _Colors.RED,
    logging.CRITICAL: _Colors.RED + _Colors.BOLD,
}


class ColorFormatter(logging.Formatter):
    """Logging formatter that adds ANSI colors to console output."""

    def format(self, record: logging.LogRecord) -> str:
        color = _LEVEL_COLORS.get(record.levelno, _Colors.RESET)
        timestamp = self.formatTime(record, self.datefmt)

        level = f"{color}{record.levelname:<8}{_Colors.RESET}"
        name = f"{_Colors.CYAN}{record.name}{_Colors.RESET}"
        msg = record.getMessage()

        return f"{_Colors.GRAY}{timestamp}{_Colors.RESET} | {level} | {name} | {msg}"


def setup_logger(log_path: str = "logs/logs.txt") -> logging.Logger:
    """Set up the centralized logger with file and console handlers.

    Args:
        log_path: Path to the log file

    Returns:
        Configured logger instance
    """
    os.makedirs(os.path.dirname(log_path), exist_ok=True)

    logger = logging.getLogger("social_agent")
    logger.setLevel(logging.DEBUG)

    # Avoid duplicate handlers if called multiple times
    if logger.handlers:
        return logger

    # File handler — all logs (DEBUG and above), plain text
    file_handler = logging.FileHandler(log_path)
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(file_formatter)

    # Console handler — INFO and above, colored
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(ColorFormatter(datefmt="%Y-%m-%d %H:%M:%S"))

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger


def load_registry(registry_path: str) -> dict:
    """Load the platform registry from a JSON file.

    Args:
        registry_path: Absolute path to platforms_registry.json

    Returns:
        Parsed registry dict with 'platforms' key
    """
    with open(registry_path, "r") as f:
        return json.load(f)


def find_platform_by_id(registry: dict, platform_id: str) -> dict | None:
    """Find a platform in the registry by its ID.

    Args:
        registry: Parsed registry dict
        platform_id: Platform ID to find

    Returns:
        Platform dict or None if not found
    """
    for platform in registry.get("platforms", []):
        if platform["id"] == platform_id:
            return platform
    return None


def detect_platform_from_url(registry: dict, url: str) -> dict | None:
    """Auto-detect a platform from a blog post URL.

    Matches the URL against registered platform base URLs.

    Args:
        registry: Parsed registry dict
        url: Blog post URL to match

    Returns:
        Matching platform dict or None
    """
    url_lower = url.lower()
    for platform in registry.get("platforms", []):
        if url_lower.startswith(platform["url"].lower()):
            return platform
    return None


def get_active_platforms(registry: dict) -> list:
    """Return all platforms where active == true.

    Args:
        registry: Parsed registry dict

    Returns:
        List of active platform dicts
    """
    return [p for p in registry.get("platforms", []) if p.get("active", False)]


def build_utm_urls(url: str, campaign: str) -> dict:
    """Build per-social-platform UTM-tagged URLs for a blog post URL.

    Args:
        url: The original blog post URL
        campaign: UTM campaign name (e.g. "blogcaster")

    Returns:
        Dict mapping social platform name → UTM-tagged URL
    """
    separator = "&" if "?" in url else "?"
    sources = {
        "linkedin": "linkedin",
        "x": "twitter",
        "devto": "devto",
        "facebook": "facebook",
    }
    return {
        platform: f"{url}{separator}utm_source={source}&utm_medium=social&utm_campaign={campaign}"
        for platform, source in sources.items()
    }
