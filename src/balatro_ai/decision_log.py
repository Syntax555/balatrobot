from __future__ import annotations

import atexit
import json
import time
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from balatro_ai.actions import Action
from balatro_ai.gs import (
    gs_ante,
    gs_blind_score,
    gs_deck_cards,
    gs_discards_left,
    gs_hand_cards,
    gs_hands_left,
    gs_jokers,
    gs_money,
    gs_pack_cards,
    gs_round_chips,
    gs_round_num,
    gs_seed,
    gs_shop_cards,
    gs_shop_packs,
    gs_shop_vouchers,
    gs_state,
)


@dataclass(frozen=True)
class DecisionLogConfig:
    path: str
    include_state: bool = True


class DecisionLogger:
    """Append-only JSONL decision logger for offline analysis and replay."""

    def __init__(self, cfg: DecisionLogConfig) -> None:
        self._cfg = cfg
        self._run_id = uuid.uuid4().hex
        self._path = Path(cfg.path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._fp = self._path.open("a", encoding="utf-8", newline="\n")
        atexit.register(self.close)

    @classmethod
    def from_config(cls, *, path: str | None, include_state: bool = True) -> DecisionLogger | None:
        if not isinstance(path, str) or not path.strip():
            return None
        return cls(DecisionLogConfig(path=path, include_state=bool(include_state)))

    def close(self) -> None:
        fp = getattr(self, "_fp", None)
        if fp is None:
            return
        try:
            fp.close()
        finally:
            self._fp = None

    def log_decision(
        self,
        *,
        step: int,
        gs: Mapping[str, Any],
        action: Action,
        run_memory: Mapping[str, Any],
        round_memory: Mapping[str, Any],
    ) -> None:
        self._write(
            {
                "event": "decision",
                "step": int(step),
                "action": {"kind": action.kind, "params": dict(action.params)},
                "intent": _intent_text(run_memory.get("intent")),
                "intent_confidence": _safe_float(run_memory.get("intent_confidence")),
                "intent_scores": run_memory.get("intent_scores"),
                "ts": time.time(),
                "run_id": self._run_id,
                "seed": gs_seed(gs),
                "state": _state_summary(gs) if self._cfg.include_state else None,
                "trace": _collect_trace(round_memory, pop=False),
            }
        )

    def log_result(
        self,
        *,
        step: int,
        before: Mapping[str, Any],
        action: Action,
        after: Mapping[str, Any],
        run_memory: Mapping[str, Any],
        round_memory: Mapping[str, Any],
    ) -> None:
        self._write(
            {
                "event": "result",
                "step": int(step),
                "action": {"kind": action.kind, "params": dict(action.params)},
                "intent": _intent_text(run_memory.get("intent")),
                "intent_confidence": _safe_float(run_memory.get("intent_confidence")),
                "intent_scores": run_memory.get("intent_scores"),
                "ts": time.time(),
                "run_id": self._run_id,
                "seed": gs_seed(after) or gs_seed(before),
                "before": _state_summary(before) if self._cfg.include_state else None,
                "after": _state_summary(after) if self._cfg.include_state else None,
                "trace": _collect_trace(round_memory, pop=True),
            }
        )

    def log_error(
        self,
        *,
        step: int,
        gs: Mapping[str, Any],
        action: Action | None,
        error: BaseException,
    ) -> None:
        self._write(
            {
                "event": "error",
                "step": int(step),
                "action": None if action is None else {"kind": action.kind, "params": dict(action.params)},
                "ts": time.time(),
                "run_id": self._run_id,
                "seed": gs_seed(gs),
                "state": _state_summary(gs) if self._cfg.include_state else None,
                "error": {"type": type(error).__name__, "message": str(error)},
            }
        )

    def _write(self, record: dict[str, Any]) -> None:
        if self._fp is None:
            return
        try:
            self._fp.write(json.dumps(record, ensure_ascii=False) + "\n")
            self._fp.flush()
        except Exception:
            # Never crash the bot due to logging.
            try:
                self._fp.flush()
            except Exception:
                pass


def _intent_text(value: Any) -> str | None:
    if isinstance(value, str):
        return value
    v = getattr(value, "value", None)
    return v if isinstance(v, str) else None


def _safe_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _state_summary(gs: Mapping[str, Any]) -> dict[str, Any]:
    blinds = gs.get("blinds")
    blind_summary: dict[str, Any] | None = None
    if isinstance(blinds, Mapping):
        blind_summary = {}
        for key in ("small", "big", "boss"):
            entry = blinds.get(key)
            if not isinstance(entry, Mapping):
                continue
                blind_summary[key] = {
                    "name": entry.get("name"),
                    "status": entry.get("status"),
                    "score": entry.get("score"),
                }
    won = gs.get("won")
    return {
        "state": gs_state(gs),
        "seed": gs_seed(gs),
        "ante": gs_ante(gs),
        "round": gs_round_num(gs),
        "money": gs_money(gs),
        "chips": gs_round_chips(gs),
        "blind_score": gs_blind_score(gs),
        "blinds": blind_summary,
        "won": won if isinstance(won, bool) else None,
        "hands_left": gs_hands_left(gs),
        "discards_left": gs_discards_left(gs),
        "hand_size": len(gs_hand_cards(gs)),
        "deck_size": len(gs_deck_cards(gs)),
        "jokers": len(gs_jokers(gs)),
        "shop_cards": len(gs_shop_cards(gs)),
        "shop_vouchers": len(gs_shop_vouchers(gs)),
        "shop_packs": len(gs_shop_packs(gs)),
        "pack_cards": len(gs_pack_cards(gs)),
    }


_TRACE_KEYS: tuple[str, ...] = (
    "boss_blind_choice",
    "shop_trace",
    "pack_trace",
    "rollout_trace",
)


def _collect_trace(memory: Mapping[str, Any], *, pop: bool) -> dict[str, Any] | None:
    if not isinstance(memory, dict):
        return None
    out: dict[str, Any] = {}
    for key in _TRACE_KEYS:
        if key not in memory:
            continue
        out[key] = memory.pop(key, None) if pop else memory.get(key)
    return out or None
