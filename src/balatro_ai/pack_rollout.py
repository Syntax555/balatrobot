from __future__ import annotations

import os
import tempfile
import time
import uuid
from collections.abc import Mapping
from typing import Any

from balatro_ai.actions import Action
from balatro_ai.build_intent import BuildIntent
from balatro_ai.config import Config
from balatro_ai.gs import gs_deck_cards, gs_jokers, gs_money, gs_pack_cards, gs_state
from balatro_ai.intent_manager import IntentManager
from balatro_ai.pack_policy import choose_targets, needs_targets, target_limit
from balatro_ai.rpc import BalatroRPC, BalatroRPCError


def pack_rollout_step(
    gs: Mapping[str, Any],
    cfg: Config,
    ctx: Any,
    rpc: BalatroRPC,
) -> dict:
    """Evaluate pack choices by snapshotting and scoring resulting deck/jokers."""
    if gs_state(gs) != "SMODS_BOOSTER_OPENED":
        return rpc.gamestate()
    pack_cards = gs_pack_cards(gs)
    if not pack_cards:
        return rpc.pack(skip=True)

    started = time.perf_counter()
    save_path = _save_path()
    try:
        rpc.save(save_path)
    except BalatroRPCError:
        return _fallback_pack_action(gs, cfg, ctx, rpc)

    intent = _intent_from_ctx(ctx)
    manager = IntentManager()
    before_money = gs_money(gs)
    budget_s = cfg.pack_rollout_time_budget_s

    best: tuple[float, Action] | None = None
    traces: list[dict[str, Any]] = []
    try:
        candidates = _pack_candidates(gs, intent)
        for action in candidates:
            if budget_s is not None and (time.perf_counter() - started) >= budget_s:
                break
            try:
                rpc.load(save_path)
                after = _apply_pack_action(rpc, action)
                reward, detail = _pack_reward(after, manager, before_money)
            except Exception as exc:
                reward = -1e30
                detail = {"error": type(exc).__name__}
            traces.append(
                {
                    "action": {"kind": action.kind, "params": dict(action.params)},
                    "reward": reward,
                    **detail,
                }
            )
            if best is None or reward > best[0]:
                best = (reward, action)
        if best is None:
            return _fallback_pack_action(gs, cfg, ctx, rpc)
        rpc.load(save_path)
        chosen = best[1]
        ctx.round_memory["pack_trace"] = {
            "mode": "snapshot",
            "intent": intent.value if intent else None,
            "candidates": traces,
            "chosen": {"kind": chosen.kind, "params": dict(chosen.params)},
        }
        return _apply_pack_action(rpc, chosen)
    finally:
        try:
            os.remove(save_path)
        except OSError:
            pass


def _fallback_pack_action(gs: Mapping[str, Any], cfg: Config, ctx: Any, rpc: BalatroRPC) -> dict:
    from balatro_ai.pack_policy import PackPolicy

    intent_text = ""
    intent = _intent_from_ctx(ctx)
    if intent is not None:
        intent_text = intent.value
    action = PackPolicy().choose_action(gs, cfg, ctx, intent_text)
    return _apply_pack_action(rpc, action)


def _apply_pack_action(rpc: BalatroRPC, action: Action) -> dict:
    params = action.params
    return rpc.pack(
        card=params.get("card"),
        targets=params.get("targets"),
        skip=params.get("skip"),
    )


def _pack_candidates(gs: Mapping[str, Any], intent: BuildIntent | None) -> list[Action]:
    pack_cards = gs_pack_cards(gs)
    intent_text = intent.value if intent else ""
    out: list[Action] = [Action(kind="pack", params={"skip": True})]
    for idx, card in enumerate(pack_cards):
        if needs_targets(card):
            targets = choose_targets(gs, intent_text, max_targets=target_limit(card))
            if targets:
                out.append(Action(kind="pack", params={"card": idx, "targets": targets}))
        else:
            out.append(Action(kind="pack", params={"card": idx}))
    return out


def _pack_reward(
    gs: Mapping[str, Any],
    manager: IntentManager,
    before_money: int,
) -> tuple[float, dict[str, Any]]:
    money = gs_money(gs)
    deck_cards = gs_deck_cards(gs)
    jokers = gs_jokers(gs)
    evaluation = manager.evaluate(dict(gs), deck_cards)
    best_intent = evaluation.intent
    best_score = evaluation.scores.get(best_intent, 0.0)
    reward = (best_score * 1000.0) + (money - before_money) * 1.0 + len(jokers) * 0.1
    return reward, {
        "money_delta": money - before_money,
        "best_intent": best_intent.value,
        "best_score": best_score,
    }


def _intent_from_ctx(ctx: Any) -> BuildIntent | None:
    value = None
    if hasattr(ctx, "round_memory"):
        value = ctx.round_memory.get("intent")
    if value is None and hasattr(ctx, "run_memory"):
        value = ctx.run_memory.get("intent")
    if isinstance(value, BuildIntent):
        return value
    if isinstance(value, str):
        try:
            return BuildIntent[value.upper()]
        except KeyError:
            return None
    inner = getattr(value, "value", None)
    if isinstance(inner, str):
        try:
            return BuildIntent[inner.upper()]
        except KeyError:
            return None
    return None


def _save_path() -> str:
    filename = f"balatrobot_pack_rollout_{uuid.uuid4().hex}.jkr"
    return os.path.join(tempfile.gettempdir(), filename)

