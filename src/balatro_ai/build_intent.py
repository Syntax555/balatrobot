from __future__ import annotations

import enum
from typing import Any, Mapping

from balatro_ai.cards import card_rank, card_suit, card_tokens
from balatro_ai.gs import gs_hand_cards, gs_jokers
from balatro_ai.joker_order import joker_text


class BuildIntent(str, enum.Enum):
    """Build intent for the run."""

    FLUSH = "FLUSH"
    STRAIGHT = "STRAIGHT"
    PAIRS = "PAIRS"
    HIGH_CARD = "HIGH_CARD"




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
    counts = {
        BuildIntent.FLUSH: 0,
        BuildIntent.STRAIGHT: 0,
        BuildIntent.PAIRS: 0,
    }
    for joker in gs_jokers(gs):
        tokens = card_tokens(joker_text(joker))
        if not tokens:
            continue
        if "flush" in tokens:
            counts[BuildIntent.FLUSH] += 1
        if "straight" in tokens:
            counts[BuildIntent.STRAIGHT] += 1
        if _matches_pairs(tokens):
            counts[BuildIntent.PAIRS] += 1
    best_intent = max(counts.items(), key=lambda item: (item[1], _intent_priority(item[0])))
    if best_intent[1] <= 0:
        return None
    confidence = _joker_confidence(best_intent[1])
    return best_intent[0], confidence


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
        suit = card_suit(card)
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
    ranks = [card_rank(card) for card in hand]
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
    ranks = {card_rank(card) for card in hand}
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


def _intent_priority(intent: BuildIntent) -> int:
    if intent == BuildIntent.FLUSH:
        return 3
    if intent == BuildIntent.STRAIGHT:
        return 2
    if intent == BuildIntent.PAIRS:
        return 1
    return 0


def _matches_pairs(tokens: set[str]) -> bool:
    if tokens & {"pair", "pairs", "kind"}:
        return True
    return "full" in tokens and "house" in tokens


def _joker_confidence(count: int) -> float:
    return min(0.9, 0.6 + 0.1 * max(0, count - 1))
