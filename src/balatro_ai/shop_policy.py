from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from balatro_ai.actions import Action
from balatro_ai.cards import card_key, card_text, card_tokens
from balatro_ai.config import Config
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
_SUIT_TOKENS = {"suit", "spade", "spades", "heart", "hearts", "diamond", "diamonds", "club", "clubs"}

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

JOKER_SCORE_XMULT = 100
JOKER_SCORE_MULT = 50
JOKER_SCORE_CHIPS = 20
JOKER_SCORE_ECON = 0
JOKER_SCORE_DEFAULT = 0
JOKER_ECON_LATE_PENALTY = 20

PACK_SCORE_EARLY = 10
PACK_SCORE_MID = 6
PACK_SCORE_LATE = 3
PACK_SCORE_NONE = 0

COMBO_SEARCH_WIDTH = 8

BUY_THRESHOLD_EARLY = 30
BUY_THRESHOLD_MID = 35
BUY_THRESHOLD_LATE = 40

REROLL_THRESHOLD_EARLY = 20
REROLL_THRESHOLD_MID = 25
REROLL_THRESHOLD_LATE = 30

COST_WEIGHT_EARLY = 1.8
COST_WEIGHT_MID = 1.2
COST_WEIGHT_LATE = 0.9

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

_CONSUMABLE_SUIT_CONVERT = {"c_star", "c_moon", "c_sun", "c_world", "c_sigil"}
_CONSUMABLE_STRAIGHT_SUPPORT = {"c_strength"}
_CONSUMABLE_PAIRS_SUPPORT = {"c_death"}

_PLANET_FLUSH = {"c_jupiter", "c_ceres", "c_eris"}
_PLANET_STRAIGHT = {"c_saturn", "c_neptune"}
_PLANET_PAIRS = {"c_mercury", "c_venus", "c_uranus", "c_earth", "c_mars", "c_planet_x"}
_PLANET_HIGH_CARD = {"c_pluto"}

_JOKER_SUIT_FOCUS = {"j_smeared", "j_ancient", "j_seeing_double", "j_idol", "j_castle"}
_JOKER_FLUSH_PAYOFF = {"j_droll", "j_crafty", "j_tribe"}
_JOKER_STRAIGHT_PAYOFF = {"j_crazy", "j_devious", "j_runner", "j_order"}
_JOKER_STRAIGHT_SUPPORT = {"j_four_fingers", "j_shortcut"}
_JOKER_PAIRS_PAYOFF = {"j_jolly", "j_mad", "j_zany", "j_sly", "j_clever", "j_wily"}

