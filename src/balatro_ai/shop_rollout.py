from __future__ import annotations

import os
import tempfile
import time
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from balatro_ai.actions import Action
from balatro_ai.config import Config
from balatro_ai.gs import gs_ante, gs_deck_cards, gs_jokers, gs_money, gs_state
from balatro_ai.intent_manager import IntentManager
from balatro_ai.rpc import BalatroRPC, BalatroRPCError


@dataclass(frozen=True)
class _ShopSequence:
    actions: list[Action]
    heuristic_score: float
    detail: dict[str, Any]


def shop_rollout_step(
    gs: Mapping[str, Any],
    cfg: Config,
    ctx: Any,
    rpc: BalatroRPC,
) -> dict:
    """Evaluate key SHOP decisions via save/load + deck-value evaluation.

    This is intentionally shallow: it evaluates immediate effects and (optionally)
    resolves an opened pack using the existing pack policy before scoring.
    """
    if gs_state(gs) != "SHOP":
        return rpc.gamestate()

    started = time.perf_counter()
    save_path = _save_path()
    try:
        rpc.save(save_path)
    except BalatroRPCError:
        from balatro_ai.shop_policy import ShopPolicy

        return _apply_sequence(rpc, [_safe_action(ShopPolicy().choose_action(gs, cfg, ctx))])

    try:
        sequences = _shop_sequences(gs, cfg, ctx, max_sequences=cfg.shop_rollout_candidates)
        if not sequences:
            from balatro_ai.shop_policy import ShopPolicy

            return _apply_sequence(rpc, [_safe_action(ShopPolicy().choose_action(gs, cfg, ctx))], cfg=cfg, ctx=ctx)

        intent_mgr = IntentManager()
        before_money = gs_money(gs)
        before_eval = intent_mgr.evaluate(dict(gs), gs_deck_cards(gs))
        before_best = before_eval.scores.get(before_eval.intent, 0.0)

        best: tuple[float, _ShopSequence] | None = None
        trace_rows: list[dict[str, Any]] = []
        for seq in sequences:
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
            from balatro_ai.shop_policy import ShopPolicy

            rpc.load(save_path)
            return _apply_sequence(rpc, [_safe_action(ShopPolicy().choose_action(gs, cfg, ctx))], cfg=cfg, ctx=ctx)

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


def _shop_sequences(
    gs: Mapping[str, Any],
    cfg: Config,
    ctx: Any,
    *,
    max_sequences: int,
) -> list[_ShopSequence]:
    from balatro_ai.shop_policy import ShopPolicy

    # Seed the candidate set from the heuristic policy (what we'd do anyway).
    base_action = ShopPolicy().choose_action(gs, cfg, ctx)
    sequences: list[_ShopSequence] = [
        _ShopSequence(
            actions=[_safe_action(base_action)],
            heuristic_score=0.0,
            detail={"source": "policy"},
        )
    ]

    # Add some obvious alternatives without duplicating too much logic:
    sequences.append(
        _ShopSequence(
            actions=[Action(kind="next_round", params={})],
            heuristic_score=-1.0,
            detail={"source": "baseline"},
        )
    )

    # Reroll is a common high-leverage choice.
    from balatro_ai.shop_policy import _can_reroll as _can_reroll_internal  # type: ignore[attr-defined]
    from balatro_ai.shop_policy import _shop_memory as _shop_memory_internal  # type: ignore[attr-defined]
    from balatro_ai.gs import gs_reroll_cost

    shop_mem = _shop_memory_internal(ctx)
    if _can_reroll_internal(cfg, gs_money(gs), _reserve_guess(cfg, gs), gs_reroll_cost(gs), shop_mem):
        sequences.append(
            _ShopSequence(
                actions=[Action(kind="reroll", params={})],
                heuristic_score=0.0,
                detail={"source": "baseline"},
            )
        )

    # Add top-K buys based on ShopPolicy's candidate collection.
    try:
        sequences.extend(_top_buy_sequences(gs, cfg, ctx, max_sequences=max_sequences))
    except Exception:
        pass

    # De-dup and cap.
    unique: list[_ShopSequence] = []
    seen: set[str] = set()
    for seq in sequences:
        key = "|".join(f"{a.kind}:{sorted(a.params.items())}" for a in seq.actions)
        if key in seen:
            continue
        seen.add(key)
        unique.append(seq)
        if len(unique) >= max(1, int(max_sequences)):
            break
    return unique


