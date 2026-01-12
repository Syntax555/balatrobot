from __future__ import annotations

import hashlib
import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from balatro_ai.cards import card_key, card_rank, card_suit
from balatro_ai.hand_stats import (
    max_straight_window_count_from_ranks,
    max_suit_count_from_suits,
)
from balatro_ai.odds import (
    SUITS,
    comb,
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

_SUIT_CONVERT_BY_KEY: dict[str, str] = {
    # Tarots that convert cards to a suit.
    "c_sun": "hearts",
    "c_moon": "clubs",
    "c_star": "diamonds",
    "c_world": "spades",
}

_DESTROY_COUNT_BY_KEY: dict[str, int] = {
    # Not exhaustive; just the common targeted "deck thinning" effects.
    "c_hanged_man": 2,
    "c_immolate": 5,
}

_FACE_RANKS = (11, 12, 13)


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

    base_rng = random.Random(
        _stable_seed(seed_text or f"pack-sim|{intent_mode}|{len(deck_cards)}")
    )
    base = _simulate_value(deck_cards, intent_mode, trials, base_rng)

    scores: list[float] = []
    for index, pack_card in enumerate(pack_cards):
        rng = random.Random(
            _stable_seed(
                (seed_text or "pack-sim") + f"|{intent_mode}|{len(deck_cards)}|{index}"
            )
        )
        scores.append(
            _score_pack_card(deck_cards, pack_card, intent_mode, base, trials, rng)
        )
    return scores


def _score_pack_card(
    deck_cards: Sequence[dict],
    pack_card: Mapping[str, Any],
    intent_mode: str,
    base: DeckSimResult,
    trials: int,
    rng: random.Random,
) -> float:
    """
    Return a delta score for selecting `pack_card`.

    The score is intent-aware: we try to model how the selection changes the deck's
    chance of producing the intent hand type.
    """
    if _is_playing_card(pack_card):
        forced = _simulate_value_with_forced_card(
            deck_cards, pack_card, intent_mode, trials, rng
        )
        draw_prob = min(1.0, HAND_SIZE / (len(deck_cards) + 1))
        return draw_prob * (forced.value - base.value)

    key = card_key(pack_card) or ""

    if intent_mode == "flush":
        suit = _suit_convert_target(key)
        if suit:
            modified = _convert_suit(deck_cards, target_suit=suit, count=3)
            new_hit = deck_flush_hit_probability(modified, hand_size=HAND_SIZE)
            return HIT_WEIGHT * (new_hit - base.hit_rate)
        destroy_count = _DESTROY_COUNT_BY_KEY.get(key, 0)
        if destroy_count > 0:
            target_suit = _majority_suit(deck_cards)
            thinned = _destroy_off_suit(
                deck_cards, target_suit=target_suit, count=destroy_count
            )
            new_hit = deck_flush_hit_probability(thinned, hand_size=HAND_SIZE)
            return HIT_WEIGHT * (new_hit - base.hit_rate)
        if key == "c_death":
            target_suit = _majority_suit(deck_cards)
            modified = _convert_suit(deck_cards, target_suit=target_suit, count=1)
            new_hit = deck_flush_hit_probability(modified, hand_size=HAND_SIZE)
            return HIT_WEIGHT * (new_hit - base.hit_rate)
        if key == "c_familiar":
            target_suit = _majority_suit(deck_cards)
            added = [dict(rank=rank, suit=target_suit) for rank in _FACE_RANKS]
            new_hit = deck_flush_hit_probability(
                [*deck_cards, *added], hand_size=HAND_SIZE
            )
            return HIT_WEIGHT * (new_hit - base.hit_rate)

    if intent_mode == "straight":
        if key == "c_strength":
            best_from = _best_strength_from_ranks(deck_cards)
            if not best_from:
                return 0.0
            modified = list(deck_cards)
            modified = _apply_rank_increments(modified, best_from)
            new_hit = deck_straight_hit_probability(modified, hand_size=HAND_SIZE)
            return HIT_WEIGHT * (new_hit - base.hit_rate)
        if key == "c_death":
            shift = _best_rank_shift_for_straight(deck_cards)
            if not shift:
                return 0.0
            from_rank, to_rank = shift
            modified = _apply_rank_shift(
                deck_cards, from_rank=from_rank, to_rank=to_rank
            )
            new_hit = deck_straight_hit_probability(modified, hand_size=HAND_SIZE)
            return HIT_WEIGHT * (new_hit - base.hit_rate)
        if key == "c_familiar":
            added_ranks = _best_ranks_to_add_for_straight(deck_cards, count=3)
            if not added_ranks:
                return 0.0
            suits = list(SUITS) if SUITS else ["spades", "hearts", "diamonds", "clubs"]
            added = [
                dict(rank=rank, suit=suits[i % len(suits)])
                for i, rank in enumerate(added_ranks)
            ]
            new_hit = deck_straight_hit_probability(
                [*deck_cards, *added], hand_size=HAND_SIZE
            )
            return HIT_WEIGHT * (new_hit - base.hit_rate)

    if intent_mode == "pairs":
        if key == "c_death":
            shift = _best_rank_shift_for_pairs(deck_cards)
            if not shift:
                return 0.0
            from_rank, to_rank = shift
            modified = _apply_rank_shift(
                deck_cards, from_rank=from_rank, to_rank=to_rank
            )
            new = _simulate_value(modified, intent_mode, trials, rng)
            return new.value - base.value
        if key == "c_familiar":
            suits = list(SUITS) if SUITS else ["spades", "hearts", "diamonds", "clubs"]
            added = [
                dict(rank=rank, suit=suits[i % len(suits)])
                for i, rank in enumerate(_FACE_RANKS)
            ]
            new = _simulate_value([*deck_cards, *added], intent_mode, trials, rng)
            return new.value - base.value

    return 0.0


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
                quality_sum += float(
                    max_suit_count_from_suits(card_suit(card) for card in hand)
                )
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
            deck_flush_hit_probability_with_forced_card(
                deck_cards, forced, hand_size=HAND_SIZE
            )
            if intent_mode == "flush"
            else deck_straight_hit_probability_with_forced_card(
                deck_cards, forced, hand_size=HAND_SIZE
            )
        )
        for _ in range(max(1, trials)):
            others = _draw_other_cards(deck_cards, HAND_SIZE - 1, rng)
            hand = [forced, *others]
            if intent_mode == "flush":
                quality_sum += float(
                    max_suit_count_from_suits(card_suit(card) for card in hand)
                )
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


