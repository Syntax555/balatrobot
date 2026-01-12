from __future__ import annotations

import functools
import math
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from balatro_ai.cards import card_rank, card_suit

SUITS: tuple[str, ...] = ("spades", "hearts", "diamonds", "clubs")
RANKS: tuple[int, ...] = (2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14)

ACE_HIGH_RANK = 14
ACE_LOW_RANK = 1


def comb(n: int, k: int) -> int:
    """Return the binomial coefficient C(n, k), or 0 for invalid inputs."""
    if k < 0 or n < 0 or k > n:
        return 0
    return _comb_cached(int(n), int(k))


@functools.lru_cache(maxsize=8192)
def _comb_cached(n: int, k: int) -> int:
    return math.comb(n, k)


def hypergeom_at_least(*, population: int, successes: int, draws: int, k_min: int) -> float:
    """
    P(X >= k_min) where X ~ Hypergeometric(population, successes, draws).
    """
    population = max(0, int(population))
    successes = max(0, int(successes))
    draws = max(0, int(draws))
    k_min = int(k_min)
    if population <= 0 or draws <= 0:
        return 1.0 if k_min <= 0 else 0.0
    successes = min(successes, population)
    draws = min(draws, population)
    k_min = max(0, k_min)
    if k_min > draws or k_min > successes:
        return 0.0
    denom = comb(population, draws)
    if denom <= 0:
        return 0.0
    k_max = min(draws, successes)
    num = 0
    for k in range(k_min, k_max + 1):
        num += comb(successes, k) * comb(population - successes, draws - k)
    return float(num) / float(denom)


def probability_of_flush_draw(
    current_deck: Sequence[Mapping[str, Any]],
    *,
    target_suit: str,
    cards_needed: int,
    draws: int,
) -> float:
    playable = [card for card in current_deck if _is_playing_card(card)]
    suit_count = sum(1 for card in playable if card_suit(card) == target_suit)
    return hypergeom_at_least(
        population=len(playable),
        successes=suit_count,
        draws=draws,
        k_min=cards_needed,
    )


def deck_flush_hit_probability(deck_cards: Sequence[Mapping[str, Any]], *, hand_size: int = 5) -> float:
    playable = [card for card in deck_cards if _is_playing_card(card)]
    n = len(playable)
    if hand_size <= 0:
        return 0.0
    if n < hand_size:
        return 0.0
    denom = comb(n, hand_size)
    if denom <= 0:
        return 0.0
    suit_counts = {s: 0 for s in SUITS}
    for card in playable:
        suit = card_suit(card)
        if suit in suit_counts:
            suit_counts[suit] += 1
    num = sum(comb(count, hand_size) for count in suit_counts.values())
    return float(num) / float(denom)


def deck_flush_hit_probability_with_forced_card(
    deck_cards: Sequence[Mapping[str, Any]],
    forced_card: Mapping[str, Any],
    *,
    hand_size: int = 5,
) -> float:
    if hand_size <= 0:
        return 0.0
    draws = hand_size - 1
    if draws <= 0:
        return 1.0
    playable = [card for card in deck_cards if _is_playing_card(card)]
    n = len(playable)
    if n < draws:
        return 0.0
    suit = card_suit(forced_card)
    if suit not in SUITS:
        return 0.0
    suit_count = sum(1 for card in playable if card_suit(card) == suit)
    denom = comb(n, draws)
    if denom <= 0:
        return 0.0
    return float(comb(suit_count, draws)) / float(denom)


def deck_straight_hit_probability(deck_cards: Sequence[Mapping[str, Any]], *, hand_size: int = 5) -> float:
    """
    Exact P(hand is a straight) for a `hand_size` draw, ignoring suits.

    Assumes a straight requires `hand_size` distinct consecutive ranks (A can be low).
    """
    if hand_size != 5:
        raise ValueError("deck_straight_hit_probability currently supports hand_size=5 only")
    playable = [card for card in deck_cards if _is_playing_card(card)]
    n = len(playable)
    if n < hand_size:
        return 0.0
    denom = comb(n, hand_size)
    if denom <= 0:
        return 0.0
    rank_counts = _rank_counts(playable)
    num = 0
    for window in _straight_windows():
        ways = 1
        for rank in window:
            ways *= _rank_count_for_straight(rank_counts, rank)
            if ways == 0:
                break
        num += ways
    return float(num) / float(denom)


