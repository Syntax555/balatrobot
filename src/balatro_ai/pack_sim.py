from __future__ import annotations

import hashlib
import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from balatro_ai.cards import card_rank, card_suit
from balatro_ai.hand_stats import (
    max_straight_window_count_from_ranks,
    max_suit_count_from_suits,
)
from balatro_ai.odds import (
    deck_flush_hit_probability,
    deck_flush_hit_probability_with_forced_card,
    deck_straight_hit_probability,
    deck_straight_hit_probability_with_forced_card,
)
from balatro_ai.poker_eval import HandType, evaluate_candidate

HAND_SIZE = 5
DEFAULT_TRIALS = 120

HIT_WEIGHT = 1000.0
QUALITY_WEIGHT = 25.0
HIGH_RANK_SUM_WEIGHT = 1.0

_FLUSH_TYPES = {
    HandType.FLUSH,
    HandType.STRAIGHT_FLUSH,
    HandType.FLUSH_HOUSE,
    HandType.FLUSH_FIVE,
}
_STRAIGHT_TYPES = {HandType.STRAIGHT, HandType.STRAIGHT_FLUSH}
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
class DeckSimResult:
    value: float
    hit_rate: float
    avg_quality: float


def evaluate_pack_choice(
    current_deck: Sequence[Mapping[str, Any]],
    pack_cards: Sequence[Mapping[str, Any]],
    intent: str,
    *,
    trials: int = DEFAULT_TRIALS,
    seed_text: str | None = None,
) -> list[float]:
    """
    Score each pack card via lightweight simulation.

    Returns a list of scores aligned with `pack_cards` indices; higher is better.
    """
    deck_cards = [_coerce_card(card) for card in current_deck if _is_playing_card(card)]
    if len(deck_cards) < 2:
        return [0.0 for _ in pack_cards]

    intent_mode = _intent_mode(intent)
    if not intent_mode:
        return [0.0 for _ in pack_cards]

    base_rng = random.Random(_stable_seed(seed_text or f"pack-sim|{intent_mode}|{len(deck_cards)}"))
    base = _simulate_value(deck_cards, intent_mode, trials, base_rng)

    scores: list[float] = []
    for index, pack_card in enumerate(pack_cards):
        if not _is_playing_card(pack_card):
            scores.append(0.0)
            continue
        forced_rng = random.Random(
            _stable_seed((seed_text or "pack-sim") + f"|{intent_mode}|{len(deck_cards)}|{index}")
        )
        forced = _simulate_value_with_forced_card(deck_cards, pack_card, intent_mode, trials, forced_rng)
        draw_prob = min(1.0, HAND_SIZE / (len(deck_cards) + 1))
        scores.append(draw_prob * (forced.value - base.value))
    return scores


def _simulate_value(
    deck_cards: Sequence[dict],
    intent_mode: str,
    trials: int,
    rng: random.Random,
) -> DeckSimResult:
    if intent_mode in {"flush", "straight"}:
        quality_sum = 0.0
        hit_rate = (
            deck_flush_hit_probability(deck_cards, hand_size=HAND_SIZE)
            if intent_mode == "flush"
            else deck_straight_hit_probability(deck_cards, hand_size=HAND_SIZE)
        )
        for _ in range(max(1, trials)):
            hand = _draw_hand(deck_cards, rng)
            if intent_mode == "flush":
                quality_sum += float(max_suit_count_from_suits(card_suit(card) for card in hand))
            else:
                quality_sum += float(
                    max_straight_window_count_from_ranks(
                        (card_rank(card) for card in hand),
                        window_span=4,
                        ace_high_rank=14,
                        ace_low_rank=1,
                        unknown_rank=0,
                    )
                )
        denom = float(max(1, trials))
        avg_quality = quality_sum / denom
        return DeckSimResult(
            value=(HIT_WEIGHT * hit_rate) + (QUALITY_WEIGHT * avg_quality),
            hit_rate=hit_rate,
            avg_quality=avg_quality,
        )

    hits = 0
    quality_sum = 0.0
    value_sum = 0.0
    for _ in range(max(1, trials)):
        hand = _draw_hand(deck_cards, rng)
        hand_eval = evaluate_candidate(hand, [])
        hand_type = hand_eval["hand_type"]
        features = hand_eval["features"]
        hit = _is_intent_hit(hand_type, intent_mode)
        hits += 1 if hit else 0
        quality = _intent_quality(features, intent_mode)
        quality_sum += quality
        value_sum += _value_from(hit, quality, features, intent_mode)
    denom = float(max(1, trials))
    return DeckSimResult(
        value=value_sum / denom,
        hit_rate=hits / denom,
        avg_quality=quality_sum / denom,
    )


