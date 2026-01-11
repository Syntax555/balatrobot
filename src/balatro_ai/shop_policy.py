from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, TYPE_CHECKING

from balatro_ai.actions import Action
from balatro_ai.cards import card_key, card_text, card_tokens
from balatro_ai.config import Config
from balatro_ai.gs import (
    gs_ante,
    gs_jokers,
    gs_money,
    gs_reroll_cost,
    gs_shop_cards,
    gs_shop_packs,
    gs_shop_vouchers,
    gs_state,
    safe_get,
)
from balatro_ai.joker_rules import joker_rule

if TYPE_CHECKING:
    from balatro_ai.policy import PolicyContext


_ECON_TOKENS = {"money", "interest", "discount", "coupon", "sell", "shop"}
_CHIPS_TOKENS = {"chips", "chip", "bonus"}
_MULT_TOKENS = {"mult", "multiplier", "if", "when", "each"}
_XMULT_TOKENS = {"xmult", "times"}

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

INDEX_INITIAL = 0
ENUMERATE_START = 1
REROLL_USED_DEFAULT = 0
REROLL_USED_INCREMENT = 1

INDEX_MIN = 0
SLICE_AFTER_FIRST_CHAR = 1


@dataclass(frozen=True)
class _Candidate:
    kind: str
    index: int
    score: int
    cost: int


class ShopPolicy:
    """Shop decision policy for choosing a single action."""

    def choose_action(self, gs: Mapping[str, Any], cfg: Config, ctx: "PolicyContext") -> Action:
        """Choose an action while in SHOP state."""
        if gs_state(gs) != "SHOP":
            raise ValueError(f"ShopPolicy used outside SHOP state: {gs_state(gs)}")
        shop_mem = _shop_memory(ctx)
        pending = shop_mem.get("pending_buy")
        if pending:
            action = _pending_action(pending, gs)
            if action is not None:
                shop_mem.pop("pending_buy", None)
                return action
            shop_mem.pop("pending_buy", None)
        money = gs_money(gs)
        ante = gs_ante(gs)
        reserve = _reserve(cfg, ante)
        reroll_cost = gs_reroll_cost(gs)
        candidates = _collect_shop_candidates(gs, ante, money, reserve)
        best = _best_candidate(candidates)
        if best is None or best.score <= SCORE_NONE:
            pack_candidates = _collect_pack_candidates(gs, ante, money, reserve)
            best_pack = _best_candidate(pack_candidates)
            if best_pack is not None and best_pack.score > SCORE_NONE:
                best = best_pack
            else:
                if _can_reroll(cfg, money, reserve, reroll_cost, shop_mem):
                    shop_mem["rerolls_used"] = (
                        shop_mem.get("rerolls_used", REROLL_USED_DEFAULT) + REROLL_USED_INCREMENT
                    )
                    return Action(kind="reroll", params={})
                return Action(kind="next_round", params={})
        if best.kind == "card" and _jokers_full(gs):
            worst_index = _worst_joker_index(gs, ante)
            if worst_index is not None:
                identity = _item_identity(gs_shop_cards(gs)[best.index])
                shop_mem["pending_buy"] = {
                    "kind": "buy",
                    "item_kind": "card",
                    "index": best.index,
                    "identity": identity,
                }
                return Action(kind="sell", params={"joker": worst_index})
        return _buy_action(best)


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
) -> list[_Candidate]:
    candidates: list[_Candidate] = []
    for index, voucher in enumerate(gs_shop_vouchers(gs)):
        cost = _item_cost(voucher)
        if not _affordable(money, reserve, cost):
            continue
        score = _score_voucher(voucher)
        candidates.append(_Candidate(kind="voucher", index=index, score=score, cost=cost))
    for index, card in enumerate(gs_shop_cards(gs)):
        cost = _item_cost(card)
        if not _affordable(money, reserve, cost):
            continue
        score = _score_joker(card, ante)
        candidates.append(_Candidate(kind="card", index=index, score=score, cost=cost))
    return candidates


