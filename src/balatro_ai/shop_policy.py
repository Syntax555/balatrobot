from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
from typing import TYPE_CHECKING, Any

from balatro_ai.actions import Action
from balatro_ai.cards import card_key, card_text, card_tokens
from balatro_ai.config import Config
from balatro_ai.content_keys import load_vanilla_content_keys
from balatro_ai.gs import (
    gs_ante,
    gs_blind_score,
    gs_jokers,
    gs_money,
    gs_reroll_cost,
    gs_round_num,
    gs_shop_cards,
    gs_shop_packs,
    gs_shop_vouchers,
    gs_state,
    safe_get,
)
from balatro_ai.joker_rules import joker_rule
from balatro_ai.token_utils import has_x_token

if TYPE_CHECKING:
    from balatro_ai.policy_context import PolicyContext

logger = logging.getLogger(__name__)


_ECON_TOKENS = {"money", "interest", "discount", "coupon", "sell", "shop"}
_CHIPS_TOKENS = {"chips", "chip", "bonus"}
_MULT_TOKENS = {"mult", "multiplier", "if", "when", "each"}
_XMULT_TOKENS = {"xmult", "times"}
_SUIT_TOKENS = {
    "suit",
    "spade",
    "spades",
    "heart",
    "hearts",
    "diamond",
    "diamonds",
    "club",
    "clubs",
}

_VOUCHER_VERY_HIGH = {
    "interest",
    "discount",
    "extra",
    "hand",
    "discard",
    "shop",
    "slot",
}
_VOUCHER_MEDIUM = {"tarot", "planet", "spectral"}

SCORE_NONE = 0

ANTE_EARLY_MAX = 2
ANTE_PACK_MID_MAX = 4
ANTE_MID_MAX = 5
ANTE_ECON_PENALTY_MIN = 6

VOUCHER_SCORE_HIGH_BASE = 60
VOUCHER_SCORE_HIGH_PER_HIT = 5
VOUCHER_SCORE_MEDIUM_BASE = 30
VOUCHER_SCORE_MEDIUM_PER_HIT = 3

JOKER_ECON_LATE_PENALTY = 20

PACK_SCORE_EARLY = 10
PACK_SCORE_MID = 6
PACK_SCORE_LATE = 3
PACK_SCORE_NONE = 0

COMBO_SEARCH_WIDTH = 8

RESERVE_OVERRIDE_SCORE = 120

INDEX_INITIAL = 0
ENUMERATE_START = 1
REROLL_USED_DEFAULT = 0
REROLL_USED_INCREMENT = 1

INDEX_MIN = 0
SLICE_AFTER_FIRST_CHAR = 1

_INTENT_FLUSH = "FLUSH"
_INTENT_STRAIGHT = "STRAIGHT"
_INTENT_PAIRS = "PAIRS"
_INTENT_HIGH_CARD = "HIGH_CARD"

_TAG_SUIT_FOCUS = "suit_focus"
_TAG_FLUSH_PAYOFF = "flush_payoff"
_TAG_STRAIGHT_PAYOFF = "straight_payoff"
_TAG_STRAIGHT_SUPPORT_JOKER = "straight_support_joker"
_TAG_PAIRS_PAYOFF = "pairs_payoff"
_TAG_SMEARED = "smeared"
_TAG_REROLL_ENGINE = "reroll_engine"

_TAG_SUIT_CONVERT = "suit_convert"
_TAG_STRAIGHT_SUPPORT_CONSUMABLE = "straight_support_consumable"
_TAG_PAIRS_SUPPORT_CONSUMABLE = "pairs_support_consumable"

_TAG_REROLL_VOUCHER = "reroll_voucher"
_TAG_TAROT_SHOP = "tarot_shop"
_TAG_PLANET_SHOP = "planet_shop"

