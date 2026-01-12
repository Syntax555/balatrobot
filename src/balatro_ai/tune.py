from __future__ import annotations

import argparse
import json
import random
import sys
from dataclasses import asdict, dataclass
from typing import Any

from balatro_ai.config import Config
from balatro_ai.gs import gs_ante, gs_money, gs_round_num, gs_state, gs_won
from balatro_ai.logging_utils import configure_logging
from balatro_ai.runner import BotRunner


@dataclass(frozen=True)
class TrialResult:
    trial: int
    score: float
    params: dict[str, Any]
    runs: list[dict[str, Any]]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Random-search tuner for Balatro AI parameters (requires running BalatroBot).")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=12346)
    parser.add_argument("--deck", default="RED")
    parser.add_argument("--stake", default="WHITE")
    parser.add_argument("--seed", action="append", default=[], help="Game seed (repeatable).")
    parser.add_argument("--count", type=int, default=10, help="Generate N seeds (TUNE-0001...).")
    parser.add_argument("--seed-prefix", default="TUNE")
    parser.add_argument("--trials", type=int, default=20, help="Number of random configs to evaluate.")
    parser.add_argument("--rng-seed", default="tune", help="RNG seed for the tuner.")
    parser.add_argument("--max-steps", type=int, default=1500)
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--log-level", default="INFO")
    parser.add_argument("--out", default="", help="Optional JSON output path.")
    return parser


def _seeds(args: argparse.Namespace) -> list[str]:
    seeds: list[str] = []
    for raw in args.seed or []:
        if isinstance(raw, str) and raw.strip():
            seeds.append(raw.strip())
    if args.count and args.count > 0:
        width = max(4, len(str(args.count)))
        for i in range(1, args.count + 1):
            seeds.append(f"{args.seed_prefix}-{i:0{width}d}")
    return seeds


def _objective(runs: list[dict[str, Any]]) -> float:
    wins = sum(1 for r in runs if r.get("won"))
    ante_sum = sum(int(r.get("ante") or 0) for r in runs)
    round_sum = sum(int(r.get("round") or 0) for r in runs)
    money_sum = sum(int(r.get("money") or 0) for r in runs)
    # Lexicographic-ish weighting: prioritize wins, then ante, then round, then money.
    return wins * 1e9 + ante_sum * 1e6 + round_sum * 1e3 + money_sum


def _sample_params(rng: random.Random) -> dict[str, Any]:
    reserve_early = rng.randint(0, 15)
    reserve_mid = rng.randint(reserve_early, 30)
    reserve_late = rng.randint(reserve_mid, 40)
    max_rerolls = rng.randint(0, 3)
    rollout_k = rng.randint(12, 60)
    discard_m = rng.randint(6, 20)
    shop_rollout = rng.random() < 0.5
    pack_rollout = rng.random() < 0.5
    shop_rollout_candidates = rng.randint(6, 16)
    pack_budget = rng.choice([None, 0.5, 1.0, 2.0])
    return {
        "reserve_early": reserve_early,
        "reserve_mid": reserve_mid,
        "reserve_late": reserve_late,
        "max_rerolls_per_shop": max_rerolls,
        "rollout_k": rollout_k,
        "discard_m": discard_m,
        "shop_rollout": shop_rollout,
        "shop_rollout_candidates": shop_rollout_candidates,
        "pack_rollout": pack_rollout,
        "pack_rollout_time_budget_s": pack_budget,
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    seeds = _seeds(args)
    if not seeds:
        print("No seeds provided and --count was 0.", file=sys.stderr)
        return 2
    trials = max(1, int(args.trials))

    configure_logging(args.log_level)
    rng = random.Random(str(args.rng_seed))
    base_url = f"http://{args.host}:{args.port}"

    best: TrialResult | None = None
    trial_results: list[TrialResult] = []

    for trial in range(1, trials + 1):
        params = _sample_params(rng)
        cfg = Config(
            deck=args.deck,
            stake=args.stake,
            seed=None,
            max_steps=max(1, int(args.max_steps)),
            timeout=float(args.timeout),
            log_level=args.log_level,
            reserve_early=params["reserve_early"],
            reserve_mid=params["reserve_mid"],
            reserve_late=params["reserve_late"],
            max_rerolls_per_shop=params["max_rerolls_per_shop"],
            rollout_k=params["rollout_k"],
            discard_m=params["discard_m"],
            shop_rollout=params["shop_rollout"],
            shop_rollout_candidates=params["shop_rollout_candidates"],
            pack_rollout=params["pack_rollout"],
            pack_rollout_time_budget_s=params["pack_rollout_time_budget_s"],
            pause_at_menu=False,
            auto_start=False,
        )
        runner = BotRunner(config=cfg, base_url=base_url)
        runs: list[dict[str, Any]] = []
        try:
            for seed in seeds:
                exit_code, final_state, _steps = runner.run_one(
                    deck=args.deck,
                    stake=args.stake,
                    seed=seed,
                    max_steps=cfg.max_steps,
                )
                runs.append(
                    {
                        "seed": seed,
                        "exit_code": exit_code,
                        "won": gs_won(final_state),
                        "state": gs_state(final_state),
                        "ante": gs_ante(final_state),
                        "round": gs_round_num(final_state),
                        "money": gs_money(final_state),
                    }
                )
        finally:
            runner.close()

        score = _objective(runs)
        result = TrialResult(trial=trial, score=score, params=params, runs=runs)
        trial_results.append(result)
        if best is None or score > best.score:
            best = result

    payload = {
        "deck": args.deck,
        "stake": args.stake,
        "seeds": seeds,
        "best": asdict(best) if best is not None else None,
        "trials": [asdict(r) for r in trial_results],
    }

    if args.out:
        from pathlib import Path

        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    else:
        print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

