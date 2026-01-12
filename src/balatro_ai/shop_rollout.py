from __future__ import annotations

import os
import tempfile
import time
import uuid
from collections.abc import Mapping
from typing import Any

from balatro_ai.actions import Action
from balatro_ai.config import Config
from balatro_ai.gs import gs_ante, gs_deck_cards, gs_jokers, gs_money, gs_state
from balatro_ai.intent_manager import IntentManager
from balatro_ai.pack_rollout import pack_rollout_step
from balatro_ai.rpc import BalatroRPC, BalatroRPCError
from balatro_ai.shop_policy import ShopPolicy, ShopRolloutCandidate, generate_shop_rollout_candidates


def shop_rollout_step(
    gs: Mapping[str, Any],
    cfg: Config,
    ctx: Any,
    rpc: BalatroRPC,
) -> dict:
    """Evaluate key SHOP decisions via save/load + deck-value evaluation.

    This is intentionally shallow and budgeted. It compares a handful of candidate
    SHOP action sequences, resolves any opened pack, then scores the resulting deck.
    """
    if gs_state(gs) != "SHOP":
        return rpc.gamestate()

    started = time.perf_counter()
    save_path = _save_path()
    try:
        rpc.save(save_path)
    except BalatroRPCError:
        action = ShopPolicy().choose_action(gs, cfg, ctx)
        return _apply_sequence(rpc, [action], cfg=cfg, ctx=ctx)

    try:
        sequences = generate_shop_rollout_candidates(gs, cfg, ctx, limit=cfg.shop_rollout_candidates)
        if not sequences:
            action = ShopPolicy().choose_action(gs, cfg, ctx)
            return _apply_sequence(rpc, [action], cfg=cfg, ctx=ctx)

        intent_mgr = IntentManager()
        before_money = gs_money(gs)
        before_eval = intent_mgr.evaluate(dict(gs), gs_deck_cards(gs))
        before_best = before_eval.scores.get(before_eval.intent, 0.0)

        best: tuple[float, ShopRolloutCandidate] | None = None
        trace_rows: list[dict[str, Any]] = []
        budget_s = cfg.shop_rollout_time_budget_s

        for seq in sequences:
            if budget_s is not None and (time.perf_counter() - started) >= budget_s:
                break
            try:
                rpc.load(save_path)
                after = _apply_sequence(rpc, seq.actions, cfg=cfg, ctx=ctx)
                reward, detail = _shop_reward(
                    after,
                    intent_mgr=intent_mgr,
                    before_money=before_money,
                    before_best_score=before_best,
                )
            except Exception as exc:
                reward = -1e30
                detail = {"error": type(exc).__name__}
            trace_rows.append(
                {
                    "actions": [{"kind": a.kind, "params": dict(a.params)} for a in seq.actions],
                    "heuristic_score": seq.heuristic_score,
                    "reward": reward,
                    **seq.detail,
                    **detail,
                }
            )
            if best is None or reward > best[0]:
                best = (reward, seq)

        if best is None:
            rpc.load(save_path)
            action = ShopPolicy().choose_action(gs, cfg, ctx)
            return _apply_sequence(rpc, [action], cfg=cfg, ctx=ctx)

        rpc.load(save_path)
        chosen = best[1]
        ctx.round_memory["shop_trace"] = {
            "mode": "snapshot",
            "ante": gs_ante(gs),
            "intent": _intent_text(ctx),
            "candidates": trace_rows,
            "chosen": [{"kind": a.kind, "params": dict(a.params)} for a in chosen.actions],
            "elapsed_s": time.perf_counter() - started,
        }
        return _apply_sequence(rpc, chosen.actions, cfg=cfg, ctx=ctx)
    finally:
        try:
            os.remove(save_path)
        except OSError:
            pass


def _apply_sequence(rpc: BalatroRPC, actions: list[Action], *, cfg: Config, ctx: Any) -> dict:
    state: dict[str, Any] = {}
    for action in actions:
        state = _apply_one(rpc, action)
        if gs_state(state) == "SMODS_BOOSTER_OPENED":
            if cfg.pack_rollout:
                state = dict(pack_rollout_step(state, cfg, ctx, rpc))
            else:
                from balatro_ai.pack_policy import PackPolicy

                intent = _intent_text(ctx) or ""
                action2 = PackPolicy().choose_action(state, cfg, ctx, intent)
                state = rpc.pack(
                    card=action2.params.get("card"),
                    targets=action2.params.get("targets"),
                    skip=action2.params.get("skip"),
                )
    if not state:
        state = dict(rpc.gamestate())
    return state


def _apply_one(rpc: BalatroRPC, action: Action) -> dict:
    params = action.params
    if action.kind == "buy":
        return rpc.buy(card=params.get("card"), voucher=params.get("voucher"), pack=params.get("pack"))
    if action.kind == "sell":
        return rpc.sell(joker=params.get("joker"), consumable=params.get("consumable"))
    if action.kind == "reroll":
        return rpc.reroll()
    if action.kind == "next_round":
        return rpc.next_round()
    return dict(rpc.gamestate())


def _shop_reward(
    gs: Mapping[str, Any],
    *,
    intent_mgr: IntentManager,
    before_money: int,
    before_best_score: float,
) -> tuple[float, dict[str, Any]]:
    money = gs_money(gs)
    evaluation = intent_mgr.evaluate(dict(gs), gs_deck_cards(gs))
    best_score = evaluation.scores.get(evaluation.intent, 0.0)
    # Reward improvements to predicted deck value and also preserve economy.
    reward = (best_score - before_best_score) * 2000.0 + (money - before_money) * 1.0 + len(gs_jokers(gs)) * 0.1
    return reward, {
        "money_delta": money - before_money,
        "best_intent": evaluation.intent.value,
        "best_score": best_score,
        "score_delta": best_score - before_best_score,
    }


def _intent_text(ctx: Any) -> str | None:
    value = None
    if hasattr(ctx, "round_memory"):
        value = ctx.round_memory.get("intent")
    if value is None and hasattr(ctx, "run_memory"):
        value = ctx.run_memory.get("intent")
    if isinstance(value, str):
        return value
    inner = getattr(value, "value", None)
    return inner if isinstance(inner, str) else None


def _save_path() -> str:
    filename = f"balatrobot_shop_rollout_{uuid.uuid4().hex}.jkr"
    return os.path.join(tempfile.gettempdir(), filename)

