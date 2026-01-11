from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from dataclasses import dataclass
from itertools import combinations
from typing import TYPE_CHECKING, Any

from balatro_ai.actions import Action
from balatro_ai.cards import card_key, card_text, card_tokens
from balatro_ai.gs import gs_hand_cards, gs_jokers, gs_state, safe_get
from balatro_ai.joker_rules import joker_rule
from balatro_ai.poker_eval import classify_hand
from balatro_ai.token_utils import has_x_token

if TYPE_CHECKING:
    from balatro_ai.policy import PolicyContext

logger = logging.getLogger(__name__)


_MAX_JOKER_ORDER_SEARCH_LEN = 8


_ECON_TOKENS = {"money", "interest", "discount", "coupon", "sell", "shop"}
_CHIPS_TOKENS = {"chips", "chip", "bonus"}
_MULT_TOKENS = {"mult", "multiplier", "mults"}
_XMULT_TOKENS = {"xmult", "times", "retrigger", "again"}

_CHIPS_RE = re.compile(r"([+-])\s*(\d+)\s*chips", re.IGNORECASE)
_MULT_ADD_RE = re.compile(r"([+-])\s*(\d+)\s*mult", re.IGNORECASE)
_MULT_MUL_RE = re.compile(r"[xX×]\s*(\d+(?:\.\d+)?)\s*mult", re.IGNORECASE)


def joker_text(joker: dict) -> str:
    """Return lowercase text for a joker, preferring label then key."""
    if not isinstance(joker, Mapping):
        return ""
    return card_text(joker)


@dataclass(frozen=True)
class JokerEffect:
    chips_add: int = 0
    mult_add: int = 0
    mult_mul: float = 1.0

    @property
    def signature(self) -> tuple[int, int, float]:
        return (self.chips_add, self.mult_add, round(self.mult_mul, 6))


def classify_joker_bucket(text: str, key: str | None = None) -> int:
    """Return the bucket index for the provided joker text."""
    rule = joker_rule(key)
    if rule is not None:
        return _category_bucket(rule.category)
    if not text:
        return 2
    lowered = text.lower()
    tokens = card_tokens(lowered)
    if "$" in lowered or tokens & _ECON_TOKENS:
        return 0
    if tokens & _CHIPS_TOKENS:
        return 1
    if tokens & _XMULT_TOKENS or _has_x_token(tokens):
        return 3
    if tokens & _MULT_TOKENS:
        return 2
    return 2


def compute_joker_permutation(jokers: list[dict]) -> list[int]:
    """Compute a stable permutation ordering jokers by bucket."""
    indexed = list(enumerate(jokers))
    ordered = sorted(
        indexed,
        key=lambda item: classify_joker_bucket(joker_text(item[1]), card_key(item[1])),
    )
    return [index for index, _ in ordered]


def find_best_joker_sequence(
    hand: list[dict],
    available_jokers: list[dict],
    *,
    hands_info: Mapping[str, Any] | None = None,
) -> list[int]:
    """Brute-force the best estimated joker application order for this hand.

    Returns a permutation of indices into `available_jokers`.
    """
    joker_count = len(available_jokers)
    if joker_count < 2:
        return list(range(joker_count))

    if joker_count > _MAX_JOKER_ORDER_SEARCH_LEN:
        logger.debug(
            "find_best_joker_sequence: jokers=%s exceeds max=%s -> fallback buckets",
            joker_count,
            _MAX_JOKER_ORDER_SEARCH_LEN,
        )
        return compute_joker_permutation(available_jokers)

    best_hand = _best_play_subset(hand, hands_info)
    base_chips, base_mult = _base_hand_score(best_hand, hands_info)

    effects = [_extract_joker_effect(joker) for joker in available_jokers]
    if all(effect.signature == (0, 0, 1.0) for effect in effects):
        return list(range(joker_count))

    best_order = list(range(joker_count))
    best_score = _simulate_order(best_order, effects, base_chips, base_mult)

    seen_orders = {tuple(best_order)}
    orders_evaluated = 1

    for prefix in _unique_prefix_orders(effects, max_len=joker_count):
        prefix_set = set(prefix)
        remaining = [idx for idx in range(joker_count) if idx not in prefix_set]
        order = prefix + remaining
        order_key = tuple(order)
        if order_key in seen_orders:
            continue
        seen_orders.add(order_key)
        orders_evaluated += 1

        score = _simulate_order(order, effects, base_chips, base_mult)
        if score > best_score:
            best_order = order
            best_score = score
        elif score == best_score and order_key < tuple(best_order):
            best_order = order

    logger.debug(
        "find_best_joker_sequence: hand=%s jokers=%s orders=%s base=(%s,%s) best_score=%.3f best_order=%s",
        len(best_hand),
        joker_count,
        orders_evaluated,
        base_chips,
        base_mult,
        best_score,
        best_order,
    )
    return best_order


