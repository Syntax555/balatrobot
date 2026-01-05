from __future__ import annotations

import enum
from typing import Any, Mapping

from balatro_ai.cards import card_rank, card_suit, card_text

class HandType(str, enum.Enum):
    """Poker hand types for Balatro."""

    HIGH_CARD = "HIGH_CARD"
    PAIR = "PAIR"
    TWO_PAIR = "TWO_PAIR"
    THREE_KIND = "THREE_KIND"
    STRAIGHT = "STRAIGHT"
    FLUSH = "FLUSH"
    FULL_HOUSE = "FULL_HOUSE"
    FOUR_KIND = "FOUR_KIND"
    STRAIGHT_FLUSH = "STRAIGHT_FLUSH"


def classify_hand(cards: list[dict]) -> HandType:
    """Classify a hand with up to 5 cards (straights/flushes only at 5 cards)."""
    count = len(cards)
    if count == 0:
        return HandType.HIGH_CARD
    ranks = [card_rank(card) for card in cards]
    suits = [card_suit(card) for card in cards]
    counts = _rank_counts(ranks)
    max_dupe = max(counts.values(), default=1)
    has_flush = count >= 5 and _flush_count(suits) >= 5
    straight_ranks = _best_straight_ranks(ranks) if count >= 5 else []
    has_straight = bool(straight_ranks)
    if has_flush and has_straight and _straight_flush_possible(cards):
        return HandType.STRAIGHT_FLUSH
    if max_dupe >= 4:
        return HandType.FOUR_KIND
    if max_dupe >= 3 and _has_pair(counts, exclude_rank=_best_rank(counts)):
        return HandType.FULL_HOUSE
    if has_flush:
        return HandType.FLUSH
    if has_straight:
        return HandType.STRAIGHT
    if max_dupe >= 3:
        return HandType.THREE_KIND
    if _pair_count(counts) >= 2:
        return HandType.TWO_PAIR
    if _pair_count(counts) >= 1:
        return HandType.PAIR
    return HandType.HIGH_CARD


def scoring_subset(cards: list[dict], hand_type: HandType, jokers_text: str) -> list[int]:
    """Return scoring card indices for a hand, honoring stone and splash."""
    count = len(cards)
    if count == 0:
        return []
    if "splash" in (jokers_text or "").lower():
        return list(range(count))
    ranks = [card_rank(card) for card in cards]
    suits = [card_suit(card) for card in cards]
    counts = _rank_counts(ranks)
    indices: list[int] = []
    if hand_type == HandType.STRAIGHT_FLUSH:
        indices = _straight_flush_indices(cards)
    elif hand_type == HandType.FOUR_KIND:
        indices = _kind_indices(ranks, counts, 4)
    elif hand_type == HandType.FULL_HOUSE:
        indices = _full_house_indices(ranks, counts)
    elif hand_type == HandType.FLUSH:
        indices = _flush_indices(suits, ranks, limit=5)
    elif hand_type == HandType.STRAIGHT:
        indices = _straight_indices(ranks)
    elif hand_type == HandType.THREE_KIND:
        indices = _kind_indices(ranks, counts, 3)
    elif hand_type == HandType.TWO_PAIR:
        indices = _two_pair_indices(ranks, counts)
    elif hand_type == HandType.PAIR:
        indices = _kind_indices(ranks, counts, 2)
    else:
        indices = _high_card_indices(ranks)
    stone_indices = [i for i, card in enumerate(cards) if _is_stone(card)]
    combined = set(indices)
    combined.update(stone_indices)
    result = sorted(combined)
    return result


def evaluate_candidate(cards: list[dict], jokers: Any) -> dict:
    """Evaluate a hand candidate for heuristics."""
    hand_type = classify_hand(cards)
    jokers_text = _jokers_text(jokers)
    scoring_indices = scoring_subset(cards, hand_type, jokers_text)
    suits = [card_suit(card) for card in cards]
    ranks = [card_rank(card) for card in cards]
    features = {
        "flush_count": _flush_count(suits),
        "max_dupe": max(_rank_counts(ranks).values(), default=1),
        "straight_quality": _straight_quality(ranks),
        "high_rank_sum": _rank_sum(ranks, scoring_indices),
    }
    return {
        "hand_type": hand_type,
        "scoring_indices": scoring_indices,
        "features": features,
    }


