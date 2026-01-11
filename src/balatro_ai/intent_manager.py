from __future__ import annotations

import hashlib
import logging
import random
from dataclasses import dataclass
from typing import Any

from balatro_ai.build_intent import BuildIntent
from balatro_ai.cards import card_rank, card_suit, card_tokens
from balatro_ai.gs import gs_jokers, gs_seed
from balatro_ai.hand_stats import (
    max_straight_window_count_from_ranks,
    max_suit_count_from_suits,
)
from balatro_ai.odds import SUITS as _SUITS
from balatro_ai.poker_eval import HandType, evaluate_candidate

logger = logging.getLogger(__name__)


HAND_SIZE = 5
DEFAULT_TRIALS = 200

# The raw values are only compared against a same-sized baseline deck, so absolute scales are less
# important than stability.
HIT_WEIGHT = 1000.0
QUALITY_WEIGHT = 25.0
HIGH_CARD_WEIGHT = 75.0

JOKER_BIAS_PER_MATCH = 0.12

MIN_SWITCH_GAP = 0.08


_PAIRS_TYPES = {
    HandType.PAIR,
    HandType.TWO_PAIR,
    HandType.THREE_KIND,
    HandType.FULL_HOUSE,
    HandType.FOUR_KIND,
    HandType.FIVE_KIND,
    HandType.FLUSH_HOUSE,
    HandType.FLUSH_FIVE,
}


@dataclass(frozen=True)
class IntentEvaluation:
    intent: BuildIntent
    confidence: float
    scores: dict[BuildIntent, float]
    raw_values: dict[BuildIntent, float]
    baseline_values: dict[BuildIntent, float]


class IntentManager:
    """Periodically re-evaluate which build intent is best for the current run."""

    def __init__(self, *, trials: int = DEFAULT_TRIALS) -> None:
        self._trials = max(1, int(trials))

    def evaluate(self, gs: dict[str, Any] | Any, deck_cards: list[dict] | None) -> IntentEvaluation:
        playable = _sorted_playing_cards(deck_cards or [])
        if len(playable) < 2:
            scores = {intent: 0.0 for intent in BuildIntent}
            raw = {intent: 0.0 for intent in BuildIntent}
            baseline = {intent: 0.0 for intent in BuildIntent}
            return IntentEvaluation(
                intent=BuildIntent.HIGH_CARD,
                confidence=0.0,
                scores=scores,
                raw_values=raw,
                baseline_values=baseline,
            )

        seed_text = gs_seed(gs) or "balatrobot"
        baseline_deck = _sorted_playing_cards(_baseline_deck(len(playable)))
        seed_base = f"intent|{seed_text}|deck={len(playable)}"

        jokers = gs_jokers(gs)
        joker_bias = _joker_bias_by_intent(jokers)

        raw_values: dict[BuildIntent, float] = {}
        baseline_values: dict[BuildIntent, float] = {}
        for intent in BuildIntent:
            seed = _stable_seed(f"{seed_base}|{intent.value}")
            rng = random.Random(seed)
            raw_values[intent] = _simulate_deck_value(playable, jokers, intent, self._trials, rng)
            baseline_rng = random.Random(seed)
            baseline_values[intent] = _simulate_deck_value(
                baseline_deck, jokers, intent, self._trials, baseline_rng
            )

        scores: dict[BuildIntent, float] = {}
        for intent in BuildIntent:
            base = baseline_values.get(intent, 0.0)
            raw = raw_values.get(intent, 0.0)
            rel = (raw - base) / base if base > 0.0 else 0.0
            scores[intent] = rel + joker_bias.get(intent, 0.0)

        best, second = _top_two(scores)
        best_score = scores.get(best, 0.0)
        second_score = scores.get(second, 0.0)
        gap = best_score - second_score
        confidence = _confidence_from_gap(gap)
        if best != BuildIntent.HIGH_CARD and (best_score <= 0.0 or gap < MIN_SWITCH_GAP):
            best = BuildIntent.HIGH_CARD
            confidence = 0.0
        return IntentEvaluation(
            intent=best,
            confidence=confidence,
            scores=scores,
            raw_values=raw_values,
            baseline_values=baseline_values,
        )

    def estimate_intent_probabilities(
        self,
        gs: dict[str, Any] | Any,
        deck_cards: list[dict] | None,
        *,
        trials: int | None = None,
    ) -> dict[BuildIntent, float]:
        """Estimate intent hit probabilities from the current deck via Monte Carlo."""
        playable = _sorted_playing_cards(deck_cards or [])
        if len(playable) < HAND_SIZE:
            return {intent: 0.0 for intent in BuildIntent}

        jokers = gs_jokers(gs)
        seed_text = gs_seed(gs) or "balatrobot"
        seed_base = f"intent|prob|{seed_text}|deck={len(playable)}"
        rng = random.Random(_stable_seed(seed_base))
        draws = max(1, int(trials) if trials is not None else self._trials)

        hits = {intent: 0 for intent in BuildIntent}
        for _ in range(draws):
            hand = rng.sample(playable, k=HAND_SIZE)
            hand_type = evaluate_candidate(hand, jokers)["hand_type"]
            if hand_type in {
                HandType.FLUSH,
                HandType.STRAIGHT_FLUSH,
                HandType.FLUSH_HOUSE,
                HandType.FLUSH_FIVE,
            }:
                hits[BuildIntent.FLUSH] += 1
            if hand_type in {HandType.STRAIGHT, HandType.STRAIGHT_FLUSH}:
                hits[BuildIntent.STRAIGHT] += 1
            if hand_type in _PAIRS_TYPES:
                hits[BuildIntent.PAIRS] += 1
            if hand_type == HandType.HIGH_CARD:
                hits[BuildIntent.HIGH_CARD] += 1

        denom = float(draws)
        return {intent: hits[intent] / denom for intent in BuildIntent}

    def should_switch(
        self,
        *,
        current: BuildIntent | None,
        evaluation: IntentEvaluation,
    ) -> bool:
        if current is None:
            return True
        if evaluation.intent == current:
            return False
        current_score = evaluation.scores.get(current, 0.0)
        best_score = evaluation.scores.get(evaluation.intent, 0.0)
        return (best_score - current_score) >= MIN_SWITCH_GAP


