from __future__ import annotations

import argparse
import hashlib
import json
import math
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

    buy_threshold_early: int
    buy_threshold_mid: int
    buy_threshold_late: int
    reroll_threshold_early: int
    reroll_threshold_mid: int
    reroll_threshold_late: int
    cost_weight_early: float
    cost_weight_mid: float
    cost_weight_late: float

    joker_score_xmult: int
    joker_score_mult: int
    joker_score_chips: int
    joker_score_econ: int
    joker_score_default: int


@dataclass(frozen=True)
class Candidate:
    key: str
    params: Params


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Successive-halving tuner (single-instance friendly). Evaluates many configs "
            "on a small seed subset, keeps the top fraction, then evaluates survivors on more seeds."
        )
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=12346)
    parser.add_argument("--deck", default="RED")
    parser.add_argument("--stake", default="WHITE")
    parser.add_argument(
        "--seed", action="append", default=[], help="Seed (repeatable)."
    )
    parser.add_argument(
        "--count", type=int, default=50, help="Generate N seeds (ASHA-0001...)."
    )
    parser.add_argument("--seed-prefix", default="ASHA")
    parser.add_argument(
        "--baseline-json",
        default="",
        help=(
            "Optional params JSON (e.g. logs/learn/.../best.json). If provided, the baseline config "
            "and its mutations are included in the candidate pool."
        ),
    )
    parser.add_argument(
        "--mutations",
        type=int,
        default=10,
        help="How many mutated variants of --baseline-json to include (0 disables).",
    )
    parser.add_argument(
        "--candidates", type=int, default=40, help="Initial candidate configs."
    )
    parser.add_argument("--eta", type=int, default=3, help="Pruning factor per rung.")
    parser.add_argument(
        "--rungs", type=int, default=4, help="Number of successive-halving rungs."
    )
    parser.add_argument(
        "--min-seeds", type=int, default=6, help="Seeds evaluated in rung 0."
    )
    parser.add_argument(
        "--max-seeds",
        type=int,
        default=50,
        help="Max seeds per candidate in final rung.",
    )
    parser.add_argument(
        "--eval-count", type=int, default=0, help="Optional holdout seed count."
    )
    parser.add_argument(
        "--eval-prefix", default="ASHA-EVAL", help="Holdout seed prefix."
    )
    parser.add_argument("--rng-seed", default="asha")
    parser.add_argument("--max-steps", type=int, default=1500)
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--log-level", default="INFO")
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
    reserve_mid = rng.randint(reserve_early, 35)
    reserve_late = rng.randint(reserve_mid, 55)
    max_rerolls = rng.randint(0, 5)
    rollout_k = rng.randint(10, 70)
    discard_m = rng.randint(6, 24)

    hand_rollout = rng.random() < 0.85
    rollout_time_budget_s = rng.choice([None, 0.15, 0.3, 0.6, 1.0])
    shop_rollout = rng.random() < 0.35
    shop_rollout_candidates = rng.randint(6, 20)
    shop_rollout_time_budget_s = (
        rng.choice([None, 0.5, 1.0, 2.0]) if shop_rollout else None
    )
    pack_rollout = rng.random() < 0.35
    pack_budget = rng.choice([None, 0.5, 1.0, 2.0])
    intent_trials = rng.choice([50, 100, 150, 200, 300])

    buy_threshold_early = rng.randint(15, 45)
    buy_threshold_mid = rng.randint(buy_threshold_early, 55)
    buy_threshold_late = rng.randint(buy_threshold_mid, 70)
    reroll_threshold_early = rng.randint(10, 35)
    reroll_threshold_mid = rng.randint(reroll_threshold_early, 45)
    reroll_threshold_late = rng.randint(reroll_threshold_mid, 60)
    cost_weight_early = rng.choice([1.3, 1.5, 1.8, 2.0, 2.2])
    cost_weight_mid = rng.choice([0.9, 1.0, 1.2, 1.3, 1.4])
    cost_weight_late = rng.choice([0.6, 0.75, 0.9, 1.0, 1.1])

    joker_score_xmult = rng.randint(70, 150)
    joker_score_mult = rng.randint(30, 90)
    joker_score_chips = rng.randint(10, 45)
    joker_score_econ = rng.randint(-10, 20)
    joker_score_default = 0

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
        buy_threshold_early=buy_threshold_early,
        buy_threshold_mid=buy_threshold_mid,
        buy_threshold_late=buy_threshold_late,
        reroll_threshold_early=reroll_threshold_early,
        reroll_threshold_mid=reroll_threshold_mid,
        reroll_threshold_late=reroll_threshold_late,
        cost_weight_early=float(cost_weight_early),
        cost_weight_mid=float(cost_weight_mid),
        cost_weight_late=float(cost_weight_late),
        joker_score_xmult=joker_score_xmult,
        joker_score_mult=joker_score_mult,
        joker_score_chips=joker_score_chips,
        joker_score_econ=joker_score_econ,
        joker_score_default=joker_score_default,
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
        buy_threshold_early=30,
        buy_threshold_mid=35,
        buy_threshold_late=40,
        reroll_threshold_early=20,
        reroll_threshold_mid=25,
        reroll_threshold_late=30,
        cost_weight_early=1.8,
        cost_weight_mid=1.2,
        cost_weight_late=0.9,
        joker_score_xmult=100,
        joker_score_mult=50,
        joker_score_chips=20,
        joker_score_econ=0,
        joker_score_default=0,
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


