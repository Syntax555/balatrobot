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
from collections.abc import Sequence
from pathlib import Path

if __package__ is None:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from balatro_ai.config import Config
from balatro_ai.logging_utils import configure_logging
from balatro_ai.runner import BotRunner

logger = logging.getLogger(__name__)


_VALID_STAKES: frozenset[str] = frozenset(
    {
        "WHITE",
        "RED",
        "GREEN",
        "BLACK",
        "BLUE",
        "PURPLE",
        "ORANGE",
        "GOLD",
    }
)

_VALID_DECKS: frozenset[str] = frozenset(
    {
        "RED",
        "BLUE",
        "YELLOW",
        "GREEN",
        "BLACK",
        "MAGIC",
        "NEBULA",
        "GHOST",
        "ABANDONED",
        "CHECKERED",
        "ZODIAC",
        "PAINTED",
        "ANAGLYPH",
        "PLASMA",
        "ERRATIC",
    }
)


def _upper_choice(name: str, allowed: frozenset[str]):
    def parse(value: str) -> str:
        if not isinstance(value, str):
            raise argparse.ArgumentTypeError(f"{name} must be a string")
        normalized = value.strip().upper()
        if not normalized:
            raise argparse.ArgumentTypeError(f"{name} is required")
        if normalized not in allowed:
            options = ", ".join(sorted(allowed))
            raise argparse.ArgumentTypeError(
                f"invalid {name} {normalized!r}; expected one of: {options}"
            )
        return normalized

    return parse


def _positive_int(name: str):
    def parse(value: str) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError) as exc:
            raise argparse.ArgumentTypeError(f"{name} must be an integer") from exc
        if parsed <= 0:
            raise argparse.ArgumentTypeError(f"{name} must be > 0")
        return parsed

    return parse


def _nonnegative_int(name: str):
    def parse(value: str) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError) as exc:
            raise argparse.ArgumentTypeError(f"{name} must be an integer") from exc
        if parsed < 0:
            raise argparse.ArgumentTypeError(f"{name} must be >= 0")
        return parsed

    return parse


def _positive_float(name: str):
    def parse(value: str) -> float:
        try:
            parsed = float(value)
        except (TypeError, ValueError) as exc:
            raise argparse.ArgumentTypeError(f"{name} must be a number") from exc
        if parsed <= 0.0:
            raise argparse.ArgumentTypeError(f"{name} must be > 0")
        return parsed

    return parse


