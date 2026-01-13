from __future__ import annotations

import argparse
import json
import random
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from balatro_ai.config import Config
from balatro_ai.gs import gs_ante, gs_money, gs_round_num, gs_state, gs_won
from balatro_ai.logging_utils import configure_logging
from balatro_ai.runner import BotRunner

_DEFAULT_OBJECTIVE = "wins_then_ante"
_OBJECTIVES: tuple[str, ...] = ("wins_then_ante", "mean_score", "trimmed_mean_score")


@dataclass(frozen=True)
class Params:
    reserve_early: int
    reserve_mid: int
    reserve_late: int
    max_rerolls_per_shop: int
    rollout_k: int
    discard_m: int
    hand_rollout: bool
    rollout_time_budget_s: float | None
    shop_rollout: bool
    shop_rollout_candidates: int
    shop_rollout_time_budget_s: float | None
    pack_rollout: bool
    pack_rollout_time_budget_s: float | None
    intent_trials: int


@dataclass(frozen=True)
class TrialResult:
    generation: int
    trial: int
    score: float
    params: Params
    runs: list[dict[str, Any]]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Automated, iterative tuner that generates seeds, evaluates candidate configs, "
            "and keeps the best (requires running BalatroBot)."
        )
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=12346)
    parser.add_argument("--deck", default="RED")
    parser.add_argument("--stake", default="WHITE")
    parser.add_argument("--train-count", type=int, default=50)
    parser.add_argument("--eval-count", type=int, default=25)
    parser.add_argument("--train-prefix", default="AUTO-TRAIN")
    parser.add_argument("--eval-prefix", default="AUTO-EVAL")
    parser.add_argument("--generations", type=int, default=10)
    parser.add_argument("--trials", type=int, default=40)
    parser.add_argument("--rng-seed", default="autotune")
    parser.add_argument("--max-steps", type=int, default=1500)
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--log-level", default="INFO")
    parser.add_argument(
        "--baseline-json",
        default="",
        help=(
            "Optional params JSON (e.g. logs/learn/.../best.json). If provided, the baseline config "
            "is evaluated once and used as a mutation starting point."
        ),
    )
    parser.add_argument(
        "--objective",
        choices=_OBJECTIVES,
        default=_DEFAULT_OBJECTIVE,
        help=(
            "Objective function. wins_then_ante matches historical behavior; "
            "mean_score / trimmed_mean_score are more robust when some seeds are unwinnable."
        ),
    )
    parser.add_argument(
        "--trim-bottom-pct",
        type=float,
        default=0.0,
        help=(
            "For trimmed_mean_score: drop the bottom fraction of per-seed scores before averaging "
            "(e.g. 0.1 ignores the hardest 10%%)."
        ),
    )
    parser.add_argument(
        "--out",
        default="logs/autotune/best.json",
        help="Path to write the best params JSON (and history).",
    )
    return parser


def _gen_seeds(prefix: str, count: int) -> list[str]:
    count = max(0, int(count))
    if count <= 0:
        return []
    width = max(4, len(str(count)))
    return [f"{prefix}-{i:0{width}d}" for i in range(1, count + 1)]


def _run_score(run: dict[str, Any]) -> float:
    won = bool(run.get("won"))
    ante = int(run.get("ante") or 0)
    round_num = int(run.get("round") or 0)
    money = int(run.get("money") or 0)
    steps = int(run.get("steps") or 0)
    return (
        (1_000_000.0 if won else 0.0)
        + ante * 10_000.0
        + round_num * 10.0
        + money
        - steps * 0.1
    )


