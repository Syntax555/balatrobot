# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "requests",
# ]
# ///

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

if __package__ is None:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from balatro_ai.config import BotConfig
from balatro_ai.logging_utils import configure_logging
from balatro_ai.runner import BotRunner


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
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the bot with CLI-provided configuration."""
    args = build_parser().parse_args(argv)
    configure_logging(args.log_level)
    base_url = f"http://{args.host}:{args.port}"
    config = BotConfig(
        base_url=base_url,
        deck=args.deck,
        stake=args.stake,
        seed=args.seed,
        max_steps=args.max_steps,
        timeout=args.timeout,
    )
    runner = BotRunner(config)
    return runner.run()


if __name__ == "__main__":
    raise SystemExit(main())