# Consumable/planet scoring is expressed as per-intent scores with a default ("*") fallback.
_CONSUMABLE_RULES: dict[str, dict[str, Any]] = {
    # Suit conversion (Tarot/Spectral): strong for FLUSH intent.
    "c_star": {
        "tags": frozenset({_TAG_SUIT_CONVERT}),
        "score": {_INTENT_FLUSH: 90, _INTENT_STRAIGHT: -10, "*": 15},
    },
    "c_moon": {
        "tags": frozenset({_TAG_SUIT_CONVERT}),
        "score": {_INTENT_FLUSH: 90, _INTENT_STRAIGHT: -10, "*": 15},
    },
    "c_sun": {
        "tags": frozenset({_TAG_SUIT_CONVERT}),
        "score": {_INTENT_FLUSH: 90, _INTENT_STRAIGHT: -10, "*": 15},
    },
    "c_world": {
        "tags": frozenset({_TAG_SUIT_CONVERT}),
        "score": {_INTENT_FLUSH: 90, _INTENT_STRAIGHT: -10, "*": 15},
    },
    "c_sigil": {
        "tags": frozenset({_TAG_SUIT_CONVERT}),
        "score": {_INTENT_FLUSH: 90, _INTENT_STRAIGHT: -10, "*": 15},
    },
    # Straight/pairs shaping (Tarot).
    "c_strength": {
        "tags": frozenset({_TAG_STRAIGHT_SUPPORT_CONSUMABLE}),
        "score": {_INTENT_STRAIGHT: 80, "*": 10},
    },
    "c_death": {
        "tags": frozenset({_TAG_PAIRS_SUPPORT_CONSUMABLE}),
        "score": {_INTENT_PAIRS: 80, "*": 15},
    },
    # Planets: hand-type scaling.
    "c_jupiter": {
        "tags": frozenset({_TAG_PLANET_SHOP}),
        "score": {_INTENT_FLUSH: 70, "*": 10},
    },
    "c_ceres": {
        "tags": frozenset({_TAG_PLANET_SHOP}),
        "score": {_INTENT_FLUSH: 70, "*": 10},
    },
    "c_eris": {
        "tags": frozenset({_TAG_PLANET_SHOP}),
        "score": {_INTENT_FLUSH: 70, "*": 10},
    },
    "c_saturn": {
        "tags": frozenset({_TAG_PLANET_SHOP}),
        "score": {_INTENT_STRAIGHT: 70, "*": 10},
    },
    "c_neptune": {
        "tags": frozenset({_TAG_PLANET_SHOP}),
        "score": {_INTENT_STRAIGHT: 70, "*": 10},
    },
    "c_mercury": {
        "tags": frozenset({_TAG_PLANET_SHOP}),
        "score": {_INTENT_PAIRS: 60, "*": 5},
    },
    "c_venus": {
        "tags": frozenset({_TAG_PLANET_SHOP}),
        "score": {_INTENT_PAIRS: 60, "*": 5},
    },
    "c_uranus": {
        "tags": frozenset({_TAG_PLANET_SHOP}),
        "score": {_INTENT_PAIRS: 60, "*": 5},
    },
    "c_earth": {
        "tags": frozenset({_TAG_PLANET_SHOP}),
        "score": {_INTENT_PAIRS: 60, "*": 5},
    },
    "c_mars": {
        "tags": frozenset({_TAG_PLANET_SHOP}),
        "score": {_INTENT_PAIRS: 60, "*": 5},
    },
    "c_planet_x": {
        "tags": frozenset({_TAG_PLANET_SHOP}),
        "score": {_INTENT_PAIRS: 60, "*": 5},
    },
    "c_pluto": {
        "tags": frozenset({_TAG_PLANET_SHOP}),
        "score": {_INTENT_HIGH_CARD: 40, "*": 10},
    },
    # Raw economy (Tarot).
    "c_hermit": {"tags": frozenset(), "score": {"*": 35}},
    "c_temperance": {"tags": frozenset(), "score": {"*": 25}},
    # Remaining Tarots: keep explicit coverage and rough strategic value.
    "c_fool": {"tags": frozenset(), "score": {"*": 20}},
    "c_magician": {"tags": frozenset(), "score": {"*": 20}},
    "c_high_priestess": {"tags": frozenset(), "score": {"*": 30}},
    "c_empress": {"tags": frozenset(), "score": {"*": 25}},
    "c_emperor": {"tags": frozenset(), "score": {"*": 25}},
    "c_heirophant": {"tags": frozenset(), "score": {"*": 20}},
    "c_lovers": {
        "tags": frozenset({_TAG_SUIT_CONVERT}),
        "score": {_INTENT_FLUSH: 60, "*": 15},
    },
    "c_chariot": {"tags": frozenset(), "score": {"*": 22}},
    "c_justice": {"tags": frozenset(), "score": {"*": 22}},
    "c_wheel_of_fortune": {"tags": frozenset(), "score": {"*": 30}},
    "c_hanged_man": {"tags": frozenset(), "score": {"*": 20}},
    "c_devil": {"tags": frozenset(), "score": {"*": 20}},
    "c_tower": {"tags": frozenset(), "score": {"*": 18}},
    "c_judgement": {"tags": frozenset(), "score": {"*": 45}},
    # Spectrals: very high early/mid impact.
    "c_familiar": {"tags": frozenset(), "score": {"*": 35}},
    "c_grim": {"tags": frozenset(), "score": {"*": 35}},
    "c_incantation": {"tags": frozenset(), "score": {"*": 35}},
    "c_talisman": {"tags": frozenset(), "score": {"*": 25}},
    "c_aura": {"tags": frozenset(), "score": {"*": 30}},
    "c_wraith": {"tags": frozenset(), "score": {"*": 80}},
    "c_ouija": {
        "tags": frozenset({_TAG_PAIRS_SUPPORT_CONSUMABLE}),
        "score": {_INTENT_PAIRS: 70, "*": 20},
    },
    "c_ectoplasm": {"tags": frozenset(), "score": {"*": 60}},
    "c_immolate": {"tags": frozenset(), "score": {"*": 55}},
    "c_ankh": {"tags": frozenset(), "score": {"*": 85}},
    "c_deja_vu": {"tags": frozenset(), "score": {"*": 30}},
    "c_hex": {"tags": frozenset(), "score": {"*": 75}},
    "c_trance": {"tags": frozenset(), "score": {"*": 20}},
    "c_medium": {"tags": frozenset(), "score": {"*": 20}},
    "c_cryptid": {"tags": frozenset(), "score": {"*": 50}},
    "c_soul": {"tags": frozenset(), "score": {"*": 90}},
    "c_black_hole": {"tags": frozenset(), "score": {"*": 70}},
}

_VOUCHER_RULES: dict[str, dict[str, Any]] = {
    "v_blank": {"base": -50},
    "v_antimatter": {"base": 80},
    "v_clearance_sale": {"base": 80},
    "v_liquidation": {"base": 80},
    "v_overstock_norm": {"base": 80},
    "v_overstock_plus": {"base": 80},
    "v_seed_money": {"base": 80},
    "v_money_tree": {"base": 80},
    "v_grabber": {"base": 80},
    "v_nacho_tong": {"base": 80},
    "v_wasteful": {"base": 80, "intent": {_INTENT_STRAIGHT: 25}},
    "v_recyclomancy": {"base": 80, "intent": {_INTENT_STRAIGHT: 25}},
    "v_paint_brush": {"base": 80},
    "v_palette": {"base": 80},
    "v_reroll_surplus": {"base": 40, "tags": frozenset({_TAG_REROLL_VOUCHER})},
    "v_reroll_glut": {"base": 40, "tags": frozenset({_TAG_REROLL_VOUCHER})},
    "v_tarot_merchant": {
        "intent": {_INTENT_FLUSH: 15},
        "tags": frozenset({_TAG_TAROT_SHOP}),
    },
    "v_tarot_tycoon": {
        "intent": {_INTENT_FLUSH: 15},
        "tags": frozenset({_TAG_TAROT_SHOP}),
    },
    "v_planet_merchant": {
        "intent": {_INTENT_FLUSH: 10, _INTENT_STRAIGHT: 10, _INTENT_PAIRS: 10},
        "tags": frozenset({_TAG_PLANET_SHOP}),
    },
    "v_planet_tycoon": {
        "intent": {_INTENT_FLUSH: 10, _INTENT_STRAIGHT: 10, _INTENT_PAIRS: 10},
        "tags": frozenset({_TAG_PLANET_SHOP}),
    },
    "v_telescope": {"base": 55, "tags": frozenset({_TAG_PLANET_SHOP})},
    "v_observatory": {"base": 65, "tags": frozenset({_TAG_PLANET_SHOP})},
    "v_omen_globe": {"base": 35},
    "v_magic_trick": {"base": 15},
    "v_hone": {"base": 25},
    "v_glow_up": {"base": 40},
    "v_illusion": {"base": 30},
    "v_directors_cut": {"base": 25},
    "v_retcon": {"base": 35},
    "v_crystal_ball": {"base": 45},
    "v_hieroglyph": {"base": 45},
    "v_petroglyph": {"base": 40},
}

def _default_consumable_rule() -> dict[str, Any]:
    return {"score": {"*": 0}, "tags": frozenset()}


def _default_voucher_rule() -> dict[str, Any]:
    return {"base": 0, "intent": {"*": 0}, "tags": frozenset()}


@lru_cache(maxsize=1)
def _all_consumable_rules() -> dict[str, dict[str, Any]]:
    vanilla = load_vanilla_content_keys().consumables
    rules = {key: _default_consumable_rule() for key in vanilla}
    rules.update(_CONSUMABLE_RULES)
    return rules


@lru_cache(maxsize=1)
def _all_voucher_rules() -> dict[str, dict[str, Any]]:
    vanilla = load_vanilla_content_keys().vouchers
    rules = {key: _default_voucher_rule() for key in vanilla}
    for key, tuned in _VOUCHER_RULES.items():
        merged = _default_voucher_rule()
        if isinstance(tuned, Mapping):
            merged.update(tuned)
            intent_map = tuned.get("intent")
            if isinstance(intent_map, Mapping):
                merged_intent: dict[str, Any] = {"*": 0}
                merged_intent.update(intent_map)
                merged["intent"] = merged_intent
        rules[key] = merged
    return rules