def _top_buy_sequences(gs: Mapping[str, Any], cfg: Config, ctx: Any, *, max_sequences: int) -> list[_ShopSequence]:
    from balatro_ai.shop_policy import _budget as _budget_internal  # type: ignore[attr-defined]
    from balatro_ai.shop_policy import _collect_pack_candidates as _collect_pack_candidates_internal  # type: ignore[attr-defined]
    from balatro_ai.shop_policy import _collect_shop_candidates as _collect_shop_candidates_internal  # type: ignore[attr-defined]
    from balatro_ai.shop_policy import _intent as _intent_internal  # type: ignore[attr-defined]
    from balatro_ai.shop_policy import _jokers_full as _jokers_full_internal  # type: ignore[attr-defined]
    from balatro_ai.shop_policy import _reserve as _reserve_internal  # type: ignore[attr-defined]
    from balatro_ai.shop_policy import _worst_joker_index as _worst_joker_index_internal  # type: ignore[attr-defined]

    ante = gs_ante(gs)
    money = gs_money(gs)
    intent = _intent_internal(ctx) or "HIGH_CARD"
    base_reserve = _reserve_internal(cfg, ante)
    budget = _budget_internal(cfg, gs, intent, base_reserve)
    reserve = budget.reserve

    shop_candidates = _collect_shop_candidates_internal(gs, ante, money, reserve, intent, budget)
    shop_candidates = sorted(shop_candidates, key=lambda c: c.score, reverse=True)
    pack_candidates = _collect_pack_candidates_internal(gs, ante, money, reserve, intent=intent)
    pack_candidates = sorted(pack_candidates, key=lambda c: c.score, reverse=True)

    out: list[_ShopSequence] = []
    for cand in (shop_candidates[:6] + pack_candidates[:4])[: max_sequences]:
        if cand.kind == "voucher":
            out.append(
                _ShopSequence(
                    actions=[Action(kind="buy", params={"voucher": cand.index})],
                    heuristic_score=float(cand.score),
                    detail={"source": "candidate", "kind": cand.kind, "identity": dict(cand.identity)},
                )
            )
            continue
        if cand.kind == "pack":
            out.append(
                _ShopSequence(
                    actions=[Action(kind="buy", params={"pack": cand.index})],
                    heuristic_score=float(cand.score),
                    detail={"source": "candidate", "kind": cand.kind, "identity": dict(cand.identity)},
                )
            )
            continue

        # Buying a joker when full needs a sell first (same pattern as ShopPolicy).
        if cand.kind == "card" and _jokers_full_internal(gs):
            worst = _worst_joker_index_internal(gs, ante, intent)
            if worst is not None:
                out.append(
                    _ShopSequence(
                        actions=[
                            Action(kind="sell", params={"joker": worst}),
                            Action(kind="buy", params={"card": cand.index}),
                        ],
                        heuristic_score=float(cand.score),
                        detail={
                            "source": "candidate",
                            "kind": cand.kind,
                            "identity": dict(cand.identity),
                            "sell_for_space": worst,
                        },
                    )
                )
                continue

        out.append(
            _ShopSequence(
                actions=[Action(kind="buy", params={"card": cand.index})],
                heuristic_score=float(cand.score),
                detail={"source": "candidate", "kind": cand.kind, "identity": dict(cand.identity)},
            )
        )
    return out


def _apply_sequence(rpc: BalatroRPC, actions: list[Action], *, cfg: Config, ctx: Any) -> dict:
    state: dict[str, Any] = dict(rpc.gamestate())
    for action in actions:
        state = _apply_one(rpc, action)
        if gs_state(state) == "SMODS_BOOSTER_OPENED":
            # Resolve the pack quickly before scoring.
            if cfg.pack_rollout:
                from balatro_ai.pack_rollout import pack_rollout_step

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


def _reserve_guess(cfg: Config, gs: Mapping[str, Any]) -> int:
    ante = gs_ante(gs)
    if ante <= 2:
        return cfg.reserve_early
    if ante <= 5:
        return cfg.reserve_mid
    return cfg.reserve_late


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


def _safe_action(action: Action) -> Action:
    if isinstance(action, Action):
        return action
    return Action(kind="gamestate", params={})


def _save_path() -> str:
    filename = f"balatrobot_shop_rollout_{uuid.uuid4().hex}.jkr"
    return os.path.join(tempfile.gettempdir(), filename)