def maybe_reorder_jokers(gs: Mapping[str, Any], ctx: PolicyContext) -> Action | None:
    """Return a rearrange action when jokers should be reordered."""
    state = gs_state(gs)
    if state not in {"SHOP", "SELECTING_HAND", "SMODS_BOOSTER_OPENED"}:
        logger.debug("maybe_reorder_jokers: state=%s not eligible", state)
        return None
    jokers = gs_jokers(gs)
    if len(jokers) < 2:
        logger.debug("maybe_reorder_jokers: state=%s jokers=%s (no reorder needed)", state, len(jokers))
        return None

    if state == "SELECTING_HAND":
        hand_cards = gs_hand_cards(gs)
        hands_info = safe_get(gs, ["hands"], None)
        permutation = find_best_joker_sequence(hand_cards, jokers, hands_info=hands_info)
    else:
        permutation = compute_joker_permutation(jokers)

    if permutation == list(range(len(jokers))):
        logger.debug("maybe_reorder_jokers: already ordered (perm=%s)", permutation)
        return None
    perm_hash = tuple(permutation)
    if ctx.memory.get("last_joker_perm_hash") == perm_hash:
        logger.debug("maybe_reorder_jokers: repeated perm hash (perm=%s) -> skip", permutation)
        return None
    if logger.isEnabledFor(logging.DEBUG):
        buckets = [classify_joker_bucket(joker_text(j), card_key(j)) for j in jokers]
        logger.debug(
            "maybe_reorder_jokers: state=%s buckets=%s perm=%s",
            state,
            buckets,
            permutation,
        )
    ctx.memory["last_joker_perm_hash"] = perm_hash
    return Action(kind="rearrange", params={"jokers": permutation})


def _has_x_token(tokens: set[str]) -> bool:
    return has_x_token(tokens, slice_after_first_char=1)


def _category_bucket(category: str) -> int:
    if category == "econ":
        return 0
    if category == "chips":
        return 1
    if category == "mult":
        return 2
    if category == "xmult":
        return 3
    return 2


def _extract_joker_effect(joker: Mapping[str, Any]) -> JokerEffect:
    effect_text = _joker_effect_text(joker)
    if not effect_text:
        return JokerEffect()

    chips_add = 0
    for match in _CHIPS_RE.finditer(effect_text):
        sign, value = match.groups()
        delta = int(value)
        chips_add += delta if sign == "+" else -delta

    mult_add = 0
    for match in _MULT_ADD_RE.finditer(effect_text):
        sign, value = match.groups()
        delta = int(value)
        mult_add += delta if sign == "+" else -delta

    mult_mul = 1.0
    for match in _MULT_MUL_RE.finditer(effect_text):
        mult_mul *= float(match.group(1))

    return JokerEffect(chips_add=chips_add, mult_add=mult_add, mult_mul=mult_mul)