def _objective(
    runs: list[dict[str, Any]], *, objective: str, trim_bottom_pct: float
) -> float:
    if objective == "wins_then_ante":
        wins = sum(1 for r in runs if r.get("won"))
        ante_sum = sum(int(r.get("ante") or 0) for r in runs)
        round_sum = sum(int(r.get("round") or 0) for r in runs)
        money_sum = sum(int(r.get("money") or 0) for r in runs)
        steps_sum = sum(int(r.get("steps") or 0) for r in runs)
        return (
            wins * 1e9 + ante_sum * 1e6 + round_sum * 1e3 + money_sum - steps_sum * 0.1
        )

    if not runs:
        return float("-inf")
    scores = sorted(_run_score(r) for r in runs)
    if objective == "mean_score":
        return float(sum(scores)) / float(len(scores))
    if objective == "trimmed_mean_score":
        pct = max(0.0, min(float(trim_bottom_pct), 0.49))
        drop = int(len(scores) * pct)
        kept = scores[drop:] if drop < len(scores) else scores[-1:]
        return float(sum(kept)) / float(len(kept))
    raise ValueError(f"Unknown objective: {objective!r}")


def _sample_params(rng: random.Random) -> Params:
    reserve_early = rng.randint(0, 15)
    reserve_mid = rng.randint(reserve_early, 30)
    reserve_late = rng.randint(reserve_mid, 45)
    max_rerolls = rng.randint(0, 4)
    rollout_k = rng.randint(12, 60)
    discard_m = rng.randint(6, 22)
    hand_rollout = rng.random() < 0.85
    rollout_time_budget_s = rng.choice([None, 0.15, 0.3, 0.6])
    shop_rollout = rng.random() < 0.35
    pack_rollout = rng.random() < 0.35
    shop_rollout_candidates = rng.randint(6, 18)
    shop_rollout_time_budget_s = (
        rng.choice([None, 0.5, 1.0, 2.0]) if shop_rollout else None
    )
    pack_budget = rng.choice([None, 0.5, 1.0, 2.0])
    intent_trials = rng.choice([50, 100, 150, 200, 300])
    return Params(
        reserve_early=reserve_early,
        reserve_mid=reserve_mid,
        reserve_late=reserve_late,
        max_rerolls_per_shop=max_rerolls,
        rollout_k=rollout_k,
        discard_m=discard_m,
        hand_rollout=hand_rollout,
        rollout_time_budget_s=rollout_time_budget_s,
        shop_rollout=shop_rollout,
        shop_rollout_candidates=shop_rollout_candidates,
        shop_rollout_time_budget_s=shop_rollout_time_budget_s,
        pack_rollout=pack_rollout,
        pack_rollout_time_budget_s=pack_budget,
        intent_trials=int(intent_trials),
    )


def _default_params() -> Params:
    return Params(
        reserve_early=10,
        reserve_mid=20,
        reserve_late=25,
        max_rerolls_per_shop=1,
        rollout_k=30,
        discard_m=12,
        hand_rollout=True,
        rollout_time_budget_s=None,
        shop_rollout=False,
        shop_rollout_candidates=10,
        shop_rollout_time_budget_s=None,
        pack_rollout=False,
        pack_rollout_time_budget_s=None,
        intent_trials=200,
    )


def _params_from_partial(partial: dict[str, Any]) -> Params | None:
    base = asdict(_default_params())
    for key, value in partial.items():
        if key in base:
            base[key] = value
    try:
        return Params(**base)
    except TypeError:
        return None