def _nonnegative_float(name: str):
    def parse(value: str) -> float:
        try:
            parsed = float(value)
        except (TypeError, ValueError) as exc:
            raise argparse.ArgumentTypeError(f"{name} must be a number") from exc
        if parsed < 0.0:
            raise argparse.ArgumentTypeError(f"{name} must be >= 0")
        return parsed

    return parse


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser for the bot."""
    parser = argparse.ArgumentParser(description="Run a BalatroBot client.")
    parser.add_argument("--host", default="127.0.0.1", help="BalatroBot host")
    parser.add_argument(
        "--port", default=12346, type=_positive_int("--port"), help="BalatroBot port"
    )
    parser.add_argument(
        "--deck",
        default="RED",
        type=_upper_choice("--deck", _VALID_DECKS),
        help="Deck to use",
    )
    parser.add_argument(
        "--stake",
        default="WHITE",
        type=_upper_choice("--stake", _VALID_STAKES),
        help="Stake level to use",
    )
    parser.add_argument("--seed", default=None, help="Optional seed for the run")
    parser.add_argument(
        "--max-steps",
        default=1000,
        type=_positive_int("--max-steps"),
        help="Max steps to run",
    )
    parser.add_argument(
        "--timeout",
        default=10.0,
        type=_positive_float("--timeout"),
        help="HTTP timeout seconds",
    )
    parser.add_argument("--log-level", default="INFO", help="Logging level")
    parser.add_argument(
        "--rollout-k",
        default=30,
        type=_positive_int("--rollout-k"),
        help="Rollout depth",
    )
    parser.add_argument(
        "--hand-rollout",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="If enabled, use save/load rollouts to choose play/discard in SELECTING_HAND.",
    )
    parser.add_argument(
        "--rollout-parallel",
        default=None,
        help="Rollout parallelism: 0, threads, or processes (default: env BALATRO_AI_ROLLOUT_PARALLEL or 0).",
    )
    parser.add_argument(
        "--rollout-workers",
        default=None,
        type=_nonnegative_int("--rollout-workers"),
        help="Rollout parallel worker count (default: env BALATRO_AI_ROLLOUT_WORKERS or 0).",
    )
    parser.add_argument(
        "--rollout-time-budget-s",
        default=None,
        type=_nonnegative_float("--rollout-time-budget-s"),
        help="Per-step rollout evaluation time budget seconds (default: env BALATRO_AI_ROLLOUT_TIME_BUDGET_S).",
    )
    parser.add_argument(
        "--discard-m",
        default=12,
        type=_nonnegative_int("--discard-m"),
        help="Discard candidates",
    )
    parser.add_argument(
        "--reserve-early",
        default=10,
        type=_nonnegative_int("--reserve-early"),
        help="Early reserve",
    )
    parser.add_argument(
        "--reserve-mid",
        default=20,
        type=_nonnegative_int("--reserve-mid"),
        help="Mid reserve",
    )
    parser.add_argument(
        "--reserve-late",
        default=25,
        type=_nonnegative_int("--reserve-late"),
        help="Late reserve",
    )
    parser.add_argument(
        "--max-rerolls-per-shop",
        default=1,
        type=_nonnegative_int("--max-rerolls-per-shop"),
        help="Maximum rerolls per shop",
    )
    parser.add_argument(
        "--decision-log",
        default=None,
        help="If set, write JSONL decision logs to this path.",
    )
    parser.add_argument(
        "--decision-log-include-state",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="If enabled, include small state summaries in JSONL decision logs.",
    )
    parser.add_argument(
        "--shop-rollout",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="If enabled, use save/load lookahead for SHOP decisions (slower, but can be stronger).",
    )
    parser.add_argument(
        "--shop-rollout-candidates",
        default=10,
        type=_positive_int("--shop-rollout-candidates"),
        help="Max number of SHOP candidate sequences to evaluate when --shop-rollout is enabled.",
    )
    parser.add_argument(
        "--shop-rollout-time-budget-s",
        default=None,
        type=_nonnegative_float("--shop-rollout-time-budget-s"),
        help="Per-SHOP rollout evaluation time budget seconds.",
    )
    parser.add_argument(
        "--pack-rollout",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="If enabled, use save/load evaluation for pack selection (slower, but can be stronger).",
    )
    parser.add_argument(
        "--pack-rollout-time-budget-s",
        default=None,
        type=_nonnegative_float("--pack-rollout-time-budget-s"),
        help="Per-pack rollout evaluation time budget seconds.",
    )
    parser.add_argument(
        "--determinism-check",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="If enabled, probe save/load determinism and disable rollouts if unsafe.",
    )
    parser.add_argument(
        "--intent-trials",
        default=200,
        type=_positive_int("--intent-trials"),
        help="Intent evaluation Monte Carlo trials (higher = more stable, slower).",
    )
    parser.add_argument(
        "--pause-at-menu",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="If enabled, pause actions at MENU until the game leaves MENU (polling gamestate).",
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
        hand_rollout=args.hand_rollout,
        rollout_parallel=args.rollout_parallel,
        rollout_workers=args.rollout_workers,
        rollout_time_budget_s=args.rollout_time_budget_s,
        discard_m=args.discard_m,
        reserve_early=args.reserve_early,
        reserve_mid=args.reserve_mid,
        reserve_late=args.reserve_late,
        max_rerolls_per_shop=args.max_rerolls_per_shop,
        decision_log_path=args.decision_log,
        decision_log_include_state=args.decision_log_include_state,
        shop_rollout=args.shop_rollout,
        shop_rollout_candidates=args.shop_rollout_candidates,
        shop_rollout_time_budget_s=args.shop_rollout_time_budget_s,
        pack_rollout=args.pack_rollout,
        pack_rollout_time_budget_s=args.pack_rollout_time_budget_s,
        determinism_check=args.determinism_check,
        intent_trials=args.intent_trials,
        pause_at_menu=args.pause_at_menu,
        auto_start=args.auto_start,
    )
    configure_logging(config.log_level)
    logger.debug("Starting BotRunner base_url=%s config=%s", base_url, config)
    runner = BotRunner(config=config, base_url=base_url)
    return runner.run()


if __name__ == "__main__":
    raise SystemExit(main())
