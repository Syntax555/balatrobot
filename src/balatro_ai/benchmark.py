from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from balatro_ai.config import Config
from balatro_ai.gs import gs_ante, gs_money, gs_round_chips, gs_round_num, gs_state, gs_won
from balatro_ai.logging_utils import configure_logging
from balatro_ai.runner import BotRunner


@dataclass(frozen=True)
class BenchmarkResult:
    seed: str
    exit_code: int
    won: bool
    final_state: str
    ante: int
    round: int
    money: int
    chips: int | None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run seeded Balatro AI benchmarks against a running BalatroBot.")
    parser.add_argument("--host", default="127.0.0.1", help="BalatroBot host")
    parser.add_argument("--port", type=int, default=12346, help="BalatroBot port")
    parser.add_argument("--deck", default="RED", help="Deck enum to use")
    parser.add_argument("--stake", default="WHITE", help="Stake enum to use")
    parser.add_argument("--seed", action="append", default=[], help="Seed (repeatable).")
    parser.add_argument("--count", type=int, default=0, help="Generate N seeds (BENCH-0001...).")
    parser.add_argument("--seed-prefix", default="BENCH", help="Prefix for generated seeds.")
    parser.add_argument("--max-steps", type=int, default=1500, help="Max action steps per run.")
    parser.add_argument("--timeout", type=float, default=20.0, help="HTTP timeout seconds.")
    parser.add_argument("--log-level", default="INFO", help="Logging level.")
    parser.add_argument("--out", default="", help="Optional path to write JSON results.")
    parser.add_argument("--decision-log", default="", help="Optional JSONL decision log path for all runs.")
    return parser


def _seeds(args: argparse.Namespace) -> list[str]:
    seeds = []
    for raw in args.seed or []:
        if not isinstance(raw, str):
            continue
        raw = raw.strip()
        if raw:
            seeds.append(raw)
    if args.count and args.count > 0:
        width = max(4, len(str(args.count)))
        for i in range(1, args.count + 1):
            seeds.append(f"{args.seed_prefix}-{i:0{width}d}")
    return seeds


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    seeds = _seeds(args)
    if not seeds:
        print("No seeds provided. Use --seed or --count.", file=sys.stderr)
        return 2

    configure_logging(args.log_level)
    base_url = f"http://{args.host}:{args.port}"
    config = Config(
        deck=args.deck,
        stake=args.stake,
        seed=None,
        max_steps=max(1, int(args.max_steps)),
        timeout=float(args.timeout),
        log_level=args.log_level,
        pause_at_menu=False,
        auto_start=False,
        decision_log_path=args.decision_log or None,
    )

    runner = BotRunner(config=config, base_url=base_url)
    results: list[BenchmarkResult] = []
    try:
        for seed in seeds:
            exit_code, final_state, _steps = runner.run_one(
                deck=args.deck,
                stake=args.stake,
                seed=seed,
                max_steps=config.max_steps,
            )
            results.append(
                BenchmarkResult(
                    seed=seed,
                    exit_code=exit_code,
                    won=gs_won(final_state),
                    final_state=gs_state(final_state),
                    ante=gs_ante(final_state),
                    round=gs_round_num(final_state),
                    money=gs_money(final_state),
                    chips=gs_round_chips(final_state),
                )
            )
    finally:
        runner.close()

    payload: dict[str, Any] = {
        "deck": args.deck,
        "stake": args.stake,
        "port": args.port,
        "results": [asdict(r) for r in results],
        "summary": {
            "runs": len(results),
            "wins": sum(1 for r in results if r.won),
            "exit_codes": {str(code): sum(1 for r in results if r.exit_code == code) for code in sorted({r.exit_code for r in results})},
        },
    }

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    else:
        print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
