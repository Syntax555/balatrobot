from __future__ import annotations

import enum
from typing import Any, Mapping

from balatro_ai.cards import card_rank, card_tokens
from balatro_ai.gs import gs_hand_cards, gs_jokers
from balatro_ai.hand_stats import (
    max_rank_count_from_ranks,
    max_straight_window_count_from_ranks,
    max_suit_count,
)
from balatro_ai.joker_order import joker_text


class BuildIntent(str, enum.Enum):
    """Build intent for the run."""

    FLUSH = "FLUSH"
    STRAIGHT = "STRAIGHT"
    PAIRS = "PAIRS"
    HIGH_CARD = "HIGH_CARD"


HAND_CONFIDENCE_OVERRIDE_THRESHOLD = 0.95
CONFIDENCE_NONE = 0.0
CONFIDENCE_MAX = 1.0

INTENT_COUNT_INITIAL = 0
INTENT_COUNT_INCREMENT = 1

FLUSH_MIN_SUITS_IN_HAND = 4
HAND_SIZE_FOR_CONFIDENCE = 5.0

PAIRS_MIN_DUPLICATE_COUNT = 2
PAIRS_CONFIDENCE_DIVISOR = 4.0

ACE_HIGH_RANK = 14
ACE_LOW_RANK = 1
RANK_UNKNOWN = 0
STRAIGHT_WINDOW_SPAN = 4
STRAIGHT_MIN_RANKS_IN_WINDOW = 3

INTENT_PRIORITY_FLUSH = 3
INTENT_PRIORITY_STRAIGHT = 2
INTENT_PRIORITY_PAIRS = 1
INTENT_PRIORITY_DEFAULT = 0

JOKER_CONFIDENCE_MAX = 0.9
JOKER_CONFIDENCE_BASE = 0.6
JOKER_CONFIDENCE_PER_EXTRA = 0.1
JOKER_CONFIDENCE_EXTRA_OFFSET = 1

FIRST_INDEX = 0
SECOND_INDEX = 1




def infer_intent(gs: Mapping[str, Any]) -> tuple[BuildIntent, float]:
    """Infer a build intent and confidence from the game state."""
    joker_intent = _intent_from_jokers(gs)
    hand_intent, hand_conf = _intent_from_hand(gs)
    if joker_intent is not None:
        if (
            hand_conf >= HAND_CONFIDENCE_OVERRIDE_THRESHOLD
            and hand_conf > joker_intent[SECOND_INDEX]
        ):
            return hand_intent, hand_conf
        return joker_intent
    if hand_conf > CONFIDENCE_NONE:
        return hand_intent, hand_conf
    return BuildIntent.HIGH_CARD, CONFIDENCE_NONE


def _intent_from_jokers(gs: Mapping[str, Any]) -> tuple[BuildIntent, float] | None:
    counts = {
        BuildIntent.FLUSH: INTENT_COUNT_INITIAL,
        BuildIntent.STRAIGHT: INTENT_COUNT_INITIAL,
        BuildIntent.PAIRS: INTENT_COUNT_INITIAL,
    }
    for joker in gs_jokers(gs):
        tokens = card_tokens(joker_text(joker))
        if not tokens:
            continue
        if "flush" in tokens:
            counts[BuildIntent.FLUSH] += INTENT_COUNT_INCREMENT
        if "straight" in tokens:
            counts[BuildIntent.STRAIGHT] += INTENT_COUNT_INCREMENT
        if _matches_pairs(tokens):
            counts[BuildIntent.PAIRS] += INTENT_COUNT_INCREMENT
    best_intent = max(
        counts.items(),
        key=lambda item: (item[SECOND_INDEX], _intent_priority(item[FIRST_INDEX])),
    )
    if best_intent[SECOND_INDEX] <= INTENT_COUNT_INITIAL:
        return None
    confidence = _joker_confidence(best_intent[SECOND_INDEX])
    return best_intent[FIRST_INDEX], confidence


def _intent_from_hand(gs: Mapping[str, Any]) -> tuple[BuildIntent, float]:
    hand = gs_hand_cards(gs)
    if not hand:
        return BuildIntent.HIGH_CARD, CONFIDENCE_NONE
    flush_conf = _flush_conf(hand)
    straight_conf = _straight_conf(hand)
    pairs_conf = _pairs_conf(hand)
    intents = [
        (BuildIntent.FLUSH, flush_conf),
        (BuildIntent.STRAIGHT, straight_conf),
        (BuildIntent.PAIRS, pairs_conf),
    ]
    best = max(
        intents,
        key=lambda item: (item[SECOND_INDEX], _intent_priority(item[FIRST_INDEX])),
    )
    if best[SECOND_INDEX] <= CONFIDENCE_NONE:
        return BuildIntent.HIGH_CARD, CONFIDENCE_NONE
    return best


def _flush_conf(hand: list[dict]) -> float:
    max_count = max_suit_count(hand)
    if max_count >= FLUSH_MIN_SUITS_IN_HAND:
        return max_count / HAND_SIZE_FOR_CONFIDENCE
    return CONFIDENCE_NONE


def _pairs_conf(hand: list[dict]) -> float:
    ranks = [card_rank(card) for card in hand]
    max_dup = max_rank_count_from_ranks(ranks, include_unknown=False, unknown_rank=RANK_UNKNOWN)
    if max_dup >= PAIRS_MIN_DUPLICATE_COUNT:
        return min(CONFIDENCE_MAX, max_dup / PAIRS_CONFIDENCE_DIVISOR)
    return CONFIDENCE_NONE


def _straight_conf(hand: list[dict]) -> float:
    max_count = max_straight_window_count_from_ranks(
        (card_rank(card) for card in hand),
        window_span=STRAIGHT_WINDOW_SPAN,
        ace_high_rank=ACE_HIGH_RANK,
        ace_low_rank=ACE_LOW_RANK,
        unknown_rank=RANK_UNKNOWN,
    )
    if max_count >= STRAIGHT_MIN_RANKS_IN_WINDOW:
        return max_count / HAND_SIZE_FOR_CONFIDENCE
    return CONFIDENCE_NONE


def _intent_priority(intent: BuildIntent) -> int:
    if intent == BuildIntent.FLUSH:
        return INTENT_PRIORITY_FLUSH
    if intent == BuildIntent.STRAIGHT:
        return INTENT_PRIORITY_STRAIGHT
    if intent == BuildIntent.PAIRS:
        return INTENT_PRIORITY_PAIRS
    return INTENT_PRIORITY_DEFAULT


def _matches_pairs(tokens: set[str]) -> bool:
    if tokens & {"pair", "pairs", "kind"}:
        return True
    return "full" in tokens and "house" in tokens


def _joker_confidence(count: int) -> float:
    return min(
        JOKER_CONFIDENCE_MAX,
        JOKER_CONFIDENCE_BASE
        + JOKER_CONFIDENCE_PER_EXTRA
        * max(INTENT_COUNT_INITIAL, count - JOKER_CONFIDENCE_EXTRA_OFFSET),
    )