def _mutate_params(rng: random.Random, base: Params) -> Params:
    def bump_int(value: int, *, low: int, high: int, scale: int) -> int:
        return max(low, min(high, int(value) + rng.randint(-scale, scale)))

    def bump_float(value: float, *, low: float, high: float, step: float) -> float:
        delta = rng.choice([-step, 0.0, step])
        return max(low, min(high, float(value) + delta))

    reserve_early = bump_int(base.reserve_early, low=0, high=15, scale=4)
    reserve_mid = bump_int(base.reserve_mid, low=reserve_early, high=35, scale=5)
    reserve_late = bump_int(base.reserve_late, low=reserve_mid, high=55, scale=6)

    buy_threshold_early = bump_int(base.buy_threshold_early, low=10, high=55, scale=5)
    buy_threshold_mid = bump_int(
        base.buy_threshold_mid, low=buy_threshold_early, high=65, scale=6
    )
    buy_threshold_late = bump_int(
        base.buy_threshold_late, low=buy_threshold_mid, high=80, scale=7
    )
    reroll_threshold_early = bump_int(
        base.reroll_threshold_early, low=0, high=45, scale=5
    )
    reroll_threshold_mid = bump_int(
        base.reroll_threshold_mid, low=reroll_threshold_early, high=55, scale=6
    )
    reroll_threshold_late = bump_int(
        base.reroll_threshold_late, low=reroll_threshold_mid, high=70, scale=7
    )

    return Params(
        reserve_early=reserve_early,
        reserve_mid=reserve_mid,
        reserve_late=reserve_late,
        max_rerolls_per_shop=bump_int(
            base.max_rerolls_per_shop, low=0, high=6, scale=1
        ),
        rollout_k=bump_int(base.rollout_k, low=8, high=90, scale=10),
        discard_m=bump_int(base.discard_m, low=4, high=30, scale=4),
        hand_rollout=base.hand_rollout
        if rng.random() < 0.85
        else not base.hand_rollout,
        rollout_time_budget_s=base.rollout_time_budget_s
        if rng.random() < 0.75
        else rng.choice([None, 0.15, 0.3, 0.6, 1.0]),
        shop_rollout=base.shop_rollout if rng.random() < 0.8 else not base.shop_rollout,
        shop_rollout_candidates=bump_int(
            base.shop_rollout_candidates, low=4, high=24, scale=4
        ),
        shop_rollout_time_budget_s=base.shop_rollout_time_budget_s
        if rng.random() < 0.75
        else rng.choice([None, 0.5, 1.0, 2.0]),
        pack_rollout=base.pack_rollout if rng.random() < 0.8 else not base.pack_rollout,
        pack_rollout_time_budget_s=base.pack_rollout_time_budget_s
        if rng.random() < 0.75
        else rng.choice([None, 0.5, 1.0, 2.0]),
        intent_trials=max(
            25,
            min(400, int(base.intent_trials) + rng.choice([-50, -25, 0, 25, 50])),
        ),
        buy_threshold_early=buy_threshold_early,
        buy_threshold_mid=buy_threshold_mid,
        buy_threshold_late=buy_threshold_late,
        reroll_threshold_early=reroll_threshold_early,
        reroll_threshold_mid=reroll_threshold_mid,
        reroll_threshold_late=reroll_threshold_late,
        cost_weight_early=bump_float(
            base.cost_weight_early, low=1.0, high=2.6, step=0.1
        ),
        cost_weight_mid=bump_float(base.cost_weight_mid, low=0.6, high=1.8, step=0.1),
        cost_weight_late=bump_float(base.cost_weight_late, low=0.4, high=1.4, step=0.1),
        joker_score_xmult=bump_int(base.joker_score_xmult, low=50, high=180, scale=10),
        joker_score_mult=bump_int(base.joker_score_mult, low=10, high=120, scale=10),
        joker_score_chips=bump_int(base.joker_score_chips, low=0, high=70, scale=8),
        joker_score_econ=bump_int(base.joker_score_econ, low=-25, high=35, scale=5),
        joker_score_default=0,
    )


