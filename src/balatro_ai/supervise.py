from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from balatro_ai.config import Config
from balatro_ai.gs import gs_ante, gs_money, gs_round_num, gs_state, gs_won
from balatro_ai.logging_utils import configure_logging
from balatro_ai.runner import BotRunner


@dataclass(frozen=True)
class BestConfig:
    params: dict[str, Any]
    bot_flags: list[str]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run repeated games using the current best params from an autotune JSON file "
            "(pairs well with balatro_ai.autotune running in another terminal)."
        )
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=12346)
    parser.add_argument("--deck", default="RED")
    parser.add_argument("--stake", default="WHITE")
    parser.add_argument("--best", default="logs/autotune/best.json")
    parser.add_argument("--seed-prefix", default="PLAY")
    parser.add_argument("--start", type=int, default=1)
    parser.add_argument("--count", type=int, default=0, help="0 = run forever")
    parser.add_argument("--max-steps", type=int, default=1500)
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--log-level", default="INFO")
    parser.add_argument("--out", default="logs/autotune/play.jsonl")
    parser.add_argument("--poll-s", type=float, default=2.0, help="Reload best.json every N seconds")
    return parser


def _load_best(path: Path) -> BestConfig | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    best = payload.get("best")
    if not isinstance(best, dict):
        return None
    params = best.get("params")
    if not isinstance(params, dict):
        return None
    flags = best.get("bot_flags")
    bot_flags = list(flags) if isinstance(flags, list) else []
    return BestConfig(params=params, bot_flags=bot_flags)


def _seed(prefix: str, index: int) -> str:
    width = max(4, len(str(index)))
    return f"{prefix}-{index:0{width}d}"


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    configure_logging(args.log_level)
    base_url = f"http://{args.host}:{args.port}"

    best_path = Path(args.best)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    next_reload = 0.0
    cached_best: BestConfig | None = None
    last_printed_flags: list[str] = []

    run_index = max(1, int(args.start))
    remaining = int(args.count)

    with out_path.open("a", encoding="utf-8") as fp:
        while remaining != 0:
            now = time.time()
            if now >= next_reload:
                loaded = _load_best(best_path)
                if loaded is not None:
                    cached_best = loaded
                    if loaded.bot_flags and loaded.bot_flags != last_printed_flags:
                        print(f"[best] {' '.join(loaded.bot_flags)}")
                        last_printed_flags = list(loaded.bot_flags)
                next_reload = now + max(0.5, float(args.poll_s))

            if cached_best is None:
                print(f"Waiting for best file: {best_path}", file=sys.stderr)
                time.sleep(max(0.5, float(args.poll_s)))
                continue

            params = dict(cached_best.params)
            cfg = Config(
                deck=args.deck,
                stake=args.stake,
                seed=None,
                max_steps=max(1, int(args.max_steps)),
                timeout=float(args.timeout),
                log_level=args.log_level,
                reserve_early=int(params.get("reserve_early", 10)),
                reserve_mid=int(params.get("reserve_mid", 20)),
                reserve_late=int(params.get("reserve_late", 25)),
                max_rerolls_per_shop=int(params.get("max_rerolls_per_shop", 1)),
                rollout_k=int(params.get("rollout_k", 30)),
                discard_m=int(params.get("discard_m", 12)),
                hand_rollout=bool(params.get("hand_rollout", True)),
                rollout_time_budget_s=params.get("rollout_time_budget_s"),
                shop_rollout=bool(params.get("shop_rollout", False)),
                shop_rollout_candidates=int(params.get("shop_rollout_candidates", 10)),
                shop_rollout_time_budget_s=params.get("shop_rollout_time_budget_s"),
                pack_rollout=bool(params.get("pack_rollout", False)),
                pack_rollout_time_budget_s=params.get("pack_rollout_time_budget_s"),
                intent_trials=int(params.get("intent_trials", 200)),
                pause_at_menu=False,
                auto_start=False,
            )

            runner = BotRunner(config=cfg, base_url=base_url)
            seed = _seed(args.seed_prefix, run_index)
            try:
                exit_code, final_state, steps = runner.run_one(
                    deck=args.deck,
                    stake=args.stake,
                    seed=seed,
                    max_steps=cfg.max_steps,
                )
            finally:
                runner.close()

            record = {
                "seed": seed,
                "exit_code": exit_code,
                "won": gs_won(final_state),
                "state": gs_state(final_state),
                "ante": gs_ante(final_state),
                "round": gs_round_num(final_state),
                "money": gs_money(final_state),
                "steps": steps,
                "params": params,
            }
            fp.write(json.dumps(record) + "\n")
            fp.flush()

            run_index += 1
            if remaining > 0:
                remaining -= 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