def _simulate_value_with_forced_card(
    deck_cards: Sequence[dict],
    forced_card: Mapping[str, Any],
    intent_mode: str,
    trials: int,
    rng: random.Random,
) -> DeckSimResult:
    forced = _coerce_card(forced_card)
    if intent_mode in {"flush", "straight"}:
        quality_sum = 0.0
        hit_rate = (
            deck_flush_hit_probability_with_forced_card(deck_cards, forced, hand_size=HAND_SIZE)
            if intent_mode == "flush"
            else deck_straight_hit_probability_with_forced_card(deck_cards, forced, hand_size=HAND_SIZE)
        )
        for _ in range(max(1, trials)):
            others = _draw_other_cards(deck_cards, HAND_SIZE - 1, rng)
            hand = [forced, *others]
            if intent_mode == "flush":
                quality_sum += float(max_suit_count_from_suits(card_suit(card) for card in hand))
            else:
                quality_sum += float(
                    max_straight_window_count_from_ranks(
                        (card_rank(card) for card in hand),
                        window_span=4,
                        ace_high_rank=14,
                        ace_low_rank=1,
                        unknown_rank=0,
                    )
                )
        denom = float(max(1, trials))
        avg_quality = quality_sum / denom
        return DeckSimResult(
            value=(HIT_WEIGHT * hit_rate) + (QUALITY_WEIGHT * avg_quality),
            hit_rate=hit_rate,
            avg_quality=avg_quality,
        )

    hits = 0
    quality_sum = 0.0
    value_sum = 0.0
    for _ in range(max(1, trials)):
        others = _draw_other_cards(deck_cards, HAND_SIZE - 1, rng)
        hand = [forced, *others]
        hand_eval = evaluate_candidate(hand, [])
        hand_type = hand_eval["hand_type"]
        features = hand_eval["features"]
        hit = _is_intent_hit(hand_type, intent_mode)
        hits += 1 if hit else 0
        quality = _intent_quality(features, intent_mode)
        quality_sum += quality
        value_sum += _value_from(hit, quality, features, intent_mode)
    denom = float(max(1, trials))
    return DeckSimResult(
        value=value_sum / denom,
        hit_rate=hits / denom,
        avg_quality=quality_sum / denom,
    )


def _draw_hand(deck_cards: Sequence[dict], rng: random.Random) -> list[dict]:
    if len(deck_cards) <= HAND_SIZE:
        return list(deck_cards)
    return rng.sample(list(deck_cards), k=HAND_SIZE)


def _draw_other_cards(deck_cards: Sequence[dict], count: int, rng: random.Random) -> list[dict]:
    if count <= 0:
        return []
    if len(deck_cards) <= count:
        return list(deck_cards)
    return rng.sample(list(deck_cards), k=count)


def _is_intent_hit(hand_type: HandType, intent_mode: str) -> bool:
    if intent_mode == "flush":
        return hand_type in _FLUSH_TYPES
    if intent_mode == "straight":
        return hand_type in _STRAIGHT_TYPES
    if intent_mode == "pairs":
        return hand_type in _PAIRS_TYPES
    return False


def _intent_quality(features: Mapping[str, Any], intent_mode: str) -> float:
    if intent_mode == "flush":
        return float(features.get("flush_count", 0))
    if intent_mode == "straight":
        return float(features.get("straight_quality", 0))
    if intent_mode == "pairs":
        return float(features.get("max_dupe", 0))
    return 0.0


def _value_from(hit: bool, quality: float, features: Mapping[str, Any], intent_mode: str) -> float:
    if not intent_mode:
        return 0.0
    if intent_mode in {"flush", "straight", "pairs"}:
        return (HIT_WEIGHT if hit else 0.0) + QUALITY_WEIGHT * quality
    high_rank_sum = float(features.get("high_rank_sum", 0))
    return HIGH_RANK_SUM_WEIGHT * high_rank_sum


def _intent_mode(intent: str) -> str:
    key = intent.lower() if isinstance(intent, str) else ""
    if "flush" in key:
        return "flush"
    if "straight" in key:
        return "straight"
    if "pair" in key:
        return "pairs"
    return ""


def _is_playing_card(card: Mapping[str, Any]) -> bool:
    return card_rank(card) > 0 and card_suit(card) is not None


def _coerce_card(card: Mapping[str, Any]) -> dict:
    return dict(card) if isinstance(card, Mapping) else {}


def _stable_seed(text: str) -> int:
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big", signed=False)