def _collect_pack_candidates(
    gs: Mapping[str, Any],
    ante: int,
    money: int,
    reserve: int,
) -> list[_Candidate]:
    candidates: list[_Candidate] = []
    pack_score = _score_pack(ante)
    if pack_score <= SCORE_NONE:
        return candidates
    for index, pack in enumerate(gs_shop_packs(gs)):
        cost = _item_cost(pack)
        if not _affordable(money, reserve, cost):
            continue
        candidates.append(_Candidate(kind="pack", index=index, score=pack_score, cost=cost))
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


def _pending_action(pending: Mapping[str, Any], gs: Mapping[str, Any]) -> Action | None:
    kind = pending.get("kind")
    item_kind = pending.get("item_kind")
    index = pending.get("index")
    identity = pending.get("identity")
    if kind != "buy" or not isinstance(index, int):
        return None
    if identity is not None and not _identity_matches(gs, item_kind, index, identity):
        return None
    if item_kind == "voucher":
        return Action(kind="buy", params={"voucher": index})
    if item_kind == "pack":
        return Action(kind="buy", params={"pack": index})
    return Action(kind="buy", params={"card": index})


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


def _worst_joker_index(gs: Mapping[str, Any], ante: int) -> int | None:
    jokers = gs_jokers(gs)
    if not jokers:
        return None
    worst_index = INDEX_INITIAL
    worst_score = _score_joker(jokers[INDEX_INITIAL], ante)
    for index, joker in enumerate(jokers[ENUMERATE_START:], start=ENUMERATE_START):
        score = _score_joker(joker, ante)
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


def _score_voucher(voucher: Mapping[str, Any]) -> int:
    text = _item_text(voucher)
    tokens = _tokens(text)
    score = SCORE_NONE
    high_hits = tokens & _VOUCHER_VERY_HIGH
    if high_hits:
        score += VOUCHER_SCORE_HIGH_BASE + VOUCHER_SCORE_HIGH_PER_HIT * len(high_hits)
    medium_hits = tokens & _VOUCHER_MEDIUM
    if medium_hits:
        score += VOUCHER_SCORE_MEDIUM_BASE + VOUCHER_SCORE_MEDIUM_PER_HIT * len(medium_hits)
    return score


def _score_joker(joker: Mapping[str, Any], ante: int) -> int:
    key = card_key(joker)
    rule = joker_rule(key)
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
        return score
    text = _item_text(joker)
    tokens = _tokens(text)
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
    if econ and ante >= ANTE_ECON_PENALTY_MIN and not (xmult or mult or chips):
        score -= JOKER_ECON_LATE_PENALTY
    return score


def _score_pack(ante: int) -> int:
    if ante <= ANTE_EARLY_MAX:
        return PACK_SCORE_EARLY
    if ante <= ANTE_PACK_MID_MAX:
        return PACK_SCORE_MID
    if ante <= ANTE_MID_MAX:
        return PACK_SCORE_LATE
    return PACK_SCORE_NONE


def _affordable(money: int, reserve: int, cost: int) -> bool:
    if cost == SCORE_NONE:
        return True
    return money - cost >= reserve


def _has_x_token(tokens: set[str]) -> bool:
    if "x" in tokens:
        return True
    for token in tokens:
        if token.startswith("x") and token[SLICE_AFTER_FIRST_CHAR:].isdigit():
            return True
    return False


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


def _identity_matches(
    gs: Mapping[str, Any],
    item_kind: str,
    index: int,
    identity: Mapping[str, Any],
) -> bool:
    items: list[dict]
    if item_kind == "voucher":
        items = gs_shop_vouchers(gs)
    elif item_kind == "pack":
        items = gs_shop_packs(gs)
    else:
        items = gs_shop_cards(gs)
    if index < INDEX_MIN or index >= len(items):
        return False
    current = items[index]
    key = identity.get("key")
    if isinstance(key, str) and card_key(current) != key:
        return False
    label = identity.get("label")
    if isinstance(label, str) and card_text(current) != label:
        return False
    return True


def _shop_memory(ctx: "PolicyContext") -> dict[str, Any]:
    shop = ctx.round_memory.get("shop")
    if not isinstance(shop, dict):
        shop = {}
        ctx.round_memory["shop"] = shop
    return shop