def _candidate_key(params: Params) -> str:
    payload = json.dumps(asdict(params), sort_keys=True, separators=(",", ":"))
    # Stable, short-ish key; collisions are unlikely for our purposes.
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _build_cfg(args: argparse.Namespace, params: Params) -> Config:
    return Config(
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
        buy_threshold_early=params.buy_threshold_early,
        buy_threshold_mid=params.buy_threshold_mid,
        buy_threshold_late=params.buy_threshold_late,
        reroll_threshold_early=params.reroll_threshold_early,
        reroll_threshold_mid=params.reroll_threshold_mid,
        reroll_threshold_late=params.reroll_threshold_late,
        cost_weight_early=params.cost_weight_early,
        cost_weight_mid=params.cost_weight_mid,
        cost_weight_late=params.cost_weight_late,
        joker_score_xmult=params.joker_score_xmult,
        joker_score_mult=params.joker_score_mult,
        joker_score_chips=params.joker_score_chips,
        joker_score_econ=params.joker_score_econ,
        joker_score_default=params.joker_score_default,
    )


def _run_seeds(
    runner: BotRunner,
    *,
    deck: str,
    stake: str,
    seeds: list[str],
    max_steps: int,
) -> list[dict[str, Any]]:
    runs: list[dict[str, Any]] = []
    for seed in seeds:
        exit_code, final_state, steps = runner.run_one(
            deck=deck,
            stake=stake,
            seed=seed,
            max_steps=max_steps,
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
                "steps": steps,
            }
        )
    return runs


def _rung_seed_budget(rung: int, *, min_seeds: int, max_seeds: int, rungs: int) -> int:
    if rungs <= 1:
        return max(1, max_seeds)
    rung = max(0, min(int(rung), int(rungs) - 1))
    t = rung / float(max(1, rungs - 1))
    seeds = int(round(min_seeds + (max_seeds - min_seeds) * t))
    return max(1, seeds)


