from __future__ import annotations

import argparse
import json
from collections import Counter
from collections.abc import Iterable
from pathlib import Path
from typing import Any


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Analyze Balatro AI decision logs (JSONL)."
    )
    parser.add_argument("--log", required=True, help="Path to a JSONL decision log.")
    return parser


def _iter_records(path: Path) -> Iterable[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as fp:
        for line in fp:
            line = line.strip()
            if not line:
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                yield value


def _is_game_over_result(rec: dict[str, Any]) -> bool:
    if rec.get("event") != "result":
        return False
    after = rec.get("after")
    return isinstance(after, dict) and after.get("state") == "GAME_OVER"


def _current_blind_name(state: dict[str, Any]) -> str | None:
    blinds = state.get("blinds")
    if not isinstance(blinds, dict):
        return None
    for key in ("small", "big", "boss"):
        entry = blinds.get(key)
        if isinstance(entry, dict) and entry.get("status") == "CURRENT":
            name = entry.get("name")
            return name if isinstance(name, str) and name.strip() else None
    return None


def _boss_name(state: dict[str, Any]) -> str | None:
    blinds = state.get("blinds")
    if not isinstance(blinds, dict):
        return None
    boss = blinds.get("boss")
    if not isinstance(boss, dict):
        return None
    name = boss.get("name")
    return name if isinstance(name, str) and name.strip() else None


def _loss_reason(state: dict[str, Any]) -> str:
    if bool(state.get("won")) is True:
        return "won"
    hands_left = state.get("hands_left")
    chips = state.get("chips")
    blind_score = state.get("blind_score")
    if (
        isinstance(hands_left, int)
        and isinstance(chips, int)
        and isinstance(blind_score, int)
    ):
        if hands_left <= 0 and chips < blind_score:
            return "out_of_hands"
        if chips < blind_score:
            return "insufficient_chips"
    return "unknown"


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    path = Path(args.log)
    runs: dict[str, dict[str, Any]] = {}

    for rec in _iter_records(path):
        run_id = rec.get("run_id")
        if not isinstance(run_id, str) or not run_id:
            continue
        slot = runs.setdefault(run_id, {"run_id": run_id})
        if rec.get("event") == "run_start":
            for key in ("seed", "deck", "stake"):
                if key in rec and slot.get(key) is None:
                    slot[key] = rec.get(key)
        if rec.get("event") == "run_end":
            state = rec.get("state")
            if isinstance(state, dict):
                slot["final_state"] = state
                slot["seed"] = slot.get("seed") or rec.get("seed") or state.get("seed")
        if _is_game_over_result(rec):
            after = rec.get("after") or {}
            if isinstance(after, dict):
                slot["final_state"] = after
                slot["seed"] = slot.get("seed") or rec.get("seed") or after.get("seed")

    finalized = [r for r in runs.values() if isinstance(r.get("final_state"), dict)]
    wins = 0
    blind_losses = Counter()
    boss_losses = Counter()
    reason_counts = Counter()

    for r in finalized:
        state = r["final_state"]
        won = bool(state.get("won")) if isinstance(state.get("won"), bool) else False
        if won:
            wins += 1
        reason = _loss_reason(state)
        reason_counts[reason] += 1
        if won:
            continue
        blind = _current_blind_name(state) or state.get("state")
        boss = _boss_name(state)
        if isinstance(blind, str) and blind:
            blind_losses[blind] += 1
        if isinstance(boss, str) and boss:
            boss_losses[boss] += 1

    payload = {
        "runs": len(finalized),
        "wins": wins,
        "win_rate": (wins / len(finalized)) if finalized else 0.0,
        "loss_reasons": dict(reason_counts),
        "losses_by_current_blind": dict(blind_losses),
        "losses_by_boss": dict(boss_losses),
    }
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