def _joker_effect_text(joker: Mapping[str, Any]) -> str:
    value = joker.get("value")
    if isinstance(value, Mapping):
        effect = value.get("effect")
        if isinstance(effect, str) and effect:
            return effect
    label = joker.get("label")
    if isinstance(label, str) and label:
        return label
    key = joker.get("key")
    if isinstance(key, str) and key:
        return key
    return ""


def _simulate_order(order: list[int], effects: list[JokerEffect], base_chips: int, base_mult: int) -> float:
    chips = float(base_chips)
    mult = float(base_mult)
    for index in order:
        effect = effects[index]
        chips += effect.chips_add
        mult += effect.mult_add
        mult *= effect.mult_mul
    return chips * mult


def _unique_prefix_orders(effects: list[JokerEffect], *, max_len: int) -> list[list[int]]:
    groups: dict[tuple[int, int, float], list[int]] = {}
    for index, effect in enumerate(effects):
        groups.setdefault(effect.signature, []).append(index)
    for indices in groups.values():
        indices.sort()

    group_keys = sorted(groups.keys())
    group_indices = [groups[key] for key in group_keys]
    used_counts = [0 for _ in group_indices]

    results: list[list[int]] = []
    prefix: list[int] = []

    def backtrack() -> None:
        if prefix:
            results.append(prefix.copy())
        if len(prefix) >= max_len:
            return
        for group_id, indices in enumerate(group_indices):
            used = used_counts[group_id]
            if used >= len(indices):
                continue
            used_counts[group_id] = used + 1
            prefix.append(indices[used])
            backtrack()
            prefix.pop()
            used_counts[group_id] = used

    backtrack()
    results.sort()
    return results


def _best_play_subset(hand_cards: list[dict], hands_info: Mapping[str, Any] | None) -> list[dict]:
    if not hand_cards:
        return []

    best_subset = [hand_cards[0]]
    best_score = -1.0
    max_size = min(5, len(hand_cards))
    for size in range(1, max_size + 1):
        for combo in combinations(hand_cards, size):
            chips, mult = _base_hand_score(list(combo), hands_info)
            score = chips * mult
            if score > best_score:
                best_score = score
                best_subset = list(combo)
    return best_subset


def _base_hand_score(hand_cards: list[dict], hands_info: Mapping[str, Any] | None) -> tuple[int, int]:
    if not hand_cards:
        return (1, 1)
    if not isinstance(hands_info, Mapping) or not hands_info:
        return (1, 1)

    hand_type = classify_hand(hand_cards).value
    desired = _normalize_hand_name(_HAND_TYPE_NAME.get(hand_type, hand_type))

    best_match: Mapping[str, Any] | None = None
    for name, info in hands_info.items():
        if not isinstance(name, str) or not isinstance(info, Mapping):
            continue
        if _normalize_hand_name(name) == desired:
            best_match = info
            break

    chips = best_match.get("chips") if best_match is not None else None
    mult = best_match.get("mult") if best_match is not None else None
    parsed_chips = chips if isinstance(chips, int) and not isinstance(chips, bool) else 1
    parsed_mult = mult if isinstance(mult, int) and not isinstance(mult, bool) else 1
    return (max(1, parsed_chips), max(1, parsed_mult))


def _normalize_hand_name(text: str) -> str:
    return "".join(char for char in text.lower() if char.isalnum())


_HAND_TYPE_NAME: dict[str, str] = {
    "HIGH_CARD": "High Card",
    "PAIR": "Pair",
    "TWO_PAIR": "Two Pair",
    "THREE_KIND": "Three of a Kind",
    "STRAIGHT": "Straight",
    "FLUSH": "Flush",
    "FULL_HOUSE": "Full House",
    "FOUR_KIND": "Four of a Kind",
    "STRAIGHT_FLUSH": "Straight Flush",
    "FIVE_KIND": "Five of a Kind",
    "FLUSH_HOUSE": "Flush House",
    "FLUSH_FIVE": "Flush Five",
}

