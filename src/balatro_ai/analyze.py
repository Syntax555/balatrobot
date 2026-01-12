from __future__ import annotations

import argparse
import json
from collections import Counter
from collections.abc import Iterable
from pathlib import Path
from typing import Any


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Analyze Balatro AI decision logs (JSONL).")
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


def _current_blind_name(after: dict[str, Any]) -> str | None:
    blinds = after.get("blinds")
    if not isinstance(blinds, dict):
        return None
    for key in ("small", "big", "boss"):
        entry = blinds.get(key)
        if isinstance(entry, dict) and entry.get("status") == "CURRENT":
            name = entry.get("name")
            return name if isinstance(name, str) and name.strip() else None
    return None


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    path = Path(args.log)
    results_by_run: dict[str, dict[str, Any]] = {}

    for rec in _iter_records(path):
        run_id = rec.get("run_id")
        if not isinstance(run_id, str) or not run_id:
            continue
        if _is_game_over_result(rec):
            after = rec.get("after") or {}
            if not isinstance(after, dict):
                continue
            results_by_run[run_id] = {
                "seed": rec.get("seed"),
                "won": bool(after.get("won")) if isinstance(after.get("won"), bool) else False,
                "ante": after.get("ante"),
                "round": after.get("round"),
                "money": after.get("money"),
                "blind": _current_blind_name(after),
                "boss": (after.get("blinds") or {}).get("boss", {}).get("name")
                if isinstance(after.get("blinds"), dict)
                else None,
            }

    wins = sum(1 for r in results_by_run.values() if r.get("won"))
    blind_losses = Counter()
    boss_losses = Counter()
    for r in results_by_run.values():
        if r.get("won"):
            continue
        blind = r.get("blind")
        boss = r.get("boss")
        if isinstance(blind, str) and blind:
            blind_losses[blind] += 1
        if isinstance(boss, str) and boss:
            boss_losses[boss] += 1

    payload = {
        "runs": len(results_by_run),
        "wins": wins,
        "win_rate": (wins / len(results_by_run)) if results_by_run else 0.0,
        "losses_by_current_blind": dict(blind_losses),
        "losses_by_boss": dict(boss_losses),
    }
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
