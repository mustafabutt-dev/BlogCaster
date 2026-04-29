"""
Metrics Recorder

Tracks run-level metrics (LLM token usage, execution time, success/failure counts,
API calls) and sends them to Google Sheets via Google Apps Script endpoints.
"""

import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

import httpx

from agent_engine.social_agent.config import settings

logger = logging.getLogger("social_agent")


@dataclass
class MetricsRecorder:
    """Records agent performance metrics and sends them to Google Sheets."""

    # Hardcoded identifiers
    agent_name: str = "BlogCaster"
    agent_owner: str = "Muhammad Mustafa"
    job_type: str = "Social Media Posting"

    # Set by the orchestrator during the run
    product: str = ""
    platform: str = ""
    website: str = ""
    website_section: str = "Blog"
    item_name: str = "Social Media Posting"
    items_discovered: int = 0
    items_succeeded: int = 0
    items_failed: int = 0

    # Accumulated during the run
    token_usage: int = 0
    api_calls_count: int = 0

    # Internal state
    run_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    status: str = "pending"
    _start_time: float = field(default=0.0, repr=False)
    _end_time: float = field(default=0.0, repr=False)

    @property
    def run_env(self) -> str:
        """Auto-detect run environment from GITHUB_ACTIONS env var."""
        return "github_actions" if os.environ.get("GITHUB_ACTIONS") else "DEV"

    @property
    def run_duration_ms(self) -> int:
        """Calculate run duration in milliseconds."""
        if self._start_time and self._end_time:
            return int((self._end_time - self._start_time) * 1000)
        return 0

    def start(self) -> None:
        """Mark the start of a run."""
        self._start_time = time.time()
        self.status = "running"
        logger.info(f"Metrics: run started (run_id={self.run_id})")

    def record_llm_usage(self, input_tokens: int, output_tokens: int, total_tokens: int, api_call_count: int) -> None:
        """Accumulate LLM token usage from a single format call."""
        self.token_usage += total_tokens
        self.api_calls_count += api_call_count
        logger.debug(
            f"Metrics: recorded LLM usage — +{total_tokens} tokens, "
            f"+{api_call_count} API calls (totals: {self.token_usage} tokens, {self.api_calls_count} calls)"
        )

    def record_success(self) -> None:
        """Increment success count."""
        self.items_succeeded += 1

    def record_failure(self) -> None:
        """Increment failure count."""
        self.items_failed += 1

    def finish(self, status: str) -> None:
        """Mark the end of a run with a final status.

        Args:
            status: One of "success", "failure", "error"
        """
        self._end_time = time.time()
        self.status = status
        logger.info(
            f"Metrics: run finished — status={status}, "
            f"duration={self.run_duration_ms}ms, "
            f"tokens={self.token_usage}, api_calls={self.api_calls_count}, "
            f"succeeded={self.items_succeeded}, failed={self.items_failed}"
        )

    def _base_payload(self) -> dict:
        """Build the base payload dict shared by both endpoints."""
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "agent_name": self.agent_name,
            "agent_owner": self.agent_owner,
            "job_type": self.job_type,
            "run_id": self.run_id,
            "status": self.status,
            "product": self.product or "NA",
            "platform": self.platform or "NA",
            "website": self.website,
            "website_section": self.website_section,
            "item_name": self.item_name,
            "items_discovered": self.items_discovered,
            "items_failed": self.items_failed,
            "items_succeeded": self.items_succeeded,
            "run_duration_ms": self.run_duration_ms,
            "token_usage": self.token_usage,
            "api_calls_count": self.api_calls_count,
        }

    def to_payload(self, include_run_env: bool = True) -> dict:
        """Build the payload dict that the Google Sheet expects.

        Args:
            include_run_env: If True, include run_env field (Team sheet only).
        """
        payload = self._base_payload()
        if include_run_env:
            payload["run_env"] = self.run_env
        return payload

    async def send(self) -> None:
        """POST metrics to both Team and Prod Google Sheets endpoints.

        Team payload includes run_env; Prod payload does not.
        Skips silently if endpoints are not configured. Errors are logged
        but never raised — metrics should never break the main workflow.
        """
        endpoints = []
        if settings.METRICS_GOOGLE_SCRIPT_URL_TEAM and settings.METRICS_TOKEN_TEAM:
            endpoints.append(("Team", settings.METRICS_GOOGLE_SCRIPT_URL_TEAM, settings.METRICS_TOKEN_TEAM, True))
        if settings.METRICS_GOOGLE_SCRIPT_URL_PROD and settings.METRICS_TOKEN_PROD:
            endpoints.append(("Prod", settings.METRICS_GOOGLE_SCRIPT_URL_PROD, settings.METRICS_TOKEN_PROD, False))

        if not endpoints:
            logger.info("Metrics: no endpoints configured — skipping send")
            return

        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            for label, url, token, include_run_env in endpoints:
                payload = self.to_payload(include_run_env=include_run_env)
                try:
                    response = await client.post(
                        url,
                        params={"token": token},
                        json=payload,
                    )
                    if response.status_code == 200:
                        logger.info(f"Metrics: sent to {label} endpoint successfully")
                    else:
                        logger.warning(
                            f"Metrics: {label} endpoint returned {response.status_code}: {response.text[:200]}"
                        )
                except Exception as e:
                    logger.warning(f"Metrics: failed to send to {label} endpoint: {e}")

    def print_summary(self) -> None:
        """Print a human-readable metrics summary and full payload to stdout."""
        import json

        payload = self.to_payload()
        print("\n--- Metrics Payload ---")
        print(json.dumps(payload, indent=2))
        print("------------------------\n")
