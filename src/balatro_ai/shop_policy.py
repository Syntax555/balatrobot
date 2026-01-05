from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping, TYPE_CHECKING

from balatro_ai.actions import Action
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

if TYPE_CHECKING:
    from balatro_ai.policy import PolicyContext


_TOKEN_RE = re.compile(r"[a-z0-9]+")
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
        pending = shop_mem.pop("pending_buy", None)
        if pending:
            action = _pending_action(pending)
            if action is not None:
                return action
        money = gs_money(gs)
        ante = gs_ante(gs)
        reserve = _reserve(cfg, ante)
        reroll_cost = gs_reroll_cost(gs)
        candidates = _collect_shop_candidates(gs, ante, money, reserve)
        best = _best_candidate(candidates)
        if best is None or best.score <= 0:
            pack_candidates = _collect_pack_candidates(gs, ante, money, reserve)
            best_pack = _best_candidate(pack_candidates)
            if best_pack is not None and best_pack.score > 0:
                best = best_pack
            else:
                if _can_reroll(cfg, money, reserve, reroll_cost, shop_mem):
                    shop_mem["rerolls_used"] = shop_mem.get("rerolls_used", 0) + 1
                    return Action(kind="reroll", params={})
                return Action(kind="next_round", params={})
        if best.kind == "card" and _jokers_full(gs):
            worst_index = _worst_joker_index(gs, ante)
            if worst_index is not None:
                shop_mem["pending_buy"] = {"kind": "buy", "item_kind": "card", "index": best.index}
                return Action(kind="sell", params={"joker": worst_index})
        return _buy_action(best)


def _reserve(cfg: Config, ante: int) -> int:
    if ante <= 2:
        return cfg.reserve_early
    if ante <= 5:
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
    if pack_score <= 0:
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
    used = shop_mem.get("rerolls_used", 0)
    if not isinstance(used, int):
        used = 0
    return used < cfg.max_rerolls_per_shop


def _buy_action(candidate: _Candidate) -> Action:
    if candidate.kind == "voucher":
        return Action(kind="buy", params={"voucher": candidate.index})
    if candidate.kind == "pack":
        return Action(kind="buy", params={"pack": candidate.index})
    return Action(kind="buy", params={"card": candidate.index})


def _pending_action(pending: Mapping[str, Any]) -> Action | None:
    kind = pending.get("kind")
    item_kind = pending.get("item_kind")
    index = pending.get("index")
    if kind != "buy" or not isinstance(index, int):
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
    worst_index = 0
    worst_score = _score_joker(jokers[0], ante)
    for index, joker in enumerate(jokers[1:], start=1):
        score = _score_joker(joker, ante)
        if score < worst_score:
            worst_score = score
            worst_index = index
    return worst_index


def _item_text(item: Mapping[str, Any]) -> str:
    label = item.get("label")
    if isinstance(label, str) and label:
        return label.lower()
    key = item.get("key")
    if isinstance(key, str) and key:
        return key.lower()
    return ""


def _item_cost(item: Mapping[str, Any]) -> int:
    for key in ("cost", "price", "amount"):
        value = item.get(key)
        if isinstance(value, int) and not isinstance(value, bool):
            return value
        if isinstance(value, Mapping):
            buy = value.get("buy")
            if isinstance(buy, int) and not isinstance(buy, bool):
                return buy
    return 0


def _tokens(text: str) -> set[str]:
    if not text:
        return set()
    return set(_TOKEN_RE.findall(text.lower()))


def _score_voucher(voucher: Mapping[str, Any]) -> int:
    text = _item_text(voucher)
    tokens = _tokens(text)
    score = 0
    high_hits = tokens & _VOUCHER_VERY_HIGH
    if high_hits:
        score += 60 + 5 * len(high_hits)
    medium_hits = tokens & _VOUCHER_MEDIUM
    if medium_hits:
        score += 30 + 3 * len(medium_hits)
    return score


def _score_joker(joker: Mapping[str, Any], ante: int) -> int:
    text = _item_text(joker)
    tokens = _tokens(text)
    score = 0
    xmult = bool(tokens & _XMULT_TOKENS) or _has_x_token(tokens)
    mult = bool(tokens & _MULT_TOKENS)
    chips = bool(tokens & _CHIPS_TOKENS)
    econ = "$" in text or bool(tokens & _ECON_TOKENS)
    if xmult:
        score += 100
    if mult:
        score += 50
    if chips:
        score += 20
    if econ and ante >= 6 and not (xmult or mult or chips):
        score -= 20
    return score


def _score_pack(ante: int) -> int:
    if ante <= 2:
        return 10
    if ante <= 4:
        return 6
    if ante <= 5:
        return 3
    return 0


def _affordable(money: int, reserve: int, cost: int) -> bool:
    if cost == 0:
        return True
    return money - cost >= reserve


def _has_x_token(tokens: set[str]) -> bool:
    if "x" in tokens:
        return True
    for token in tokens:
        if token.startswith("x") and token[1:].isdigit():
            return True
    return False


def _shop_memory(ctx: "PolicyContext") -> dict[str, Any]:
    shop = ctx.round_memory.get("shop")
    if not isinstance(shop, dict):
        shop = {}
        ctx.round_memory["shop"] = shop
    return shop