def consumable_rule(key: str | None) -> Mapping[str, Any] | None:
    if not key:
        return None
    normalized = key.lower()
    if not normalized.startswith("c_"):
        return None
    return _all_consumable_rules().get(normalized, _default_consumable_rule())


def voucher_rule(key: str | None) -> Mapping[str, Any] | None:
    if not key:
        return None
    normalized = key.lower()
    if not normalized.startswith("v_"):
        return None
    return _all_voucher_rules().get(normalized, _default_voucher_rule())

_JOKER_INTENT_TAG_WEIGHTS: dict[str, dict[str, int]] = {
    _INTENT_FLUSH: {
        _TAG_FLUSH_PAYOFF: 60,
        _TAG_SUIT_FOCUS: 45,
        _TAG_STRAIGHT_PAYOFF: -15,
        _TAG_STRAIGHT_SUPPORT_JOKER: -15,
    },
    _INTENT_STRAIGHT: {
        _TAG_STRAIGHT_PAYOFF: 60,
        _TAG_STRAIGHT_SUPPORT_JOKER: 45,
        _TAG_SUIT_FOCUS: -45,
    },
    _INTENT_PAIRS: {
        _TAG_PAIRS_PAYOFF: 55,
        _TAG_FLUSH_PAYOFF: -10,
        _TAG_STRAIGHT_PAYOFF: -10,
    },
    _INTENT_HIGH_CARD: {
        _TAG_SUIT_FOCUS: -5,
        _TAG_FLUSH_PAYOFF: -5,
        _TAG_STRAIGHT_PAYOFF: -5,
    },
}

_PACK_TYPE_RULES: dict[str, dict[str, Any]] = {
    # Defaults are intentionally small modifiers; the baseline is ante-driven.
    "buffoon": {"bonus": 4},
    "standard": {"bonus": 0},
    "arcana": {"bonus": 1},
    "celestial": {"bonus": 1},
    "spectral": {"bonus": 2},
    "other": {"bonus": 0},
}


@dataclass(frozen=True)
class _Candidate:
    kind: str
    index: int
    score: int
    cost: int
    identity: dict[str, str]


@dataclass(frozen=True)
class _Budget:
    reserve: int
    buy_threshold: int
    reroll_threshold: int
    cost_weight: float


class ShopPolicy:
    """Shop decision policy for choosing a single action."""

    def choose_action(
        self, gs: Mapping[str, Any], cfg: Config, ctx: PolicyContext
    ) -> Action:
        """Choose an action while in SHOP state."""
        if gs_state(gs) != "SHOP":
            raise ValueError(f"ShopPolicy used outside SHOP state: {gs_state(gs)}")
        shop_mem = _shop_memory(ctx)
        intent = _intent(ctx) or _INTENT_HIGH_CARD
        category_scores = _joker_category_scores(cfg)
        trace_base: dict[str, Any] = {
            "intent": intent,
            "ante": gs_ante(gs),
            "round": gs_round_num(gs),
            "money": gs_money(gs),
            "reroll_cost": gs_reroll_cost(gs),
            "rerolls_used": shop_mem.get("rerolls_used", REROLL_USED_DEFAULT),
        }
        pending_actions = shop_mem.get("pending_actions")
        if isinstance(pending_actions, list) and pending_actions:
            action = _next_pending_action(
                pending_actions, gs, intent=intent, category_scores=category_scores
            )
            if action is not None:
                ctx.round_memory["shop_trace"] = {
                    **trace_base,
                    "mode": "pending",
                    "pending_actions": list(pending_actions),
                    "chosen": {"kind": action.kind, "params": dict(action.params)},
                }
                logger.debug(
                    "ShopPolicy: executing pending action=%s params=%s",
                    action.kind,
                    action.params,
                )
                return action
            logger.debug("ShopPolicy: pending actions invalidated (item not found)")
            shop_mem.pop("pending_actions", None)
        money = gs_money(gs)
        ante = gs_ante(gs)
        base_reserve = _reserve(cfg, ante)
        budget = _budget(cfg, gs, intent, base_reserve)
        reserve = budget.reserve
        reroll_cost = gs_reroll_cost(gs)
        logger.debug(
            "ShopPolicy: money=%s ante=%s intent=%s reserve=%s->%s reroll_cost=%s rerolls_used=%s",
            money,
            ante,
            intent,
            base_reserve,
            reserve,
            reroll_cost,
            shop_mem.get("rerolls_used", REROLL_USED_DEFAULT),
        )
        shop_candidates = _collect_shop_candidates(
            gs, ante, money, reserve, intent, budget, category_scores=category_scores
        )
        candidates_sorted = sorted(
            shop_candidates, key=lambda item: item.score, reverse=True
        )
        trace_candidates = [
            {
                "kind": c.kind,
                "index": c.index,
                "score": c.score,
                "cost": c.cost,
                "identity": dict(c.identity),
            }
            for c in candidates_sorted[:12]
        ]
        plan_result = _best_purchase_plan(
            shop_candidates,
            money=money,
            reserve=reserve,
            intent=intent,
            ante=ante,
        )
        plan = plan_result[0] if plan_result else None
        plan_score = plan_result[1] if plan_result else SCORE_NONE
        if plan and plan_score >= budget.buy_threshold:
            if plan[0].kind == "card" and _jokers_full(gs):
                _set_pending_buys(shop_mem, plan)
                worst_index = _worst_joker_index(
                    gs, ante, intent, category_scores=category_scores
                )
                if worst_index is not None:
                    ctx.round_memory["shop_trace"] = {
                        **trace_base,
                        "mode": "sell_for_space",
                        "reserve": reserve,
                        "buy_threshold": budget.buy_threshold,
                        "plan_score": plan_score,
                        "plan": [
                            dict(item.identity)
                            | {"kind": item.kind, "index": item.index}
                            for item in plan
                        ],
                        "candidates": trace_candidates,
                        "chosen": {"kind": "sell", "params": {"joker": worst_index}},
                    }
                    return Action(kind="sell", params={"joker": worst_index})
            _set_pending_buys(shop_mem, plan[1:])
            chosen = _buy_action(plan[0])
            ctx.round_memory["shop_trace"] = {
                **trace_base,
                "mode": "buy_plan",
                "reserve": reserve,
                "buy_threshold": budget.buy_threshold,
                "plan_score": plan_score,
                "plan": [
                    dict(item.identity) | {"kind": item.kind, "index": item.index}
                    for item in plan
                ],
                "candidates": trace_candidates,
                "chosen": {"kind": chosen.kind, "params": dict(chosen.params)},
            }
            return _buy_action(plan[0])

        best_shop = plan[0] if plan else None
        best_score = plan_score if best_shop else SCORE_NONE
        if _should_reroll(
            cfg, money, reserve, reroll_cost, shop_mem, best_score, budget
        ):
            shop_mem["rerolls_used"] = (
                shop_mem.get("rerolls_used", REROLL_USED_DEFAULT)
                + REROLL_USED_INCREMENT
            )
            shop_mem.pop("pending_actions", None)
            logger.debug(
                "ShopPolicy: reroll (rerolls_used=%s)", shop_mem["rerolls_used"]
            )
            ctx.round_memory["shop_trace"] = {
                **trace_base,
                "mode": "reroll",
                "reserve": reserve,
                "reroll_threshold": budget.reroll_threshold,
                "best_score": best_score,
                "candidates": trace_candidates,
                "chosen": {"kind": "reroll", "params": {}},
            }
            return Action(kind="reroll", params={})

        pack_candidates = _collect_pack_candidates(
            gs, ante, money, reserve, intent=intent
        )
        packs_sorted = sorted(
            pack_candidates, key=lambda item: item.score, reverse=True
        )
        trace_packs = [
            {
                "kind": c.kind,
                "index": c.index,
                "score": c.score,
                "cost": c.cost,
                "identity": dict(c.identity),
            }
            for c in packs_sorted[:8]
        ]
        best_pack = _best_candidate(pack_candidates)
        if best_pack is not None and best_pack.score > SCORE_NONE:
            logger.debug("ShopPolicy: choosing pack candidate=%s", best_pack)
            chosen = _buy_action(best_pack)
            ctx.round_memory["shop_trace"] = {
                **trace_base,
                "mode": "buy_pack",
                "reserve": reserve,
                "best_pack": dict(best_pack.identity)
                | {"index": best_pack.index, "score": best_pack.score},
                "candidates": trace_candidates,
                "pack_candidates": trace_packs,
                "chosen": {"kind": chosen.kind, "params": dict(chosen.params)},
            }
            return _buy_action(best_pack)

        logger.debug("ShopPolicy: next_round (no good buys)")
        ctx.round_memory["shop_trace"] = {
            **trace_base,
            "mode": "next_round",
            "reserve": reserve,
            "best_score": best_score,
            "candidates": trace_candidates,
            "pack_candidates": trace_packs,
            "chosen": {"kind": "next_round", "params": {}},
        }
        return Action(kind="next_round", params={})