def deck_straight_hit_probability_with_forced_card(
    deck_cards: Sequence[Mapping[str, Any]],
    forced_card: Mapping[str, Any],
    *,
    hand_size: int = 5,
) -> float:
    if hand_size != 5:
        raise ValueError("deck_straight_hit_probability_with_forced_card currently supports hand_size=5 only")
    draws = hand_size - 1
    playable = [card for card in deck_cards if _is_playing_card(card)]
    n = len(playable)
    if n < draws:
        return 0.0
    forced_rank = card_rank(forced_card)
    if forced_rank <= 0:
        return 0.0
    denom = comb(n, draws)
    if denom <= 0:
        return 0.0
    rank_counts = _rank_counts(playable)
    num = 0
    for window in _straight_windows_including_rank(forced_rank):
        ways = 1
        for rank in window:
            if _rank_matches_forced(forced_rank, rank):
                continue
            ways *= _rank_count_for_straight(rank_counts, rank)
            if ways == 0:
                break
        num += ways
    return float(num) / float(denom)


def probability_complete_flush_after_draw(
    *,
    kept_suits: Sequence[str | None],
    deck_suits: Sequence[str | None],
    draws: int,
    required: int = 5,
) -> float:
    kept_counts = _count_suits(kept_suits)
    deck_counts = _count_suits(deck_suits)
    spades, hearts, diamonds, clubs = SUITS
    draws = max(0, int(draws))
    required = max(0, int(required))
    if required <= 0:
        return 1.0
    if any(kept_counts[s] >= required for s in SUITS):
        return 1.0
    population = sum(deck_counts.values())
    if draws <= 0:
        return 0.0
    draws = min(draws, population)
    denom = comb(population, draws)
    if denom <= 0:
        return 0.0
    total = 0.0
    spades_in_deck, hearts_in_deck, diamonds_in_deck, clubs_in_deck = (
        deck_counts[s] for s in SUITS
    )
    for spades_drawn in range(0, min(draws, spades_in_deck) + 1):
        for hearts_drawn in range(0, min(draws - spades_drawn, hearts_in_deck) + 1):
            for diamonds_drawn in range(
                0, min(draws - spades_drawn - hearts_drawn, diamonds_in_deck) + 1
            ):
                clubs_drawn = draws - spades_drawn - hearts_drawn - diamonds_drawn
                if clubs_drawn < 0 or clubs_drawn > clubs_in_deck:
                    continue
                if (
                    kept_counts[spades] + spades_drawn >= required
                    or kept_counts[hearts] + hearts_drawn >= required
                    or kept_counts[diamonds] + diamonds_drawn >= required
                    or kept_counts[clubs] + clubs_drawn >= required
                ):
                    ways = (
                        comb(spades_in_deck, spades_drawn)
                        * comb(hearts_in_deck, hearts_drawn)
                        * comb(diamonds_in_deck, diamonds_drawn)
                        * comb(clubs_in_deck, clubs_drawn)
                    )
                    total += float(ways) / float(denom)
    return min(1.0, max(0.0, total))


