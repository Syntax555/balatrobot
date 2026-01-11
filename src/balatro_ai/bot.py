# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "httpx>=0.28.1",
# ]
# ///

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Sequence

if __package__ is None:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from balatro_ai.config import Config
from balatro_ai.logging_utils import configure_logging
from balatro_ai.runner import BotRunner

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser for the bot."""
    parser = argparse.ArgumentParser(description="Run a BalatroBot client.")
    parser.add_argument("--host", default="127.0.0.1", help="BalatroBot host")
    parser.add_argument("--port", default=12346, type=int, help="BalatroBot port")
    parser.add_argument("--deck", default="RED", help="Deck to use")
    parser.add_argument("--stake", default="WHITE", help="Stake level to use")
    parser.add_argument("--seed", default=None, help="Optional seed for the run")
    parser.add_argument("--max-steps", default=1000, type=int, help="Max steps to run")
    parser.add_argument("--timeout", default=10.0, type=float, help="HTTP timeout seconds")
    parser.add_argument("--log-level", default="INFO", help="Logging level")
    parser.add_argument("--rollout-k", default=30, type=int, help="Rollout depth")
    parser.add_argument("--discard-m", default=12, type=int, help="Discard candidates")
    parser.add_argument("--reserve-early", default=10, type=int, help="Early reserve")
    parser.add_argument("--reserve-mid", default=20, type=int, help="Mid reserve")
    parser.add_argument("--reserve-late", default=25, type=int, help="Late reserve")
    parser.add_argument(
        "--max-rerolls-per-shop",
        default=1,
        type=int,
        help="Maximum rerolls per shop",
    )
    parser.add_argument(
        "--pause-at-menu",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="If enabled, wait forever at MENU until script restart.",
    )
    parser.add_argument(
        "--auto-start",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="If enabled, call RPC start from MENU using --deck/--stake/--seed.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the bot with CLI-provided configuration."""
    args = build_parser().parse_args(argv)
    base_url = f"http://{args.host}:{args.port}"
    config = Config(
        deck=args.deck,
        stake=args.stake,
        seed=args.seed,
        max_steps=args.max_steps,
        timeout=args.timeout,
        log_level=args.log_level,
        rollout_k=args.rollout_k,
        discard_m=args.discard_m,
        reserve_early=args.reserve_early,
        reserve_mid=args.reserve_mid,
        reserve_late=args.reserve_late,
        max_rerolls_per_shop=args.max_rerolls_per_shop,
        pause_at_menu=args.pause_at_menu,
        auto_start=args.auto_start,
    )
    configure_logging(config.log_level)
    logger.debug("Starting BotRunner base_url=%s config=%s", base_url, config)
    runner = BotRunner(config=config, base_url=base_url)
    return runner.run()


if __name__ == "__main__":
    raise SystemExit(main())