def _rank_counts(ranks: list[int]) -> dict[int, int]:
    counts: dict[int, int] = {}
    for rank in ranks:
        if rank <= 0:
            continue
        counts[rank] = counts.get(rank, 0) + 1
    return counts


def _pair_count(counts: Mapping[int, int]) -> int:
    return sum(1 for count in counts.values() if count >= 2)


def _has_pair(counts: Mapping[int, int], exclude_rank: int | None = None) -> bool:
    for rank, count in counts.items():
        if exclude_rank is not None and rank == exclude_rank:
            continue
        if count >= 2:
            return True
    return False


def _best_rank(counts: Mapping[int, int], minimum: int = 3) -> int:
    best = 0
    for rank, count in counts.items():
        if count >= minimum and rank > best:
            best = rank
    return best


def _flush_count(suits: list[str | None]) -> int:
    counts: dict[str, int] = {}
    for suit in suits:
        if not suit:
            continue
        counts[suit] = counts.get(suit, 0) + 1
    return max(counts.values(), default=0)


def _straight_flush_possible(cards: list[dict]) -> bool:
    suits: dict[str, list[int]] = {}
    for index, card in enumerate(cards):
        suit = card_suit(card)
        if not suit:
            continue
        suits.setdefault(suit, []).append(index)
    for indices in suits.values():
        if len(indices) < 5:
            continue
        suited_cards = [cards[i] for i in indices]
        ranks = [card_rank(card) for card in suited_cards]
        if _best_straight_ranks(ranks):
            return True
    return False


def _best_straight_ranks(ranks: list[int]) -> list[int]:
    unique = sorted({rank for rank in ranks if rank > 0})
    if not unique:
        return []
    if 14 in unique:
        unique.append(1)
        unique = sorted(set(unique))
    best: list[int] = []
    for start in unique:
        end = start + 4
        window = [rank for rank in range(start, end + 1)]
        if all(rank in unique for rank in window):
            if not best or end > max(best):
                best = window
    return best


def _straight_indices(ranks: list[int]) -> list[int]:
    target = _best_straight_ranks(ranks)
    if not target:
        return _high_card_indices(ranks)
    rank_to_indices: dict[int, list[int]] = {}
    for index, rank in enumerate(ranks):
        if rank <= 0:
            continue
        rank_to_indices.setdefault(rank, []).append(index)
    indices: list[int] = []
    for rank in target:
        actual_rank = 14 if rank == 1 else rank
        choices = rank_to_indices.get(actual_rank, [])
        if choices:
            indices.append(choices[0])
    return indices


def _straight_flush_indices(cards: list[dict]) -> list[int]:
    best_indices: list[int] = []
    best_high = 0
    suits: dict[str, list[int]] = {}
    for index, card in enumerate(cards):
        suit = card_suit(card)
        if not suit:
            continue
        suits.setdefault(suit, []).append(index)
    for indices in suits.values():
        if len(indices) < 5:
            continue
        suited_cards = [cards[i] for i in indices]
        ranks = [card_rank(card) for card in suited_cards]
        target = _best_straight_ranks(ranks)
        if not target:
            continue
        high = max(target)
        if high > best_high:
            suited_indices = _straight_indices(ranks)
            best_indices = [indices[i] for i in suited_indices]
            best_high = high
    return best_indices or _straight_indices([card_rank(card) for card in cards])


def _kind_indices(ranks: list[int], counts: Mapping[int, int], kind: int) -> list[int]:
    best_rank = 0
    for rank, count in counts.items():
        if count >= kind and rank > best_rank:
            best_rank = rank
    if best_rank == 0:
        return []
    indices: list[int] = []
    for index, rank in enumerate(ranks):
        if rank == best_rank and len(indices) < kind:
            indices.append(index)
    return indices