def _simulate_deck_value(
    deck_cards: list[dict],
    jokers: list[dict],
    intent: BuildIntent,
    trials: int,
    rng: random.Random,
) -> float:
    if len(deck_cards) < HAND_SIZE:
        return 0.0

    hits = 0
    quality_sum = 0.0
    high_sum = 0.0
    for _ in range(max(1, trials)):
        hand = rng.sample(deck_cards, k=HAND_SIZE)
        if intent == BuildIntent.FLUSH:
            suits = [card_suit(card) for card in hand]
            max_suit = max_suit_count_from_suits(suits)
            quality_sum += float(max_suit)
            hits += 1 if max_suit >= HAND_SIZE else 0
        elif intent == BuildIntent.STRAIGHT:
            ranks = [card_rank(card) for card in hand]
            max_window = max_straight_window_count_from_ranks(
                ranks,
                window_span=4,
                ace_high_rank=14,
                ace_low_rank=1,
                unknown_rank=0,
            )
            quality_sum += float(max_window)
            hits += 1 if max_window >= HAND_SIZE else 0
        elif intent == BuildIntent.PAIRS:
            eval_result = evaluate_candidate(hand, jokers)
            hand_type = eval_result["hand_type"]
            features = eval_result["features"]
            hits += 1 if hand_type in _PAIRS_TYPES else 0
            quality_sum += float(features.get("max_dupe", 0))
            high_sum += float(features.get("high_rank_sum", 0))
        else:
            eval_result = evaluate_candidate(hand, jokers)
            features = eval_result["features"]
            high_sum += float(features.get("high_rank_sum", 0))

    denom = float(max(1, trials))
    hit_rate = hits / denom
    avg_quality = quality_sum / denom
    avg_high = high_sum / denom
    if intent == BuildIntent.HIGH_CARD:
        return HIGH_CARD_WEIGHT * avg_high
    if intent == BuildIntent.PAIRS:
        return (HIT_WEIGHT * hit_rate) + (QUALITY_WEIGHT * avg_quality) + avg_high
    return (HIT_WEIGHT * hit_rate) + (QUALITY_WEIGHT * avg_quality)


def _baseline_deck(deck_size: int) -> list[dict]:
    ranks = list(range(2, 15))
    suits = list(_SUITS) if _SUITS else ["spades", "hearts", "diamonds", "clubs"]
    base = [{"rank": rank, "suit": suit} for rank in ranks for suit in suits]
    if deck_size <= 0:
        return []
    if deck_size <= len(base):
        return base[:deck_size]
    repeated: list[dict] = []
    while len(repeated) < deck_size:
        repeated.extend(base)
    return repeated[:deck_size]


def _joker_bias_by_intent(jokers: list[dict]) -> dict[BuildIntent, float]:
    counts = {intent: 0 for intent in BuildIntent}
    for joker in jokers:
        text = str(joker.get("label") or joker.get("key") or "")
        tokens = card_tokens(text)
        if not tokens:
            continue
        if "flush" in tokens:
            counts[BuildIntent.FLUSH] += 1
        if "straight" in tokens:
            counts[BuildIntent.STRAIGHT] += 1
        if _matches_pairs(tokens):
            counts[BuildIntent.PAIRS] += 1
        if _matches_high_card(tokens):
            counts[BuildIntent.HIGH_CARD] += 1
    return {intent: float(count) * JOKER_BIAS_PER_MATCH for intent, count in counts.items()}


def _matches_pairs(tokens: set[str]) -> bool:
    if tokens & {"pair", "pairs", "kind"}:
        return True
    return "full" in tokens and "house" in tokens


def _matches_high_card(tokens: set[str]) -> bool:
    if "high" in tokens and "card" in tokens:
        return True
    return "highcard" in tokens or "high_card" in tokens


def _is_playing_card(card: Any) -> bool:
    return isinstance(card, dict) and card_rank(card) > 0 and card_suit(card) is not None


def _sorted_playing_cards(cards: list[dict]) -> list[dict]:
    playable = [card for card in cards if _is_playing_card(card)]
    return sorted(playable, key=lambda card: (card_rank(card), card_suit(card) or ""))


def _stable_seed(text: str) -> int:
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big", signed=False)


def _top_two(scores: dict[BuildIntent, float]) -> tuple[BuildIntent, BuildIntent]:
    ordered = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    if not ordered:
        return (BuildIntent.HIGH_CARD, BuildIntent.HIGH_CARD)
    best = ordered[0][0]
    second = ordered[1][0] if len(ordered) > 1 else best
    return (best, second)


def _confidence_from_gap(gap: float) -> float:
    # gap is a relative advantage (dimensionless). Values around 0.25 are generally decisive.
    scaled = gap / 0.25
    if scaled <= 0.0:
        return 0.0
    return min(1.0, float(scaled))
