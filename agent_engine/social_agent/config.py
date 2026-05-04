"""
Centralized Configuration

Pydantic BaseSettings loading from .env file.
All credentials and paths are configured here.
"""

import os

from dotenv import load_dotenv
from pydantic_settings import BaseSettings

# Resolve project root (three levels up from this file: config.py → social_agent → agent_engine → socialAgent)
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load .env into os.environ so dynamic lookups (e.g. platform-specific credentials) work
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env file."""

    # LLM Configuration
    PROFESSIONALIZE_BASE_URL: str = ""
    PROFESSIONALIZE_API_KEY_2: str = ""
    PROFESSIONALIZE_LLM_MODEL: str = ""

    # LinkedIn Configuration
    LINKEDIN_ACCESS_TOKEN: str = ""

    # X (Twitter) Configuration
    X_API_KEY: str = ""
    X_API_SECRET: str = ""
    X_ACCESS_TOKEN: str = ""
    X_ACCESS_TOKEN_SECRET: str = ""

    # Facebook Page Configuration (default)
    FACEBOOK_PAGE_ID: str = ""
    FACEBOOK_PAGE_ACCESS_TOKEN: str = ""
    # Platform-specific overrides loaded dynamically from env:
    # FACEBOOK_{BRAND}_PAGE_ID / FACEBOOK_{BRAND}_PAGE_ACCESS_TOKEN
    # e.g. FACEBOOK_GROUPDOCS_PAGE_ID, FACEBOOK_CONHOLDATE_PAGE_ID

    # Metrics Configuration (Google Sheets endpoints)
    METRICS_GOOGLE_SCRIPT_URL_TEAM: str = ""
    METRICS_TOKEN_TEAM: str = ""
    METRICS_GOOGLE_SCRIPT_URL_PROD: str = ""
    METRICS_TOKEN_PROD: str = ""

    # File Paths (relative to project root)
    REGISTRY_PATH: str = "registry/platforms_registry.json"
    RECORDS_PATH: str = "content/records/published_record.json"
    LOG_PATH: str = "logs/logs.txt"

    # MCP Server Paths (relative to project root)
    RSS_FETCHER_PATH: str = "mcp-servers/rss-fetcher/server.py"
    LINKEDIN_POSTER_PATH: str = "mcp-servers/linkedin-poster/server.py"
    X_POSTER_PATH: str = "mcp-servers/x-poster/server.py"
    FACEBOOK_POSTER_PATH: str = "mcp-servers/facebook-poster/server.py"
    RECORD_KEEPER_PATH: str = "mcp-servers/record-keeper/server.py"

    model_config = {
        "env_file": os.path.join(PROJECT_ROOT, ".env"),
        "extra": "ignore",
    }

    def resolve_path(self, relative_path: str) -> str:
        """Resolve a relative path against the project root."""
        return os.path.join(PROJECT_ROOT, relative_path)


settings = Settings()