_VOUCHER_HIGH = {
    "v_antimatter",
    "v_clearance_sale",
    "v_liquidation",
    "v_overstock_norm",
    "v_overstock_plus",
    "v_seed_money",
    "v_money_tree",
    "v_grabber",
    "v_nacho_tong",
    "v_wasteful",
    "v_recyclomancy",
    "v_paint_brush",
    "v_palette",
}
_VOUCHER_REROLL = {"v_reroll_surplus", "v_reroll_glut"}


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

    def choose_action(self, gs: Mapping[str, Any], cfg: Config, ctx: PolicyContext) -> Action:
        """Choose an action while in SHOP state."""
        if gs_state(gs) != "SHOP":
            raise ValueError(f"ShopPolicy used outside SHOP state: {gs_state(gs)}")
        shop_mem = _shop_memory(ctx)
        intent = _intent(ctx) or _INTENT_HIGH_CARD
        pending_actions = shop_mem.get("pending_actions")
        if isinstance(pending_actions, list) and pending_actions:
            action = _next_pending_action(pending_actions, gs, intent=intent)
            if action is not None:
                logger.debug("ShopPolicy: executing pending action=%s params=%s", action.kind, action.params)
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
        shop_candidates = _collect_shop_candidates(gs, ante, money, reserve, intent, budget)
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
                worst_index = _worst_joker_index(gs, ante, intent)
                if worst_index is not None:
                    return Action(kind="sell", params={"joker": worst_index})
            _set_pending_buys(shop_mem, plan[1:])
            return _buy_action(plan[0])

        best_shop = plan[0] if plan else None
        best_score = plan_score if best_shop else SCORE_NONE
        if _should_reroll(cfg, money, reserve, reroll_cost, shop_mem, best_score, budget):
            shop_mem["rerolls_used"] = shop_mem.get("rerolls_used", REROLL_USED_DEFAULT) + REROLL_USED_INCREMENT
            shop_mem.pop("pending_actions", None)
            logger.debug("ShopPolicy: reroll (rerolls_used=%s)", shop_mem["rerolls_used"])
            return Action(kind="reroll", params={})

        pack_candidates = _collect_pack_candidates(gs, ante, money, reserve)
        best_pack = _best_candidate(pack_candidates)
        if best_pack is not None and best_pack.score > SCORE_NONE:
            logger.debug("ShopPolicy: choosing pack candidate=%s", best_pack)
            return _buy_action(best_pack)

        logger.debug("ShopPolicy: next_round (no good buys)")
        return Action(kind="next_round", params={})


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
) -> list[_Candidate]:
    candidates: list[_Candidate] = []
    for index, voucher in enumerate(gs_shop_vouchers(gs)):
        cost = _item_cost(voucher)
        score = _score_voucher(voucher, intent=intent, ante=ante, cost=cost, budget=budget)
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
        score = _score_shop_card(card, intent=intent, ante=ante, cost=cost, budget=budget, gs=gs)
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
) -> list[_Candidate]:
    candidates: list[_Candidate] = []
    pack_score = _score_pack(ante)
    logger.debug("Shop pack base score: ante=%s pack_score=%s", ante, pack_score)
    if pack_score <= SCORE_NONE:
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
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(
                "Shop pack option: idx=%s cost=%s score=%s key=%s text=%r",
                index,
                cost,
                pack_score,
                card_key(pack),
                _item_text(pack),
            )
        candidates.append(
            _Candidate(
                kind="pack",
                index=index,
                score=pack_score,
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
        worst_index = _worst_joker_index(gs, gs_ante(gs), intent)
        if worst_index is not None:
            return Action(kind="sell", params={"joker": worst_index})
    pending_actions.pop(0)
    candidate = _Candidate(kind=item_kind, index=index, score=0, cost=0, identity=dict(identity))
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


def _worst_joker_index(gs: Mapping[str, Any], ante: int, intent: str) -> int | None:
    jokers = gs_jokers(gs)
    if not jokers:
        return None
    worst_index = INDEX_INITIAL
    worst_score = _score_joker(jokers[INDEX_INITIAL], ante=ante, intent=intent, existing_jokers=jokers)
    for index, joker in enumerate(jokers[ENUMERATE_START:], start=ENUMERATE_START):
        score = _score_joker(joker, ante=ante, intent=intent, existing_jokers=jokers)
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


def _score_voucher(
    voucher: Mapping[str, Any],
    *,
    intent: str,
    ante: int,
    cost: int,
    budget: _Budget,
) -> int:
    key = card_key(voucher) or ""
    text = _item_text(voucher)
    tokens = _tokens(text)
    score = SCORE_NONE

    if key in _VOUCHER_HIGH:
        score += 80
    if key in _VOUCHER_REROLL:
        score += 40
    if key == "v_blank":
        score -= 50
    if key in {"v_tarot_merchant", "v_tarot_tycoon"} and intent == _INTENT_FLUSH:
        score += 15
    if key in {"v_planet_merchant", "v_planet_tycoon"} and intent in {
        _INTENT_FLUSH,
        _INTENT_STRAIGHT,
        _INTENT_PAIRS,
    }:
        score += 10
    if key in {"v_wasteful", "v_recyclomancy"} and intent == _INTENT_STRAIGHT:
        score += 25

    high_hits = tokens & _VOUCHER_VERY_HIGH
    if high_hits:
        score += VOUCHER_SCORE_HIGH_BASE + VOUCHER_SCORE_HIGH_PER_HIT * len(high_hits)
    medium_hits = tokens & _VOUCHER_MEDIUM
    if medium_hits:
        score += VOUCHER_SCORE_MEDIUM_BASE + VOUCHER_SCORE_MEDIUM_PER_HIT * len(medium_hits)

    score += _cost_adjust(score, cost=cost, budget=budget, ante=ante)
    return score


def _score_joker(
    joker: Mapping[str, Any],
    *,
    ante: int,
    intent: str,
    existing_jokers: list[dict],
) -> int:
    key = card_key(joker)
    rule = joker_rule(key)
    tokens = _tokens(_item_text(joker))
    if rule is not None:
        score = _score_from_category(rule.category)
        if rule.category == "econ" and ante >= ANTE_ECON_PENALTY_MIN:
            text = _item_text(joker)
            tokens = _tokens(text)
            xmult = bool(tokens & _XMULT_TOKENS) or _has_x_token(tokens)
            mult = bool(tokens & _MULT_TOKENS)
            chips = bool(tokens & _CHIPS_TOKENS)
            if not (xmult or mult or chips):
                score -= JOKER_ECON_LATE_PENALTY
        score += _intent_adjust_for_joker(key, tokens=tokens, intent=intent, existing_jokers=existing_jokers)
        return score
    text = _item_text(joker)
    score = SCORE_NONE
    xmult = bool(tokens & _XMULT_TOKENS) or _has_x_token(tokens)
    mult = bool(tokens & _MULT_TOKENS)
    chips = bool(tokens & _CHIPS_TOKENS)
    econ = "$" in text or bool(tokens & _ECON_TOKENS)
    if xmult:
        score += JOKER_SCORE_XMULT
    if mult:
        score += JOKER_SCORE_MULT
    if chips:
        score += JOKER_SCORE_CHIPS
    if econ:
        score += 10
    if econ and ante >= ANTE_ECON_PENALTY_MIN and not (xmult or mult or chips):
        score -= JOKER_ECON_LATE_PENALTY
    score += _intent_adjust_for_joker(key, tokens=tokens, intent=intent, existing_jokers=existing_jokers)
    return score


def _score_pack(ante: int) -> int:
    if ante <= ANTE_EARLY_MAX:
        return PACK_SCORE_EARLY
    if ante <= ANTE_PACK_MID_MAX:
        return PACK_SCORE_MID
    if ante <= ANTE_MID_MAX:
        return PACK_SCORE_LATE
    return PACK_SCORE_NONE


def _affordable(money: int, reserve: int, cost: int, *, score: int = SCORE_NONE) -> bool:
    if cost == SCORE_NONE:
        return True
    if money - cost >= reserve:
        return True
    return score >= RESERVE_OVERRIDE_SCORE and (money - cost) >= 0


def _has_x_token(tokens: set[str]) -> bool:
    return has_x_token(tokens, slice_after_first_char=SLICE_AFTER_FIRST_CHAR)


def _score_from_category(category: str) -> int:
    if category == "xmult":
        return JOKER_SCORE_XMULT
    if category == "mult":
        return JOKER_SCORE_MULT
    if category == "chips":
        return JOKER_SCORE_CHIPS
    if category == "econ":
        return JOKER_SCORE_ECON
    return JOKER_SCORE_DEFAULT


def _item_identity(item: Mapping[str, Any]) -> dict[str, str]:
    identity: dict[str, str] = {}
    key = card_key(item)
    if key:
        identity["key"] = key
    text = card_text(item)
    if text:
        identity["label"] = text
    return identity


def _find_item_index(gs: Mapping[str, Any], item_kind: str, identity: Mapping[str, Any]) -> int | None:
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


def _budget(cfg: Config, gs: Mapping[str, Any], intent: str, base_reserve: int) -> _Budget:
    ante = gs_ante(gs)
    money = gs_money(gs)
    round_num = gs_round_num(gs)
    blind_score = gs_blind_score(gs) or 0

    if ante <= ANTE_EARLY_MAX:
        buy_threshold = BUY_THRESHOLD_EARLY
        reroll_threshold = REROLL_THRESHOLD_EARLY
        cost_weight = COST_WEIGHT_EARLY
    elif ante <= ANTE_MID_MAX:
        buy_threshold = BUY_THRESHOLD_MID
        reroll_threshold = REROLL_THRESHOLD_MID
        cost_weight = COST_WEIGHT_MID
    else:
        buy_threshold = BUY_THRESHOLD_LATE
        reroll_threshold = REROLL_THRESHOLD_LATE
        cost_weight = COST_WEIGHT_LATE

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
) -> int:
    key = card_key(card) or ""
    jokers = gs_jokers(gs)
    if key.startswith("j_"):
        base = _score_joker(card, ante=ante, intent=intent, existing_jokers=jokers)
    elif key.startswith("c_"):
        base = _score_consumable(card, intent=intent)
    else:
        base = _score_joker(card, ante=ante, intent=intent, existing_jokers=jokers)
    base += _synergy_bonus_with_existing(card, intent=intent, existing_jokers=jokers)
    base += _cost_adjust(base, cost=cost, budget=budget, ante=ante)
    return base


def _score_consumable(card: Mapping[str, Any], *, intent: str) -> int:
    key = card_key(card) or ""
    score = 0

    if key in _CONSUMABLE_SUIT_CONVERT:
        if intent == _INTENT_FLUSH:
            score += 90
        elif intent == _INTENT_STRAIGHT:
            score -= 10
        else:
            score += 15
    if key in _CONSUMABLE_STRAIGHT_SUPPORT:
        score += 80 if intent == _INTENT_STRAIGHT else 10
    if key in _CONSUMABLE_PAIRS_SUPPORT:
        score += 80 if intent == _INTENT_PAIRS else 15

    if key in _PLANET_FLUSH:
        score += 70 if intent == _INTENT_FLUSH else 10
    if key in _PLANET_STRAIGHT:
        score += 70 if intent == _INTENT_STRAIGHT else 10
    if key in _PLANET_PAIRS:
        score += 60 if intent == _INTENT_PAIRS else 5
    if key in _PLANET_HIGH_CARD:
        score += 40 if intent == _INTENT_HIGH_CARD else 10

    if key == "c_hermit":
        score += 35
    if key == "c_temperance":
        score += 25

    if score != 0:
        return score

    text = _item_text(card)
    tokens = _tokens(text)
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
    key_text = key or ""

    is_suit_focus = key_text in _JOKER_SUIT_FOCUS or bool(tokens & _SUIT_TOKENS)
    is_flush_payoff = key_text in _JOKER_FLUSH_PAYOFF or "flush" in tokens
    is_straight_payoff = key_text in _JOKER_STRAIGHT_PAYOFF or "straight" in tokens
    is_straight_support = key_text in _JOKER_STRAIGHT_SUPPORT
    is_pairs_payoff = key_text in _JOKER_PAIRS_PAYOFF or bool(tokens & {"pair", "pairs", "kind"})

    if intent == _INTENT_FLUSH:
        if is_flush_payoff:
            bonus += 60
        if is_suit_focus:
            bonus += 45
        if is_straight_payoff or is_straight_support:
            bonus -= 15
        if key_text == "j_smeared":
            bonus += 60
    elif intent == _INTENT_STRAIGHT:
        if is_straight_payoff:
            bonus += 60
        if is_straight_support:
            bonus += 45
        if is_suit_focus:
            bonus -= 45
        if key_text == "j_smeared":
            bonus -= 40
    elif intent == _INTENT_PAIRS:
        if is_pairs_payoff:
            bonus += 55
        if is_flush_payoff or is_straight_payoff:
            bonus -= 10
    else:
        if is_suit_focus or is_flush_payoff or is_straight_payoff:
            bonus -= 5

    if key_text == "j_chaos":
        bonus += 20
    if key_text == "j_flash":
        bonus += 10

    bonus += _synergy_bonus_with_existing({"key": key_text, "label": ""}, intent=intent, existing_jokers=existing_jokers)
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
    existing_keys = {card_key(joker) or "" for joker in existing_jokers}
    score = 0

    if intent == _INTENT_FLUSH and key in _CONSUMABLE_SUIT_CONVERT and existing_keys & _JOKER_FLUSH_PAYOFF:
        score += 50
    if intent == _INTENT_FLUSH and key in _JOKER_FLUSH_PAYOFF and existing_keys & _JOKER_SUIT_FOCUS:
        score += 35
    if intent == _INTENT_STRAIGHT and key in _CONSUMABLE_STRAIGHT_SUPPORT and existing_keys & _JOKER_STRAIGHT_PAYOFF:
        score += 35
    if intent == _INTENT_STRAIGHT and key in _JOKER_STRAIGHT_SUPPORT and existing_keys & _JOKER_STRAIGHT_PAYOFF:
        score += 25
    if intent == _INTENT_PAIRS and key in _CONSUMABLE_PAIRS_SUPPORT and existing_keys & _JOKER_PAIRS_PAYOFF:
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
            combined = first.score + second.score + _pair_synergy(first, second, intent=intent, ante=ante)
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

    if intent == _INTENT_FLUSH:
        if {a_key, b_key} & _CONSUMABLE_SUIT_CONVERT and {a_key, b_key} & _JOKER_FLUSH_PAYOFF:
            return 60
        if "j_smeared" in {a_key, b_key} and {a_key, b_key} & _JOKER_FLUSH_PAYOFF:
            return 40
    if intent == _INTENT_STRAIGHT:
        if {a_key, b_key} & _CONSUMABLE_STRAIGHT_SUPPORT and {a_key, b_key} & _JOKER_STRAIGHT_PAYOFF:
            return 40
        if {a_key, b_key} <= (_JOKER_STRAIGHT_SUPPORT | _JOKER_STRAIGHT_PAYOFF):
            return 25
    if intent == _INTENT_PAIRS:
        if {a_key, b_key} & _CONSUMABLE_PAIRS_SUPPORT and {a_key, b_key} & _JOKER_PAIRS_PAYOFF:
            return 40

    if ante >= ANTE_ECON_PENALTY_MIN:
        return 0
    return 0


def _voucher_card_synergy(voucher: _Candidate, card: _Candidate, *, intent: str) -> int:
    v_key = voucher.identity.get("key", "")
    c_key = card.identity.get("key", "")
    if v_key in _VOUCHER_REROLL and c_key in {"j_flash", "j_chaos"}:
        return 20
    if (
        v_key in {"v_tarot_merchant", "v_tarot_tycoon"}
        and intent == _INTENT_FLUSH
        and c_key in _CONSUMABLE_SUIT_CONVERT
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