def _full_house_indices(ranks: list[int], counts: Mapping[int, int]) -> list[int]:
    ranks_sorted = sorted(counts.items(), key=lambda item: item[0], reverse=True)
    triple_rank = None
    pair_rank = None
    for rank, count in ranks_sorted:
        if count >= 3 and triple_rank is None:
            triple_rank = rank
        elif count >= 2 and pair_rank is None:
            pair_rank = rank
    if triple_rank is None or pair_rank is None:
        return []
    indices: list[int] = []
    for index, rank in enumerate(ranks):
        if rank == triple_rank and len(indices) < 3:
            indices.append(index)
        elif rank == pair_rank and len(indices) < 5:
            indices.append(index)
    return indices


def _two_pair_indices(ranks: list[int], counts: Mapping[int, int]) -> list[int]:
    pair_ranks = [rank for rank, count in counts.items() if count >= 2]
    pair_ranks.sort(reverse=True)
    if len(pair_ranks) < 2:
        return []
    selected = set(pair_ranks[:2])
    indices: list[int] = []
    for index, rank in enumerate(ranks):
        if rank in selected and len(indices) < 4:
            indices.append(index)
    return indices


def _high_card_indices(ranks: list[int]) -> list[int]:
    if not ranks:
        return []
    best_index = 0
    best_rank = -1
    for index, rank in enumerate(ranks):
        if rank > best_rank:
            best_rank = rank
            best_index = index
    return [best_index]


def _flush_indices(suits: list[str | None], ranks: list[int], limit: int) -> list[int]:
    suited: dict[str, list[int]] = {}
    for index, suit in enumerate(suits):
        if not suit:
            continue
        suited.setdefault(suit, []).append(index)
    if not suited:
        return []
    best_suit = max(suited.items(), key=lambda item: (len(item[1]), _rank_sum(ranks, item[1])))[0]
    indices = suited[best_suit]
    indices.sort(key=lambda idx: ranks[idx], reverse=True)
    return indices[:limit]


def _rank_sum(ranks: list[int], indices: list[int]) -> int:
    return sum(ranks[index] for index in indices if 0 <= index < len(ranks))


def _straight_quality(ranks: list[int]) -> int:
    unique = sorted({rank for rank in ranks if rank > 0})
    if not unique:
        return 0
    if 14 in unique:
        unique.append(1)
        unique = sorted(set(unique))
    best = 0
    for start in unique:
        end = start + 4
        count = sum(1 for rank in unique if start <= rank <= end)
        if count > best:
            best = count
    return best


def _jokers_text(jokers: Any) -> str:
    if isinstance(jokers, str):
        return jokers.lower()
    if isinstance(jokers, list):
        parts: list[str] = []
        for joker in jokers:
            if isinstance(joker, Mapping):
                parts.append(card_text(joker))
        return " ".join(parts)
    return ""


def _is_stone(card: Mapping[str, Any]) -> bool:
    text_parts: list[str] = []
    for key in ("label", "key", "enhancement", "modifier", "edition"):
        value = card.get(key)
        if isinstance(value, str):
            text_parts.append(value.lower())
        if isinstance(value, Mapping):
            label = value.get("label")
            if isinstance(label, str):
                text_parts.append(label.lower())
            key_val = value.get("key")
            if isinstance(key_val, str):
                text_parts.append(key_val.lower())
    mods = card.get("modifiers")
    if isinstance(mods, list):
        for item in mods:
            if isinstance(item, str):
                text_parts.append(item.lower())
            if isinstance(item, Mapping):
                label = item.get("label")
                if isinstance(label, str):
                    text_parts.append(label.lower())
                key_val = item.get("key")
                if isinstance(key_val, str):
                    text_parts.append(key_val.lower())
    return any("stone" in text for text in text_parts)