def _runs_by_seed(runs: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    by_seed: dict[str, dict[str, Any]] = {}
    for run in runs:
        seed = run.get("seed")
        if isinstance(seed, str) and seed:
            by_seed[seed] = dict(run)
    return by_seed


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    seeds = _seeds(args)
    if not seeds:
        print("No seeds provided. Use --seed or --count.", file=sys.stderr)
        return 2

    configure_logging(args.log_level)
    rng = random.Random(str(args.rng_seed))
    base_url = f"http://{args.host}:{args.port}"

    initial_candidates = max(1, int(args.candidates))
    eta = max(2, int(args.eta))
    rungs = max(1, int(args.rungs))
    min_seeds = max(1, int(args.min_seeds))
    max_seeds = min(len(seeds), max(1, int(args.max_seeds)))
    min_seeds = min(min_seeds, max_seeds)

    candidates: list[Candidate] = []
    seen: set[str] = set()

    baseline_json = str(getattr(args, "baseline_json", "") or "").strip()
    if baseline_json:
        baseline = _baseline_params(Path(baseline_json))
        if baseline is not None:
            key = _candidate_key(baseline)
            seen.add(key)
            candidates.append(Candidate(key=key, params=baseline))
            for _ in range(max(0, int(args.mutations))):
                mutated = _mutate_params(rng, baseline)
                key = _candidate_key(mutated)
                if key in seen:
                    continue
                seen.add(key)
                candidates.append(Candidate(key=key, params=mutated))
                if len(candidates) >= initial_candidates:
                    break
    while len(candidates) < initial_candidates:
        params = _sample_params(rng)
        key = _candidate_key(params)
        if key in seen:
            continue
        seen.add(key)
        candidates.append(Candidate(key=key, params=params))

    history: list[dict[str, Any]] = []
    best: dict[str, Any] | None = None
    candidate_runs: dict[str, list[dict[str, Any]]] = {}

    for rung in range(rungs):
        budget = _rung_seed_budget(
            rung, min_seeds=min_seeds, max_seeds=max_seeds, rungs=rungs
        )
        rung_seeds = seeds[:budget]
        scored: list[tuple[float, Candidate, list[dict[str, Any]]]] = []

        for idx, cand in enumerate(candidates, start=1):
            cfg = _build_cfg(args, cand.params)
            runner = BotRunner(config=cfg, base_url=base_url)
            try:
                prior = candidate_runs.get(cand.key, [])
                by_seed = _runs_by_seed(prior)
                missing = [s for s in rung_seeds if s not in by_seed]
                if missing:
                    new_runs = _run_seeds(
                        runner,
                        deck=args.deck,
                        stake=args.stake,
                        seeds=missing,
                        max_steps=cfg.max_steps,
                    )
                    by_seed.update(_runs_by_seed(new_runs))
                runs = [by_seed[s] for s in rung_seeds if s in by_seed]
                candidate_runs[cand.key] = runs
            finally:
                runner.close()
            score = _objective(
                runs,
                objective=str(args.objective),
                trim_bottom_pct=float(args.trim_bottom_pct),
            )
            scored.append((score, cand, runs))
            history.append(
                {
                    "rung": rung,
                    "budget": budget,
                    "candidate": cand.key,
                    "score": score,
                    "params": asdict(cand.params),
                    "runs": runs,
                }
            )
            if best is None or score > float(best.get("score", float("-inf"))):
                best = {
                    "rung": rung,
                    "budget": budget,
                    "candidate": cand.key,
                    "score": score,
                    "params": asdict(cand.params),
                    "runs": runs,
                }

        scored.sort(key=lambda item: item[0], reverse=True)
        survivors = max(1, int(math.ceil(len(scored) / float(eta))))
        candidates = [cand for _score, cand, _runs in scored[:survivors]]

    payload: dict[str, Any] = {
        "deck": args.deck,
        "stake": args.stake,
        "seeds": seeds,
        "best": best,
        "history": history,
    }

    eval_seeds = _gen_seeds(str(args.eval_prefix), int(args.eval_count))
    if eval_seeds and best is not None and isinstance(best.get("params"), dict):
        best_params = _params_from_partial(best["params"])
        if best_params is not None:
            cfg = _build_cfg(args, best_params)
            runner = BotRunner(config=cfg, base_url=base_url)
            try:
                eval_runs = _run_seeds(
                    runner,
                    deck=args.deck,
                    stake=args.stake,
                    seeds=eval_seeds,
                    max_steps=cfg.max_steps,
                )
            finally:
                runner.close()
            payload["eval_seeds"] = eval_seeds
            payload["best_eval"] = {
                "objective": str(args.objective),
                "trim_bottom_pct": float(args.trim_bottom_pct),
                "score": _objective(
                    eval_runs,
                    objective=str(args.objective),
                    trim_bottom_pct=float(args.trim_bottom_pct),
                ),
                "runs": eval_runs,
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