def _load_params_json(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(
            f"--baseline-json must contain an object, got: {type(raw).__name__}"
        )
    if isinstance(raw.get("best"), dict) and isinstance(
        raw["best"].get("params"), dict
    ):
        return dict(raw["best"]["params"])
    if isinstance(raw.get("params"), dict):
        return dict(raw["params"])
    return dict(raw)


def _baseline_params(path: Path) -> Params | None:
    try:
        params = _load_params_json(path)
        if not isinstance(params, dict):
            return None
        return _params_from_partial(params)
    except Exception:
        return None


def _mutate(best: Params, rng: random.Random) -> Params:
    def bump(value: int, low: int, high: int, scale: int = 3) -> int:
        return max(low, min(high, value + rng.randint(-scale, scale)))

    reserve_early = bump(best.reserve_early, 0, 15, scale=4)
    reserve_mid = bump(best.reserve_mid, reserve_early, 35, scale=5)
    reserve_late = bump(best.reserve_late, reserve_mid, 50, scale=6)
    return Params(
        reserve_early=reserve_early,
        reserve_mid=reserve_mid,
        reserve_late=reserve_late,
        max_rerolls_per_shop=bump(best.max_rerolls_per_shop, 0, 5, scale=1),
        rollout_k=bump(best.rollout_k, 8, 80, scale=8),
        discard_m=bump(best.discard_m, 4, 28, scale=4),
        hand_rollout=best.hand_rollout
        if rng.random() < 0.85
        else not best.hand_rollout,
        rollout_time_budget_s=best.rollout_time_budget_s
        if rng.random() < 0.75
        else rng.choice([None, 0.15, 0.3, 0.6]),
        shop_rollout=best.shop_rollout if rng.random() < 0.8 else not best.shop_rollout,
        shop_rollout_candidates=bump(best.shop_rollout_candidates, 4, 24, scale=4),
        shop_rollout_time_budget_s=best.shop_rollout_time_budget_s
        if rng.random() < 0.75
        else rng.choice([None, 0.5, 1.0, 2.0]),
        pack_rollout=best.pack_rollout if rng.random() < 0.8 else not best.pack_rollout,
        pack_rollout_time_budget_s=best.pack_rollout_time_budget_s
        if rng.random() < 0.75
        else rng.choice([None, 0.5, 1.0, 2.0]),
        intent_trials=max(
            25, min(400, int(best.intent_trials) + rng.choice([-50, -25, 0, 25, 50]))
        ),
    )


def _format_bot_flags(params: Params) -> list[str]:
    flags = [
        f"--reserve-early={params.reserve_early}",
        f"--reserve-mid={params.reserve_mid}",
        f"--reserve-late={params.reserve_late}",
        f"--max-rerolls-per-shop={params.max_rerolls_per_shop}",
        f"--rollout-k={params.rollout_k}",
        f"--discard-m={params.discard_m}",
        f"--intent-trials={params.intent_trials}",
    ]
    flags.append("--hand-rollout" if params.hand_rollout else "--no-hand-rollout")
    if params.rollout_time_budget_s is not None:
        flags.append(f"--rollout-time-budget-s={params.rollout_time_budget_s}")
    if params.shop_rollout:
        flags.append("--shop-rollout")
        flags.append(f"--shop-rollout-candidates={params.shop_rollout_candidates}")
        if params.shop_rollout_time_budget_s is not None:
            flags.append(
                f"--shop-rollout-time-budget-s={params.shop_rollout_time_budget_s}"
            )
    else:
        flags.append("--no-shop-rollout")
    if params.pack_rollout:
        flags.append("--pack-rollout")
        if params.pack_rollout_time_budget_s is not None:
            flags.append(
                f"--pack-rollout-time-budget-s={params.pack_rollout_time_budget_s}"
            )
    else:
        flags.append("--no-pack-rollout")
    return flags


def _load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    configure_logging(args.log_level)

    train_seeds = _gen_seeds(args.train_prefix, args.train_count)
    eval_seeds = _gen_seeds(args.eval_prefix, args.eval_count)
    if not train_seeds:
        print("No train seeds generated. Use --train-count > 0.", file=sys.stderr)
        return 2

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    state = _load_state(out_path)
    history: list[dict[str, Any]] = list(state.get("history") or [])
    best_payload = state.get("best") if isinstance(state.get("best"), dict) else None
    best: TrialResult | None = None
    if best_payload and isinstance(best_payload.get("params"), dict):
        p = best_payload["params"]
        try:
            best_params = Params(**p)
            best = TrialResult(
                generation=int(best_payload.get("generation") or 0),
                trial=int(best_payload.get("trial") or 0),
                score=float(best_payload.get("score") or 0.0),
                params=best_params,
                runs=list(best_payload.get("runs") or []),
            )
        except TypeError:
            best = None

    rng = random.Random(str(args.rng_seed))
    base_url = f"http://{args.host}:{args.port}"

    baseline_first = False
    baseline_json = str(getattr(args, "baseline_json", "") or "").strip()
    if best is None and baseline_json:
        baseline = _baseline_params(Path(baseline_json))
        if baseline is not None:
            best = TrialResult(
                generation=0,
                trial=0,
                score=float("-inf"),
                params=baseline,
                runs=[],
            )
            baseline_first = True

    for generation in range(1, max(1, int(args.generations)) + 1):
        for trial in range(1, max(1, int(args.trials)) + 1):
            if baseline_first and generation == 1 and trial == 1 and best is not None:
                params = best.params
            else:
                params = (
                    _mutate(best.params, rng)
                    if best is not None and rng.random() < 0.7
                    else _sample_params(rng)
                )
            cfg = Config(
                deck=args.deck,
                stake=args.stake,
                seed=None,
                max_steps=max(1, int(args.max_steps)),
                timeout=float(args.timeout),
                log_level=args.log_level,
                reserve_early=params.reserve_early,
                reserve_mid=params.reserve_mid,
                reserve_late=params.reserve_late,
                max_rerolls_per_shop=params.max_rerolls_per_shop,
                rollout_k=params.rollout_k,
                discard_m=params.discard_m,
                hand_rollout=params.hand_rollout,
                rollout_time_budget_s=params.rollout_time_budget_s,
                shop_rollout=params.shop_rollout,
                shop_rollout_candidates=params.shop_rollout_candidates,
                shop_rollout_time_budget_s=params.shop_rollout_time_budget_s,
                pack_rollout=params.pack_rollout,
                pack_rollout_time_budget_s=params.pack_rollout_time_budget_s,
                intent_trials=params.intent_trials,
                pause_at_menu=False,
                auto_start=False,
            )
            runner = BotRunner(config=cfg, base_url=base_url)
            runs: list[dict[str, Any]] = []
            try:
                for seed in train_seeds:
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
                            "steps": _steps,
                        }
                    )
            finally:
                runner.close()

            score = _objective(
                runs,
                objective=str(args.objective),
                trim_bottom_pct=float(args.trim_bottom_pct),
            )
            result = TrialResult(
                generation=generation,
                trial=trial,
                score=score,
                params=params,
                runs=runs,
            )
            history.append(
                {
                    "generation": generation,
                    "trial": trial,
                    "score": score,
                    "params": asdict(params),
                    "train": runs,
                }
            )
            if best is None or score > best.score:
                best = result
                bot_flags = _format_bot_flags(best.params)
                print(
                    f"[best] gen={generation} trial={trial} score={int(score)} flags: {' '.join(bot_flags)}"
                )

                eval_runs: list[dict[str, Any]] = []
                if eval_seeds:
                    eval_cfg = cfg
                    eval_runner = BotRunner(config=eval_cfg, base_url=base_url)
                    try:
                        for seed in eval_seeds:
                            exit_code, final_state, _steps = eval_runner.run_one(
                                deck=args.deck,
                                stake=args.stake,
                                seed=seed,
                                max_steps=eval_cfg.max_steps,
                            )
                            eval_runs.append(
                                {
                                    "seed": seed,
                                    "exit_code": exit_code,
                                    "won": gs_won(final_state),
                                    "state": gs_state(final_state),
                                    "ante": gs_ante(final_state),
                                    "round": gs_round_num(final_state),
                                    "money": gs_money(final_state),
                                    "steps": _steps,
                                }
                            )
                    finally:
                        eval_runner.close()

                out_payload = {
                    "deck": args.deck,
                    "stake": args.stake,
                    "train_seeds": train_seeds,
                    "eval_seeds": eval_seeds,
                    "best": {
                        "generation": best.generation,
                        "trial": best.trial,
                        "score": best.score,
                        "params": asdict(best.params),
                        "train": best.runs,
                        "eval": eval_runs,
                        "bot_flags": bot_flags,
                    },
                    "history": history[-2000:],
                }
                out_path.write_text(json.dumps(out_payload, indent=2), encoding="utf-8")

    if best is None:
        print("No trials executed.", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
