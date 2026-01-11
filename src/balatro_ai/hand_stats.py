from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from balatro_ai.cards import card_rank, card_suit


def suit_counts_from_suits(suits: Iterable[str | None]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for suit in suits:
        if not suit:
            continue
        counts[suit] = counts.get(suit, 0) + 1
    return counts


def suit_counts(cards: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    return suit_counts_from_suits(card_suit(card) for card in cards)


def max_suit_count_from_suits(suits: Iterable[str | None]) -> int:
    counts = suit_counts_from_suits(suits)
    return max(counts.values()) if counts else 0


def max_suit_count(cards: Iterable[Mapping[str, Any]]) -> int:
    return max_suit_count_from_suits(card_suit(card) for card in cards)


def majority_suit_from_suits(suits: Iterable[str | None]) -> str | None:
    counts = suit_counts_from_suits(suits)
    if not counts:
        return None
    return max(counts.items(), key=lambda item: item[1])[0]


def majority_suit(cards: Iterable[Mapping[str, Any]]) -> str | None:
    return majority_suit_from_suits(card_suit(card) for card in cards)


def rank_counts_from_ranks(
    ranks: Iterable[int],
    *,
    include_unknown: bool = True,
    unknown_rank: int = 0,
) -> dict[int, int]:
    counts: dict[int, int] = {}
    for rank in ranks:
        if not include_unknown and rank <= unknown_rank:
            continue
        counts[rank] = counts.get(rank, 0) + 1
    return counts


def max_rank_count_from_ranks(
    ranks: Iterable[int],
    *,
    include_unknown: bool = True,
    unknown_rank: int = 0,
) -> int:
    counts = rank_counts_from_ranks(
        ranks, include_unknown=include_unknown, unknown_rank=unknown_rank
    )
    return max(counts.values()) if counts else 0


def max_straight_window_count_from_ranks(
    ranks: Iterable[int],
    *,
    window_span: int = 4,
    ace_high_rank: int = 14,
    ace_low_rank: int = 1,
    unknown_rank: int = 0,
) -> int:
    unique = {rank for rank in ranks if rank > unknown_rank}
    if not unique:
        return 0
    if ace_high_rank in unique:
        unique.add(ace_low_rank)
    ordered = sorted(unique)
    best = 0
    for start in ordered:
        end = start + window_span
        count = sum(1 for rank in ordered if start <= rank <= end)
        if count > best:
            best = count
    return best


def max_straight_window_count(cards: Iterable[Mapping[str, Any]]) -> int:
    return max_straight_window_count_from_ranks(card_rank(card) for card in cards)