def _draw_other_cards(
    deck_cards: Sequence[dict], count: int, rng: random.Random
) -> list[dict]:
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


def _value_from(
    hit: bool, quality: float, features: Mapping[str, Any], intent_mode: str
) -> float:
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


def _suit_convert_target(key: str) -> str | None:
    if not key:
        return None
    suit = _SUIT_CONVERT_BY_KEY.get(key)
    if suit in SUITS:
        return suit
    return None


def _majority_suit(deck_cards: Sequence[Mapping[str, Any]]) -> str:
    counts = {s: 0 for s in (SUITS or ("spades", "hearts", "diamonds", "clubs"))}
    for card in deck_cards:
        suit = card_suit(card)
        if suit in counts:
            counts[suit] += 1
    ordered_suits = list(SUITS) if SUITS else ["spades", "hearts", "diamonds", "clubs"]
    return max(ordered_suits, key=lambda s: (counts.get(s, 0), -ordered_suits.index(s)))


def _convert_suit(
    deck_cards: Sequence[dict], *, target_suit: str, count: int
) -> list[dict]:
    if count <= 0 or target_suit not in (
        SUITS or ("spades", "hearts", "diamonds", "clubs")
    ):
        return list(deck_cards)
    modified = [dict(card) for card in deck_cards]
    remaining = int(count)
    for card in modified:
        if remaining <= 0:
            break
        suit = card_suit(card)
        if suit is None or suit == target_suit:
            continue
        card["suit"] = target_suit
        remaining -= 1
    return modified


def _destroy_off_suit(
    deck_cards: Sequence[dict], *, target_suit: str, count: int
) -> list[dict]:
    if count <= 0:
        return list(deck_cards)
    remaining = int(count)
    kept: list[dict] = []
    for card in deck_cards:
        suit = card_suit(card)
        if remaining > 0 and suit is not None and suit != target_suit:
            remaining -= 1
            continue
        kept.append(dict(card))
    return kept if kept else list(deck_cards)


def _rank_counts(deck_cards: Sequence[Mapping[str, Any]]) -> dict[int, int]:
    counts: dict[int, int] = {}
    for card in deck_cards:
        rank = card_rank(card)
        if rank <= 0:
            continue
        counts[rank] = counts.get(rank, 0) + 1
    return counts


def _straight_hit_probability_from_rank_counts(
    rank_counts: Mapping[int, int], deck_size: int
) -> float:
    if deck_size < HAND_SIZE:
        return 0.0
    denom = comb(deck_size, HAND_SIZE)
    if denom <= 0:
        return 0.0
    num = 0
    for start in range(1, 11):
        ways = 1
        for rank in range(start, start + 5):
            count = int(
                rank_counts.get(14, 0) if rank == 1 else rank_counts.get(rank, 0)
            )
            ways *= count
            if ways == 0:
                break
        num += ways
    return float(num) / float(denom)


