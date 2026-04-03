"""
Social Media Agent — CLI Entry Point

Usage:
    python -m agent_engine.social_agent.main --url "https://blog.aspose.com/some-post"
    python -m agent_engine.social_agent.main --auto --platform aspose
    python -m agent_engine.social_agent.main --auto
    python -m agent_engine.social_agent.main
"""

import argparse
import asyncio
import sys

from agent_engine.social_agent.config import settings
from agent_engine.social_agent.utils.helpers import (
    get_active_platforms,
    load_registry,
    setup_logger,
)


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="social-media-agent",
        description="Post blog content to LinkedIn and X (Twitter).",
    )
    parser.add_argument(
        "--url",
        type=str,
        help="Blog post URL to share (Manual Mode)",
    )
    parser.add_argument(
        "--auto",
        action="store_true",
        help="Enable Auto Mode (pick latest unposted blog)",
    )
    parser.add_argument(
        "--platform",
        type=str,
        help="Platform ID for Auto Mode (e.g. aspose, groupdocs, conholdate)",
    )
    parser.add_argument(
        "--target",
        type=str,
        choices=["all", "linkedin", "x"],
        default="all",
        help="Social media target: all, linkedin, or x (default: all)",
    )
    return parser


def print_usage(parser: argparse.ArgumentParser) -> None:
    """Print usage instructions."""
    parser.print_help()
    print()
    print("Examples:")
    print('  python -m agent_engine.social_agent.main --url "https://blog.aspose.com/some-post"')
    print("  python -m agent_engine.social_agent.main --auto --platform aspose")
    print("  python -m agent_engine.social_agent.main --auto --platform groupdocs")


def print_available_platforms() -> None:
    """Print available platform IDs from the registry."""
    try:
        registry_path = settings.resolve_path(settings.REGISTRY_PATH)
        registry = load_registry(registry_path)
        platforms = get_active_platforms(registry)
        print("\nAvailable platforms:")
        for p in platforms:
            print(f"  - {p['id']:15s} ({p['name']})")
    except Exception as e:
        print(f"\nError loading registry: {e}")


def main() -> None:
    """Main entry point — parse args and dispatch to the appropriate mode."""
    parser = build_parser()
    args = parser.parse_args()

    # Set up logger
    log_path = settings.resolve_path(settings.LOG_PATH)
    logger = setup_logger(log_path)

    # Import orchestrator here to avoid circular imports and ensure logger is set up
    from agent_engine.social_agent.agent_logic.orchestrator import run_auto_mode, run_manual_mode
    from agent_engine.social_agent.tools.mcp_tools import open_mcp_sessions

    # No flags — print usage
    if not args.url and not args.auto:
        print_usage(parser)
        sys.exit(0)

    # --auto without --platform — print error and list platforms
    if args.auto and not args.platform:
        print("Error: --platform is required with --auto")
        print_available_platforms()
        sys.exit(1)

    async def _run_manual(url: str, target: str) -> bool:
        async with open_mcp_sessions() as sessions:
            return await run_manual_mode(sessions, url, target=target)

    async def _run_auto(platform: str, target: str) -> bool:
        async with open_mcp_sessions() as sessions:
            return await run_auto_mode(sessions, platform, target=target)

    # Manual Mode
    if args.url:
        logger.info(f"CLI: Manual Mode invoked for URL: {args.url} (target: {args.target})")
        try:
            success = asyncio.run(_run_manual(args.url, args.target))
            sys.exit(0 if success else 1)
        except KeyboardInterrupt:
            logger.info("Interrupted by user")
            print("\nInterrupted.")
            sys.exit(130)
        except Exception as e:
            logger.error(f"Unexpected error in Manual Mode: {e}", exc_info=True)
            print(f"Unexpected error: {e}")
            sys.exit(1)

    # Auto Mode
    if args.auto and args.platform:
        logger.info(f"CLI: Auto Mode invoked for platform: {args.platform} (target: {args.target})")
        try:
            success = asyncio.run(_run_auto(args.platform, args.target))
            sys.exit(0 if success else 1)
        except KeyboardInterrupt:
            logger.info("Interrupted by user")
            print("\nInterrupted.")
            sys.exit(130)
        except Exception as e:
            logger.error(f"Unexpected error in Auto Mode: {e}", exc_info=True)
            print(f"Unexpected error: {e}")
            sys.exit(1)


if __name__ == "__main__":
    main()
