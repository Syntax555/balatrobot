from __future__ import annotations

import enum
import re
from typing import Any, Mapping

from balatro_ai.gs import gs_hand_cards, gs_jokers
from balatro_ai.joker_order import joker_text


class BuildIntent(str, enum.Enum):
    """Build intent for the run."""

    FLUSH = "FLUSH"
    STRAIGHT = "STRAIGHT"
    PAIRS = "PAIRS"
    HIGH_CARD = "HIGH_CARD"


_TOKEN_RE = re.compile(r"[a-z0-9]+")
_SUIT_TOKENS = {
    "spades": "spades",
    "spade": "spades",
    "hearts": "hearts",
    "heart": "hearts",
    "diamonds": "diamonds",
    "diamond": "diamonds",
    "clubs": "clubs",
    "club": "clubs",
}
_RANK_MAP = {
    "a": 14,
    "k": 13,
    "q": 12,
    "j": 11,
    "t": 10,
    "10": 10,
    "9": 9,
    "8": 8,
    "7": 7,
    "6": 6,
    "5": 5,
    "4": 4,
    "3": 3,
    "2": 2,
}


def infer_intent(gs: Mapping[str, Any]) -> tuple[BuildIntent, float]:
    """Infer a build intent and confidence from the game state."""
    joker_intent = _intent_from_jokers(gs)
    hand_intent, hand_conf = _intent_from_hand(gs)
    if joker_intent is not None:
        if hand_conf >= 0.95 and hand_conf > joker_intent[1]:
            return hand_intent, hand_conf
        return joker_intent
    if hand_conf > 0:
        return hand_intent, hand_conf
    return BuildIntent.HIGH_CARD, 0.0


def _intent_from_jokers(gs: Mapping[str, Any]) -> tuple[BuildIntent, float] | None:
    for joker in gs_jokers(gs):
        text = joker_text(joker)
        if "flush" in text:
            return BuildIntent.FLUSH, 0.9
        if "straight" in text:
            return BuildIntent.STRAIGHT, 0.9
        if "two pair" in text or "pair" in text or "kind" in text:
            return BuildIntent.PAIRS, 0.9
    return None


def _intent_from_hand(gs: Mapping[str, Any]) -> tuple[BuildIntent, float]:
    hand = gs_hand_cards(gs)
    if not hand:
        return BuildIntent.HIGH_CARD, 0.0
    flush_conf = _flush_conf(hand)
    straight_conf = _straight_conf(hand)
    pairs_conf = _pairs_conf(hand)
    intents = [
        (BuildIntent.FLUSH, flush_conf),
        (BuildIntent.STRAIGHT, straight_conf),
        (BuildIntent.PAIRS, pairs_conf),
    ]
    best = max(intents, key=lambda item: (item[1], _intent_priority(item[0])))
    if best[1] <= 0:
        return BuildIntent.HIGH_CARD, 0.0
    return best


def _flush_conf(hand: list[dict]) -> float:
    counts: dict[str, int] = {}
    for card in hand:
        suit = _card_suit(card)
        if not suit:
            continue
        counts[suit] = counts.get(suit, 0) + 1
    if not counts:
        return 0.0
    max_count = max(counts.values())
    if max_count >= 4:
        return max_count / 5.0
    return 0.0


def _pairs_conf(hand: list[dict]) -> float:
    ranks = [_rank_value(card) for card in hand]
    counts: dict[int, int] = {}
    for rank in ranks:
        if rank <= 0:
            continue
        counts[rank] = counts.get(rank, 0) + 1
    if not counts:
        return 0.0
    max_dup = max(counts.values())
    if max_dup >= 2:
        return min(1.0, max_dup / 4.0)
    return 0.0


def _straight_conf(hand: list[dict]) -> float:
    ranks = {_rank_value(card) for card in hand}
    ranks.discard(0)
    if not ranks:
        return 0.0
    if 14 in ranks:
        ranks.add(1)
    unique = sorted(ranks)
    max_count = 0
    for start in unique:
        end = start + 4
        count = sum(1 for rank in unique if start <= rank <= end)
        if count > max_count:
            max_count = count
    if max_count >= 3:
        return max_count / 5.0
    return 0.0


def _card_suit(card: Mapping[str, Any]) -> str | None:
    for key in ("suit", "suit_name", "suit_key"):
        value = card.get(key)
        if isinstance(value, str) and value:
            return _SUIT_TOKENS.get(value.lower(), value.lower())
    label = card.get("label")
    if isinstance(label, str):
        tokens = _TOKEN_RE.findall(label.lower())
        for token in tokens:
            if token in _SUIT_TOKENS:
                return _SUIT_TOKENS[token]
    return None


def _rank_value(card: Mapping[str, Any]) -> int:
    for key in ("rank", "value", "rank_value"):
        value = card.get(key)
        if isinstance(value, int) and not isinstance(value, bool):
            return value
        if isinstance(value, str):
            mapped = _RANK_MAP.get(value.lower())
            if mapped is not None:
                return mapped
    label = card.get("label")
    if isinstance(label, str):
        return _rank_from_text(label)
    return 0


def _rank_from_text(text: str) -> int:
    lowered = text.lower()
    if "10" in lowered:
        return 10
    tokens = _TOKEN_RE.findall(lowered)
    for token in tokens:
        if token in _RANK_MAP:
            return _RANK_MAP[token]
    for char in lowered:
        if char in _RANK_MAP:
            return _RANK_MAP[char]
    return 0


def _intent_priority(intent: BuildIntent) -> int:
    if intent == BuildIntent.FLUSH:
        return 3
    if intent == BuildIntent.STRAIGHT:
        return 2
    if intent == BuildIntent.PAIRS:
        return 1
    return 0