@dataclass(frozen=True)
class ShopRolloutCandidate:
    """A candidate action sequence for snapshot-based SHOP evaluation."""

    actions: list[Action]
    heuristic_score: float
    detail: dict[str, Any]


def generate_shop_rollout_candidates(
    gs: Mapping[str, Any],
    cfg: Config,
    ctx: PolicyContext,
    *,
    limit: int,
) -> list[ShopRolloutCandidate]:
    """Generate safe, shallow candidate sequences to evaluate from a SHOP snapshot."""
    if gs_state(gs) != "SHOP":
        return []
    max_items = max(1, int(limit))
    intent = _intent(ctx) or _INTENT_HIGH_CARD
    shop_mem = _shop_memory(ctx)
    category_scores = _joker_category_scores(cfg)

    candidates: list[ShopRolloutCandidate] = []

    base_action = ShopPolicy().choose_action(gs, cfg, ctx)
    candidates.append(
        ShopRolloutCandidate(
            actions=[base_action],
            heuristic_score=0.0,
            detail={"source": "policy"},
        )
    )

    candidates.append(
        ShopRolloutCandidate(
            actions=[Action(kind="next_round", params={})],
            heuristic_score=-1.0,
            detail={"source": "baseline"},
        )
    )

    money = gs_money(gs)
    ante = gs_ante(gs)
    reserve = _budget(cfg, gs, intent, _reserve(cfg, ante)).reserve
    reroll_cost = gs_reroll_cost(gs)
    if _can_reroll(cfg, money, reserve, reroll_cost, shop_mem):
        candidates.append(
            ShopRolloutCandidate(
                actions=[Action(kind="reroll", params={})],
                heuristic_score=0.0,
                detail={"source": "baseline"},
            )
        )

    budget = _budget(cfg, gs, intent, _reserve(cfg, ante))
    shop_candidates = _collect_shop_candidates(
        gs,
        ante,
        money,
        budget.reserve,
        intent,
        budget,
        category_scores=category_scores,
    )
    shop_candidates = sorted(shop_candidates, key=lambda c: c.score, reverse=True)
    pack_candidates = _collect_pack_candidates(
        gs, ante, money, budget.reserve, intent=intent
    )
    pack_candidates = sorted(pack_candidates, key=lambda c: c.score, reverse=True)

    for cand in (shop_candidates[:6] + pack_candidates[:4])[:max_items]:
        if cand.kind == "voucher":
            candidates.append(
                ShopRolloutCandidate(
                    actions=[Action(kind="buy", params={"voucher": cand.index})],
                    heuristic_score=float(cand.score),
                    detail={
                        "source": "candidate",
                        "kind": cand.kind,
                        "identity": dict(cand.identity),
                    },
                )
            )
            continue
        if cand.kind == "pack":
            candidates.append(
                ShopRolloutCandidate(
                    actions=[Action(kind="buy", params={"pack": cand.index})],
                    heuristic_score=float(cand.score),
                    detail={
                        "source": "candidate",
                        "kind": cand.kind,
                        "identity": dict(cand.identity),
                    },
                )
            )
            continue
        if cand.kind == "card" and _jokers_full(gs):
            worst = _worst_joker_index(gs, ante, intent, category_scores=category_scores)
            if worst is not None:
                candidates.append(
                    ShopRolloutCandidate(
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
        candidates.append(
            ShopRolloutCandidate(
                actions=[Action(kind="buy", params={"card": cand.index})],
                heuristic_score=float(cand.score),
                detail={
                    "source": "candidate",
                    "kind": cand.kind,
                    "identity": dict(cand.identity),
                },
            )
        )

    # Deduplicate and cap.
    seen: set[str] = set()
    unique: list[ShopRolloutCandidate] = []
    for cand in candidates:
        key = "|".join(f"{a.kind}:{sorted(a.params.items())}" for a in cand.actions)
        if key in seen:
            continue
        seen.add(key)
        unique.append(cand)
        if len(unique) >= max_items:
            break
    return unique


def _reserve(cfg: Config, ante: int) -> int:
    if ante <= ANTE_EARLY_MAX:
        return cfg.reserve_early
    if ante <= ANTE_MID_MAX:
        return cfg.reserve_mid
    return cfg.reserve_late


def _collect_shop_candidates(
    gs: Mapping[str, Any],
    ante: int,
    money: int,
    reserve: int,
    intent: str,
    budget: _Budget,
    *,
    category_scores: Mapping[str, int],
) -> list[_Candidate]:
    candidates: list[_Candidate] = []
    jokers = gs_jokers(gs)
    for index, voucher in enumerate(gs_shop_vouchers(gs)):
        cost = _item_cost(voucher)
        score = _score_voucher(
            voucher,
            intent=intent,
            ante=ante,
            cost=cost,
            budget=budget,
            existing_jokers=jokers,
        )
        if not _affordable(money, reserve, cost, score=score):
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(
                    "Shop voucher skipped (unaffordable): idx=%s cost=%s money=%s reserve=%s score=%s key=%s text=%r",
                    index,
                    cost,
                    money,
                    reserve,
                    score,
                    card_key(voucher),
                    _item_text(voucher),
                )
            continue
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(
                "Shop voucher option: idx=%s cost=%s score=%s key=%s text=%r",
                index,
                cost,
                score,
                card_key(voucher),
                _item_text(voucher),
            )
        candidates.append(
            _Candidate(
                kind="voucher",
                index=index,
                score=score,
                cost=cost,
                identity=_item_identity(voucher),
            )
        )
    for index, card in enumerate(gs_shop_cards(gs)):
        cost = _item_cost(card)
        score = _score_shop_card(
            card,
            intent=intent,
            ante=ante,
            cost=cost,
            budget=budget,
            gs=gs,
            category_scores=category_scores,
        )
        if not _affordable(money, reserve, cost, score=score):
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(
                    "Shop card skipped (unaffordable): idx=%s cost=%s money=%s reserve=%s score=%s key=%s text=%r",
                    index,
                    cost,
                    money,
                    reserve,
                    score,
                    card_key(card),
                    _item_text(card),
                )
            continue
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(
                "Shop card option: idx=%s cost=%s score=%s key=%s text=%r",
                index,
                cost,
                score,
                card_key(card),
                _item_text(card),
            )
        candidates.append(
            _Candidate(
                kind="card",
                index=index,
                score=score,
                cost=cost,
                identity=_item_identity(card),
            )
        )
    return candidates


def _collect_pack_candidates(
    gs: Mapping[str, Any],
    ante: int,
    money: int,
    reserve: int,
    *,
    intent: str,
) -> list[_Candidate]:
    candidates: list[_Candidate] = []
    pack_base = _score_pack(ante)
    logger.debug("Shop pack base score: ante=%s pack_score=%s", ante, pack_base)
    if pack_base <= SCORE_NONE:
        return candidates
    for index, pack in enumerate(gs_shop_packs(gs)):
        cost = _item_cost(pack)
        if not _affordable(money, reserve, cost):
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(
                    "Shop pack skipped (unaffordable): idx=%s cost=%s money=%s reserve=%s key=%s text=%r",
                    index,
                    cost,
                    money,
                    reserve,
                    card_key(pack),
                    _item_text(pack),
                )
            continue
        score = _score_pack_item(pack, ante=ante, intent=intent)
        if score <= SCORE_NONE:
            continue
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(
                "Shop pack option: idx=%s cost=%s score=%s key=%s text=%r",
                index,
                cost,
                score,
                card_key(pack),
                _item_text(pack),
            )
        candidates.append(
            _Candidate(
                kind="pack",
                index=index,
                score=score,
                cost=cost,
                identity=_item_identity(pack),
            )
        )
    return candidates


def _best_candidate(candidates: list[_Candidate]) -> _Candidate | None:
    best: _Candidate | None = None
    for candidate in candidates:
        if best is None or candidate.score > best.score:
            best = candidate
    return best


def _can_reroll(
    cfg: Config,
    money: int,
    reserve: int,
    reroll_cost: int,
    shop_mem: Mapping[str, Any],
) -> bool:
    if money - reroll_cost < reserve:
        return False
    used = shop_mem.get("rerolls_used", REROLL_USED_DEFAULT)
    if not isinstance(used, int):
        used = REROLL_USED_DEFAULT
    return used < cfg.max_rerolls_per_shop


def _buy_action(candidate: _Candidate) -> Action:
    if candidate.kind == "voucher":
        return Action(kind="buy", params={"voucher": candidate.index})
    if candidate.kind == "pack":
        return Action(kind="buy", params={"pack": candidate.index})
    return Action(kind="buy", params={"card": candidate.index})


def _next_pending_action(
    pending_actions: list[Any],
    gs: Mapping[str, Any],
    *,
    intent: str,
    category_scores: Mapping[str, int],
) -> Action | None:
    if not pending_actions:
        return None
    head = pending_actions[0]
    if not isinstance(head, Mapping):
        pending_actions.clear()
        return None
    kind = head.get("kind")
    item_kind = head.get("item_kind")
    identity = head.get("identity")
    if kind != "buy" or item_kind not in {"voucher", "pack", "card"}:
        pending_actions.clear()
        return None
    if not isinstance(identity, Mapping):
        pending_actions.clear()
        return None
    index = _find_item_index(gs, item_kind, identity)
    if index is None:
        pending_actions.clear()
        return None
    if item_kind == "card" and _jokers_full(gs):
        worst_index = _worst_joker_index(
            gs, gs_ante(gs), intent, category_scores=category_scores
        )
        if worst_index is not None:
            return Action(kind="sell", params={"joker": worst_index})
    pending_actions.pop(0)
    candidate = _Candidate(
        kind=item_kind, index=index, score=0, cost=0, identity=dict(identity)
    )
    return _buy_action(candidate)


def _jokers_full(gs: Mapping[str, Any]) -> bool:
    slots = _joker_slots(gs)
    if slots is None:
        return False
    return len(gs_jokers(gs)) >= slots


def _joker_slots(gs: Mapping[str, Any]) -> int | None:
    for key in (
        "joker_slots",
        "joker_limit",
        "joker_max",
        "jokers_limit",
        "jokers_max",
    ):
        value = safe_get(gs, [key], None)
        if isinstance(value, int) and not isinstance(value, bool):
            return value
    return None


def _worst_joker_index(
    gs: Mapping[str, Any], ante: int, intent: str, *, category_scores: Mapping[str, int]
) -> int | None:
    jokers = gs_jokers(gs)
    if not jokers:
        return None
    worst_index = INDEX_INITIAL
    worst_score = _score_joker(
        jokers[INDEX_INITIAL],
        ante=ante,
        intent=intent,
        existing_jokers=jokers,
        category_scores=category_scores,
    )
    for index, joker in enumerate(jokers[ENUMERATE_START:], start=ENUMERATE_START):
        score = _score_joker(
            joker,
            ante=ante,
            intent=intent,
            existing_jokers=jokers,
            category_scores=category_scores,
        )
        if score < worst_score:
            worst_score = score
            worst_index = index
    return worst_index


def _item_text(item: Mapping[str, Any]) -> str:
    return card_text(item)


def _item_cost(item: Mapping[str, Any]) -> int:
    for key in ("cost", "price", "amount"):
        value = item.get(key)
        if isinstance(value, int) and not isinstance(value, bool):
            return value
        if isinstance(value, Mapping):
            buy = value.get("buy")
            if isinstance(buy, int) and not isinstance(buy, bool):
                return buy
    return SCORE_NONE


def _tokens(text: str) -> set[str]:
    return card_tokens(text)


def _score_by_intent(score_map: Any, intent: str) -> int:
    if not isinstance(score_map, Mapping):
        return 0
    value = score_map.get(intent, score_map.get("*", 0))
    return value if isinstance(value, int) else 0


def _pack_type(key: str) -> str:
    lowered = (key or "").lower()
    if lowered.startswith("p_buffoon"):
        return "buffoon"
    if lowered.startswith("p_standard"):
        return "standard"
    if lowered.startswith("p_arcana"):
        return "arcana"
    if lowered.startswith("p_celestial"):
        return "celestial"
    if lowered.startswith("p_spectral"):
        return "spectral"
    return "other"


def _consumable_tags(key: str, tokens: set[str]) -> frozenset[str]:
    tags: set[str] = set()
    rule = consumable_rule(key)
    if isinstance(rule, Mapping):
        rule_tags = rule.get("tags")
        if isinstance(rule_tags, (set, frozenset)):
            tags |= set(rule_tags)
    return frozenset(tags)


def _joker_tags(key: str | None, tokens: set[str]) -> frozenset[str]:
    tags: set[str] = set()
    rule = joker_rule(key)
    if rule is not None:
        tags |= set(rule.tags)
    # Token inference: keeps new content usable without adding explicit rules.
    if tokens & _SUIT_TOKENS:
        tags.add(_TAG_SUIT_FOCUS)
    if "flush" in tokens:
        tags.add(_TAG_FLUSH_PAYOFF)
    if "straight" in tokens:
        tags.add(_TAG_STRAIGHT_PAYOFF)
    if {"pair", "pairs", "kind"} & tokens:
        tags.add(_TAG_PAIRS_PAYOFF)
    return frozenset(tags)


def _item_tags(key: str, tokens: set[str]) -> frozenset[str]:
    if key.startswith("j_"):
        return _joker_tags(key, tokens)
    if key.startswith("c_"):
        return _consumable_tags(key, tokens)
    return frozenset()


def _joker_intent_tag_bonus(tags: frozenset[str], intent: str) -> int:
    weights = (
        _JOKER_INTENT_TAG_WEIGHTS.get(intent)
        or _JOKER_INTENT_TAG_WEIGHTS[_INTENT_HIGH_CARD]
    )
    return sum(weights.get(tag, 0) for tag in tags)


def _score_voucher(
    voucher: Mapping[str, Any],
    *,
    intent: str,
    ante: int,
    cost: int,
    budget: _Budget,
    existing_jokers: list[dict],
) -> int:
    key = card_key(voucher) or ""
    text = _item_text(voucher)
    tokens = _tokens(text)
    score = SCORE_NONE

    rule = voucher_rule(key)
    if isinstance(rule, Mapping):
        base = rule.get("base")
        if isinstance(base, int):
            score += base
        score += _score_by_intent(rule.get("intent"), intent)

    high_hits = tokens & _VOUCHER_VERY_HIGH
    if high_hits:
        score += VOUCHER_SCORE_HIGH_BASE + VOUCHER_SCORE_HIGH_PER_HIT * len(high_hits)
    medium_hits = tokens & _VOUCHER_MEDIUM
    if medium_hits:
        score += VOUCHER_SCORE_MEDIUM_BASE + VOUCHER_SCORE_MEDIUM_PER_HIT * len(
            medium_hits
        )

    score += _voucher_synergy_bonus(
        key, tokens=tokens, intent=intent, existing_jokers=existing_jokers
    )
    score += _cost_adjust(score, cost=cost, budget=budget, ante=ante)
    return score


def _voucher_synergy_bonus(
    key: str,
    *,
    tokens: set[str],
    intent: str,
    existing_jokers: list[dict],
) -> int:
    if not existing_jokers:
        return 0
    existing_tags: set[str] = set()
    for joker in existing_jokers:
        joker_key = card_key(joker) or ""
        if not joker_key:
            continue
        joker_tokens = _tokens(_item_text(joker))
        existing_tags |= set(_joker_tags(joker_key, joker_tokens))

    rule = voucher_rule(key)
    voucher_tags: set[str] = set()
    if isinstance(rule, Mapping):
        tags = rule.get("tags")
        if isinstance(tags, (set, frozenset)):
            voucher_tags |= set(tags)

    bonus = 0
    if _TAG_REROLL_VOUCHER in voucher_tags and _TAG_REROLL_ENGINE in existing_tags:
        bonus += 25
    if (
        intent == _INTENT_FLUSH
        and _TAG_TAROT_SHOP in voucher_tags
        and _TAG_SUIT_FOCUS in existing_tags
    ):
        bonus += 10
    if _TAG_PLANET_SHOP in voucher_tags and (
        _TAG_FLUSH_PAYOFF in existing_tags or _TAG_STRAIGHT_PAYOFF in existing_tags
    ):
        bonus += 8
    return bonus


def _score_joker(
    joker: Mapping[str, Any],
    *,
    ante: int,
    intent: str,
    existing_jokers: list[dict],
    category_scores: Mapping[str, int],
) -> int:
    key = card_key(joker)
    text = _item_text(joker)
    rule = joker_rule(key, text)
    tokens = _tokens(text)

    score = SCORE_NONE
    if rule is not None:
        score += rule.resolved_base_score(category_scores=category_scores)
        if rule.category == "econ" and ante >= ANTE_ECON_PENALTY_MIN:
            xmult = bool(tokens & _XMULT_TOKENS) or _has_x_token(tokens)
            mult = bool(tokens & _MULT_TOKENS)
            chips = bool(tokens & _CHIPS_TOKENS)
            if not (xmult or mult or chips):
                score -= JOKER_ECON_LATE_PENALTY
        score += _intent_adjust_for_joker(
            key, tokens=tokens, intent=intent, existing_jokers=existing_jokers
        )
        return score

    xmult = bool(tokens & _XMULT_TOKENS) or _has_x_token(tokens)
    mult = bool(tokens & _MULT_TOKENS)
    chips = bool(tokens & _CHIPS_TOKENS)
    econ = "$" in text or bool(tokens & _ECON_TOKENS)

    if xmult:
        score += category_scores.get("xmult", 0)
    elif mult:
        score += category_scores.get("mult", 0)
    elif chips:
        score += category_scores.get("chips", 0)
    elif econ:
        score += category_scores.get("econ", 0)
    else:
        score += category_scores.get("default", 0)

    if econ and ante >= ANTE_ECON_PENALTY_MIN and not (xmult or mult or chips):
        score -= JOKER_ECON_LATE_PENALTY
    score += _intent_adjust_for_joker(
        key, tokens=tokens, intent=intent, existing_jokers=existing_jokers
    )
    return score


def _score_pack(ante: int) -> int:
    if ante <= ANTE_EARLY_MAX:
        return PACK_SCORE_EARLY
    if ante <= ANTE_PACK_MID_MAX:
        return PACK_SCORE_MID
    if ante <= ANTE_MID_MAX:
        return PACK_SCORE_LATE
    return PACK_SCORE_NONE


def _score_pack_item(pack: Mapping[str, Any], *, ante: int, intent: str) -> int:
    base = _score_pack(ante)
    if base <= SCORE_NONE:
        return SCORE_NONE
    key = card_key(pack) or ""
    kind = _pack_type(key)
    rule = _PACK_TYPE_RULES.get(kind) or _PACK_TYPE_RULES["other"]
    bonus = rule.get("bonus", 0) if isinstance(rule, Mapping) else 0
    return base + (bonus if isinstance(bonus, int) else 0)


def _affordable(
    money: int, reserve: int, cost: int, *, score: int = SCORE_NONE
) -> bool:
    if cost == SCORE_NONE:
        return True
    if money - cost >= reserve:
        return True
    return score >= RESERVE_OVERRIDE_SCORE and (money - cost) >= 0


def _has_x_token(tokens: set[str]) -> bool:
    return has_x_token(tokens, slice_after_first_char=SLICE_AFTER_FIRST_CHAR)


def _joker_category_scores(cfg: Config) -> dict[str, int]:
    return {
        "xmult": int(cfg.joker_score_xmult),
        "mult": int(cfg.joker_score_mult),
        "chips": int(cfg.joker_score_chips),
        "econ": int(cfg.joker_score_econ),
        "default": int(cfg.joker_score_default),
    }


def _item_identity(item: Mapping[str, Any]) -> dict[str, str]:
    identity: dict[str, str] = {}
    key = card_key(item)
    if key:
        identity["key"] = key
    text = card_text(item)
    if text:
        identity["label"] = text
    return identity


def _find_item_index(
    gs: Mapping[str, Any], item_kind: str, identity: Mapping[str, Any]
) -> int | None:
    items: list[dict]
    if item_kind == "voucher":
        items = gs_shop_vouchers(gs)
    elif item_kind == "pack":
        items = gs_shop_packs(gs)
    else:
        items = gs_shop_cards(gs)
    key = identity.get("key")
    label = identity.get("label")
    for index, current in enumerate(items):
        if isinstance(key, str) and card_key(current) != key:
            continue
        if isinstance(label, str) and card_text(current) != label:
            continue
        return index
    return None


def _shop_memory(ctx: PolicyContext) -> dict[str, Any]:
    shop = ctx.round_memory.get("shop")
    if not isinstance(shop, dict):
        shop = {}
        ctx.round_memory["shop"] = shop
    return shop


def _intent(ctx: PolicyContext) -> str:
    intent = ctx.round_memory.get("intent")
    intent_text = _intent_to_text(intent)
    if intent_text:
        return intent_text
    intent = ctx.run_memory.get("intent")
    intent_text = _intent_to_text(intent)
    if intent_text:
        return intent_text
    return ""


def _intent_to_text(intent: Any) -> str:
    if isinstance(intent, str):
        return intent
    value = getattr(intent, "value", None)
    if isinstance(value, str):
        return value
    return ""


def _budget(
    cfg: Config, gs: Mapping[str, Any], intent: str, base_reserve: int
) -> _Budget:
    ante = gs_ante(gs)
    money = gs_money(gs)
    round_num = gs_round_num(gs)
    blind_score = gs_blind_score(gs) or 0

    if ante <= ANTE_EARLY_MAX:
        buy_threshold = cfg.buy_threshold_early
        reroll_threshold = cfg.reroll_threshold_early
        cost_weight = cfg.cost_weight_early
    elif ante <= ANTE_MID_MAX:
        buy_threshold = cfg.buy_threshold_mid
        reroll_threshold = cfg.reroll_threshold_mid
        cost_weight = cfg.cost_weight_mid
    else:
        buy_threshold = cfg.buy_threshold_late
        reroll_threshold = cfg.reroll_threshold_late
        cost_weight = cfg.cost_weight_late

    boss_soon = round_num % 3 == 2
    tough_blind = blind_score > 0 and blind_score >= 1_000 * max(1, ante)
    behind = tough_blind and money < base_reserve + 5
    ahead = money > base_reserve + 25

    reserve = base_reserve
    if boss_soon or behind:
        reserve = max(0, reserve - 6)
        buy_threshold = max(10, buy_threshold - 5)
        reroll_threshold = max(0, reroll_threshold - 5)
        cost_weight *= 0.85
    if ahead and not boss_soon:
        reserve += 5
        cost_weight *= 1.05

    if blind_score > 0 and blind_score >= 2_000 * max(1, ante):
        reserve = max(0, reserve - 4)
        buy_threshold = max(10, buy_threshold - 3)
        cost_weight *= 0.9

    if intent == _INTENT_HIGH_CARD and ante <= ANTE_EARLY_MAX:
        reserve += 2

    return _Budget(
        reserve=reserve,
        buy_threshold=buy_threshold,
        reroll_threshold=reroll_threshold,
        cost_weight=cost_weight,
    )


def _cost_adjust(score: int, *, cost: int, budget: _Budget, ante: int) -> int:
    if cost <= 0:
        return 0
    weight = budget.cost_weight
    if score >= RESERVE_OVERRIDE_SCORE:
        weight *= 0.4
    penalty = int(round(weight * float(cost)))
    if ante >= ANTE_ECON_PENALTY_MIN and score <= 20:
        penalty += 2
    return -penalty


def _score_shop_card(
    card: Mapping[str, Any],
    *,
    intent: str,
    ante: int,
    cost: int,
    budget: _Budget,
    gs: Mapping[str, Any],
    category_scores: Mapping[str, int],
) -> int:
    key = card_key(card) or ""
    jokers = gs_jokers(gs)
    if key.startswith("j_"):
        base = _score_joker(
            card,
            ante=ante,
            intent=intent,
            existing_jokers=jokers,
            category_scores=category_scores,
        )
    elif key.startswith("c_"):
        base = _score_consumable(card, intent=intent)
    else:
        base = _score_joker(
            card,
            ante=ante,
            intent=intent,
            existing_jokers=jokers,
            category_scores=category_scores,
        )
    base += _synergy_bonus_with_existing(card, intent=intent, existing_jokers=jokers)
    base += _cost_adjust(base, cost=cost, budget=budget, ante=ante)
    return base


def _score_consumable(card: Mapping[str, Any], *, intent: str) -> int:
    key = card_key(card) or ""

    rule = consumable_rule(key)
    if isinstance(rule, Mapping):
        return _score_by_intent(rule.get("score"), intent)

    text = _item_text(card)
    tokens = _tokens(text)
    score = 0
    if "$" in text or tokens & _ECON_TOKENS:
        score += 20
    if tokens & _SUIT_TOKENS and intent == _INTENT_FLUSH:
        score += 25
    if "straight" in tokens and intent == _INTENT_STRAIGHT:
        score += 25
    if {"pair", "pairs", "kind"} & tokens and intent == _INTENT_PAIRS:
        score += 20
    return score


def _intent_adjust_for_joker(
    key: str | None,
    *,
    tokens: set[str],
    intent: str,
    existing_jokers: list[dict],
) -> int:
    bonus = 0
    rule = joker_rule(key)
    if rule is not None:
        bonus += rule.flat_bonus
        bonus += rule.bonus_for_intent(intent)

    key_text = key or ""
    tags = _joker_tags(key_text, tokens)
    bonus += _joker_intent_tag_bonus(tags, intent)
    bonus += _synergy_bonus_with_existing(
        {"key": key_text, "label": ""}, intent=intent, existing_jokers=existing_jokers
    )
    return bonus


def _synergy_bonus_with_existing(
    item: Mapping[str, Any],
    *,
    intent: str,
    existing_jokers: list[dict],
) -> int:
    key = card_key(item) or ""
    if not key:
        return 0
    tokens = _tokens(_item_text(item))
    tags = _item_tags(key, tokens)

    existing_tags: set[str] = set()
    for joker in existing_jokers:
        joker_key = card_key(joker) or ""
        if not joker_key:
            continue
        joker_tokens = _tokens(_item_text(joker))
        existing_tags |= set(_joker_tags(joker_key, joker_tokens))
    score = 0

    if (
        intent == _INTENT_FLUSH
        and _TAG_SUIT_CONVERT in tags
        and _TAG_FLUSH_PAYOFF in existing_tags
    ):
        score += 50
    if (
        intent == _INTENT_FLUSH
        and _TAG_FLUSH_PAYOFF in tags
        and _TAG_SUIT_FOCUS in existing_tags
    ):
        score += 35
    if (
        intent == _INTENT_STRAIGHT
        and _TAG_STRAIGHT_SUPPORT_CONSUMABLE in tags
        and _TAG_STRAIGHT_PAYOFF in existing_tags
    ):
        score += 35
    if (
        intent == _INTENT_STRAIGHT
        and _TAG_STRAIGHT_SUPPORT_JOKER in tags
        and _TAG_STRAIGHT_PAYOFF in existing_tags
    ):
        score += 25
    if (
        intent == _INTENT_PAIRS
        and _TAG_PAIRS_SUPPORT_CONSUMABLE in tags
        and _TAG_PAIRS_PAYOFF in existing_tags
    ):
        score += 35

    return score


def _best_purchase_plan(
    candidates: list[_Candidate],
    *,
    money: int,
    reserve: int,
    intent: str,
    ante: int,
) -> tuple[list[_Candidate], int] | None:
    if not candidates:
        return None
    buyables = [c for c in candidates if c.kind in {"voucher", "card"}]
    if not buyables:
        return None

    buyables.sort(key=lambda c: c.score, reverse=True)
    buyables = buyables[:COMBO_SEARCH_WIDTH]

    best_single = buyables[0]
    best_plan: list[_Candidate] = [best_single]
    best_score = best_single.score

    for first in buyables:
        money_after_first = money - first.cost
        if money_after_first < reserve:
            continue
        best_second: _Candidate | None = None
        best_second_total = SCORE_NONE
        for second in buyables:
            if second is first:
                continue
            if money_after_first - second.cost < reserve:
                continue
            combined = (
                first.score
                + second.score
                + _pair_synergy(first, second, intent=intent, ante=ante)
            )
            if combined > best_second_total:
                best_second_total = combined
                best_second = second
        if best_second is None:
            continue
        if best_second_total > best_score:
            best_score = best_second_total
            best_plan = [first, best_second]

    return best_plan, best_score


def _pair_synergy(a: _Candidate, b: _Candidate, *, intent: str, ante: int) -> int:
    if a.kind != "card" or b.kind != "card":
        if a.kind == "voucher" and b.kind == "card":
            return _voucher_card_synergy(a, b, intent=intent)
        if b.kind == "voucher" and a.kind == "card":
            return _voucher_card_synergy(b, a, intent=intent)
        return 0

    a_key = a.identity.get("key", "")
    b_key = b.identity.get("key", "")
    if not a_key or not b_key:
        return 0

    a_tokens = _tokens(a.identity.get("label", ""))
    b_tokens = _tokens(b.identity.get("label", ""))
    a_tags = _item_tags(a_key, a_tokens)
    b_tags = _item_tags(b_key, b_tokens)

    if intent == _INTENT_FLUSH:
        if (_TAG_SUIT_CONVERT in a_tags and _TAG_FLUSH_PAYOFF in b_tags) or (
            _TAG_SUIT_CONVERT in b_tags and _TAG_FLUSH_PAYOFF in a_tags
        ):
            return 60
        if (_TAG_SMEARED in a_tags and _TAG_FLUSH_PAYOFF in b_tags) or (
            _TAG_SMEARED in b_tags and _TAG_FLUSH_PAYOFF in a_tags
        ):
            return 40
    if intent == _INTENT_STRAIGHT:
        if (
            _TAG_STRAIGHT_SUPPORT_CONSUMABLE in a_tags
            and _TAG_STRAIGHT_PAYOFF in b_tags
        ) or (
            _TAG_STRAIGHT_SUPPORT_CONSUMABLE in b_tags
            and _TAG_STRAIGHT_PAYOFF in a_tags
        ):
            return 40
        if (
            _TAG_STRAIGHT_SUPPORT_JOKER in a_tags or _TAG_STRAIGHT_PAYOFF in a_tags
        ) and (_TAG_STRAIGHT_SUPPORT_JOKER in b_tags or _TAG_STRAIGHT_PAYOFF in b_tags):
            return 25
    if intent == _INTENT_PAIRS:
        if (
            _TAG_PAIRS_SUPPORT_CONSUMABLE in a_tags and _TAG_PAIRS_PAYOFF in b_tags
        ) or (_TAG_PAIRS_SUPPORT_CONSUMABLE in b_tags and _TAG_PAIRS_PAYOFF in a_tags):
            return 40

    if ante >= ANTE_ECON_PENALTY_MIN:
        return 0
    return 0


def _voucher_card_synergy(voucher: _Candidate, card: _Candidate, *, intent: str) -> int:
    v_key = voucher.identity.get("key", "")
    c_key = card.identity.get("key", "")
    v_rule = voucher_rule(v_key) or {}
    v_tags = (
        v_rule.get("tags", frozenset()) if isinstance(v_rule, Mapping) else frozenset()
    )

    c_tokens = _tokens(card.identity.get("label", ""))
    c_tags = _item_tags(c_key, c_tokens)

    if _TAG_REROLL_VOUCHER in v_tags and _TAG_REROLL_ENGINE in c_tags:
        return 20
    if (
        _TAG_TAROT_SHOP in v_tags
        and intent == _INTENT_FLUSH
        and _TAG_SUIT_CONVERT in c_tags
    ):
        return 15
    return 0


def _set_pending_buys(shop_mem: dict[str, Any], candidates: list[_Candidate]) -> None:
    if not candidates:
        shop_mem.pop("pending_actions", None)
        return
    pending: list[dict[str, Any]] = []
    for cand in candidates:
        pending.append(
            {
                "kind": "buy",
                "item_kind": cand.kind,
                "identity": cand.identity,
            }
        )
    shop_mem["pending_actions"] = pending


def _should_reroll(
    cfg: Config,
    money: int,
    reserve: int,
    reroll_cost: int,
    shop_mem: Mapping[str, Any],
    best_score: int,
    budget: _Budget,
) -> bool:
    if not _can_reroll(cfg, money, reserve, reroll_cost, shop_mem):
        return False
    return best_score < budget.reroll_threshold
