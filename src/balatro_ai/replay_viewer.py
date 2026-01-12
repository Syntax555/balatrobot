from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from collections.abc import Iterable
from pathlib import Path
from typing import Any


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="View Balatro AI decision logs (JSONL).")
    parser.add_argument("--log", required=True, help="Path to a JSONL decision log.")
    parser.add_argument("--limit", type=int, default=0, help="Max lines to print (0 = all).")
    parser.add_argument("--event", default="", help="Filter by event type (decision/result/error).")
    parser.add_argument("--action", default="", help="Filter by action kind (e.g., buy, reroll, rollout).")
    parser.add_argument("--state", default="", help="Filter by state (e.g., SHOP).")
    parser.add_argument("--stats", action="store_true", help="Print summary stats instead of entries.")
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


def _match(record: dict[str, Any], *, event: str, action: str, state: str) -> bool:
    if event and record.get("event") != event:
        return False
    if action:
        act = record.get("action") or {}
        if not isinstance(act, dict) or act.get("kind") != action:
            return False
    if state:
        for key in ("state", "before", "after"):
            snap = record.get(key)
            if isinstance(snap, dict) and snap.get("state") == state:
                return True
        return False
    return True


def _print_record(record: dict[str, Any]) -> None:
    event = record.get("event")
    step = record.get("step")
    seed = record.get("seed")
    action = record.get("action") or {}
    action_kind = action.get("kind") if isinstance(action, dict) else None
    state = None
    snap = record.get("state")
    if isinstance(snap, dict):
        state = snap.get("state")
    if state is None:
        after = record.get("after")
        if isinstance(after, dict):
            state = after.get("state")
    intent = record.get("intent")
    money = None
    after = record.get("after") if record.get("event") == "result" else record.get("state")
    if isinstance(after, dict):
        money = after.get("money")
    print(f"step={step} event={event} state={state} action={action_kind} intent={intent} money={money} seed={seed}")
    if event == "error":
        err = record.get("error") or {}
        if isinstance(err, dict):
            print(f"  error={err.get('type')}: {err.get('message')}")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    path = Path(args.log)
    if not path.exists():
        print(f"Log not found: {path}", file=sys.stderr)
        return 2

    event = (args.event or "").strip()
    action = (args.action or "").strip()
    state = (args.state or "").strip()
    limit = int(args.limit or 0)

    records = (r for r in _iter_records(path) if _match(r, event=event, action=action, state=state))
    if args.stats:
        counts = Counter()
        action_counts = Counter()
        state_counts = Counter()
        for rec in records:
            counts[rec.get("event")] += 1
            act = rec.get("action") or {}
            if isinstance(act, dict) and act.get("kind"):
                action_counts[act["kind"]] += 1
            for key in ("state", "after"):
                snap = rec.get(key)
                if isinstance(snap, dict) and snap.get("state"):
                    state_counts[snap["state"]] += 1
                    break
        print("events:", dict(counts))
        print("actions:", dict(action_counts))
        print("states:", dict(state_counts))
        return 0

    printed = 0
    for rec in records:
        _print_record(rec)
        printed += 1
        if limit and printed >= limit:
            break
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