def probability_complete_straight_after_draw(
    *,
    kept_ranks: Sequence[int],
    deck_cards: Sequence[Mapping[str, Any]],
    draws: int,
    hand_size: int = 5,
) -> float:
    if hand_size != 5:
        raise ValueError("probability_complete_straight_after_draw currently supports hand_size=5 only")
    draws = max(0, int(draws))
    if draws <= 0:
        return 1.0 if _has_straight_from_ranks(kept_ranks) else 0.0

    playable = [card for card in deck_cards if _is_playing_card(card)]
    rank_counts = _rank_counts(playable)
    population = sum(rank_counts.values())
    if population <= 0:
        return 0.0
    draws = min(draws, population)
    denom = comb(population, draws)
    if denom <= 0:
        return 0.0

    kept_present = _present_ranks(kept_ranks)
    if _has_straight_from_present(kept_present):
        return 1.0

    ranks = list(RANKS)
    bounds = [rank_counts.get(rank, 0) for rank in ranks]
    total = 0.0
    for picked in _bounded_count_vectors(bounds, draws):
        present = set(kept_present)
        for idx, count in enumerate(picked):
            if count > 0:
                present.add(ranks[idx])
        if _has_straight_from_present(present):
            ways = 1
            for idx, count in enumerate(picked):
                ways *= comb(bounds[idx], count)
                if ways == 0:
                    break
            total += float(ways) / float(denom)
    return min(1.0, max(0.0, total))


def _is_playing_card(card: Mapping[str, Any]) -> bool:
    return card_rank(card) > 0 and card_suit(card) is not None


def _count_suits(suits: Sequence[str | None]) -> dict[str, int]:
    counts = {s: 0 for s in SUITS}
    for suit in suits:
        if suit in counts:
            counts[suit] += 1
    return counts


def _rank_counts(cards: Iterable[Mapping[str, Any]]) -> dict[int, int]:
    counts: dict[int, int] = {rank: 0 for rank in RANKS}
    for card in cards:
        rank = card_rank(card)
        if rank in counts:
            counts[rank] += 1
    return counts


def _rank_count_for_straight(rank_counts: Mapping[int, int], rank: int) -> int:
    if rank == ACE_LOW_RANK:
        return int(rank_counts.get(ACE_HIGH_RANK, 0))
    return int(rank_counts.get(rank, 0))


def _straight_windows() -> list[list[int]]:
    return [list(window) for window in _STRAIGHT_WINDOWS]


def _straight_windows_including_rank(rank: int) -> list[list[int]]:
    return [list(window) for window in _straight_windows_including_rank_cached(rank)]


@functools.lru_cache(maxsize=32)
def _straight_windows_including_rank_cached(rank: int) -> tuple[tuple[int, ...], ...]:
    rank = int(rank)
    windows: list[tuple[int, ...]] = []
    for window in _STRAIGHT_WINDOWS:
        if rank in window or (rank == ACE_HIGH_RANK and ACE_LOW_RANK in window):
            windows.append(window)
    return tuple(windows)


def _rank_matches_forced(forced_rank: int, window_rank: int) -> bool:
    if forced_rank == window_rank:
        return True
    if forced_rank == ACE_HIGH_RANK and window_rank == ACE_LOW_RANK:
        return True
    return False


def _present_ranks(ranks: Sequence[int]) -> set[int]:
    present = {rank for rank in ranks if rank > 0}
    if ACE_HIGH_RANK in present:
        present.add(ACE_LOW_RANK)
    return present


def _has_straight_from_ranks(ranks: Sequence[int]) -> bool:
    return _has_straight_from_present(_present_ranks(ranks))


def _has_straight_from_present(present: set[int]) -> bool:
    for start in range(ACE_LOW_RANK, 11):
        if all(rank in present for rank in range(start, start + 5)):
            return True
    return False


def _bounded_count_vectors(bounds: list[int], total: int) -> Iterable[list[int]]:
    """Yield count-vectors with per-index bounds that sum to `total`."""
    if total < 0:
        return []

    def rec(i: int, remaining: int, current: list[int]) -> Iterable[list[int]]:
        if i == len(bounds) - 1:
            if 0 <= remaining <= bounds[i]:
                yield current + [remaining]
            return
        for take in range(0, min(remaining, bounds[i]) + 1):
            yield from rec(i + 1, remaining - take, current + [take])

    return rec(0, total, [])


_STRAIGHT_WINDOWS: tuple[tuple[int, ...], ...] = tuple(
    tuple(range(start, start + 5)) for start in range(ACE_LOW_RANK, 11)
)