def _best_strength_from_ranks(deck_cards: Sequence[Mapping[str, Any]]) -> list[int]:
    counts = _rank_counts(deck_cards)
    if not counts:
        return []
    base = _straight_hit_probability_from_rank_counts(counts, len(deck_cards))

    candidates = [rank for rank in range(2, 14) if counts.get(rank, 0) > 0]
    best: list[int] = []
    best_p = base
    for r1 in candidates:
        for r2 in candidates:
            if r2 < r1:
                continue
            if r1 == r2 and counts.get(r1, 0) < 2:
                continue
            shifted = dict(counts)
            shifted[r1] = shifted.get(r1, 0) - 1
            shifted[r1 + 1] = shifted.get(r1 + 1, 0) + 1
            shifted[r2] = shifted.get(r2, 0) - 1
            shifted[r2 + 1] = shifted.get(r2 + 1, 0) + 1
            if shifted.get(r1, 0) < 0 or shifted.get(r2, 0) < 0:
                continue
            p = _straight_hit_probability_from_rank_counts(shifted, len(deck_cards))
            if p > best_p + 1e-12:
                best_p = p
                best = [r1, r2]
    return best


def _apply_rank_increments(
    deck_cards: Sequence[dict], from_ranks: Sequence[int]
) -> list[dict]:
    modified = [dict(card) for card in deck_cards]
    remaining: dict[int, int] = {}
    for rank in from_ranks:
        if 2 <= int(rank) <= 13:
            remaining[int(rank)] = remaining.get(int(rank), 0) + 1
    for card in modified:
        rank = card_rank(card)
        need = remaining.get(rank, 0)
        if need <= 0:
            continue
        card["rank"] = min(14, int(rank) + 1)
        remaining[rank] = need - 1
        if all(value <= 0 for value in remaining.values()):
            break
    return modified


def _best_rank_shift_for_straight(
    deck_cards: Sequence[Mapping[str, Any]],
) -> tuple[int, int] | None:
    counts = _rank_counts(deck_cards)
    if not counts:
        return None
    base = _straight_hit_probability_from_rank_counts(counts, len(deck_cards))
    best_shift: tuple[int, int] | None = None
    best_p = base
    ranks = [rank for rank in range(2, 15) if counts.get(rank, 0) > 0]
    for from_rank in ranks:
        for to_rank in ranks:
            if to_rank == from_rank:
                continue
            shifted = dict(counts)
            shifted[from_rank] = shifted.get(from_rank, 0) - 1
            shifted[to_rank] = shifted.get(to_rank, 0) + 1
            if shifted.get(from_rank, 0) < 0:
                continue
            p = _straight_hit_probability_from_rank_counts(shifted, len(deck_cards))
            if p > best_p + 1e-12:
                best_p = p
                best_shift = (from_rank, to_rank)
    return best_shift


def _best_ranks_to_add_for_straight(
    deck_cards: Sequence[Mapping[str, Any]], *, count: int
) -> list[int]:
    if count <= 0:
        return []
    counts = _rank_counts(deck_cards)
    if not counts:
        return []
    best_window: list[int] = []
    best_product = -1
    for start in range(1, 11):
        window = list(range(start, start + 5))
        product = 1
        for rank in window:
            c = int(counts.get(14, 0) if rank == 1 else counts.get(rank, 0))
            product *= max(0, c)
        if product > best_product:
            best_product = product
            best_window = window
    candidates: list[tuple[int, int]] = []
    for rank in best_window:
        actual_rank = 14 if rank == 1 else rank
        candidates.append((int(counts.get(actual_rank, 0)), actual_rank))
    candidates.sort(key=lambda item: (item[0], item[1]))
    chosen: list[int] = []
    for _, rank in candidates:
        if len(chosen) >= int(count):
            break
        chosen.append(rank)
    while len(chosen) < int(count):
        chosen.append(chosen[-1])
    return chosen


def _best_rank_shift_for_pairs(
    deck_cards: Sequence[Mapping[str, Any]],
) -> tuple[int, int] | None:
    counts = _rank_counts(deck_cards)
    if len(counts) < 2:
        return None
    ranks = sorted(counts.items(), key=lambda item: (-item[1], -item[0]))
    to_rank = ranks[0][0]
    from_rank = min(
        (rank for rank in counts if rank != to_rank),
        key=lambda r: (counts.get(r, 0), r),
    )
    if counts.get(from_rank, 0) <= 0:
        return None
    return (from_rank, to_rank)


def _apply_rank_shift(
    deck_cards: Sequence[dict],
    *,
    from_rank: int,
    to_rank: int,
) -> list[dict]:
    if from_rank == to_rank:
        return [dict(card) for card in deck_cards]
    modified = [dict(card) for card in deck_cards]
    for card in modified:
        if card_rank(card) == from_rank:
            card["rank"] = int(to_rank)
            break
    return modified
