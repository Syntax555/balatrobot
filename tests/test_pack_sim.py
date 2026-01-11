from __future__ import annotations

from balatro_ai.config import Config
from balatro_ai.pack_policy import pick_pack_card_with_simulation
from balatro_ai.pack_sim import evaluate_pack_choice


def _standard_deck() -> list[dict]:
    suits = ["spades", "hearts", "diamonds", "clubs"]
    return [{"rank": rank, "suit": suit} for rank in range(2, 15) for suit in suits]


def _straight_strength_deck() -> list[dict]:
    suits = ["spades", "hearts", "diamonds", "clubs"]
    ranks = [6] * 12 + [7] + [8] * 12 + [9] * 12 + [10] * 12 + [11] * 3
    return [{"rank": rank, "suit": suits[i % len(suits)]} for i, rank in enumerate(ranks)]


def _pairs_death_deck() -> list[dict]:
    suits = ["spades", "hearts", "diamonds", "clubs"]
    ranks: list[int] = []
    ranks.extend([2] * 20)
    ranks.extend([3] * 10)
    for r in range(4, 15):
        ranks.extend([r] * 2)
    assert len(ranks) == 52
    return [{"rank": rank, "suit": suits[i % len(suits)]} for i, rank in enumerate(ranks)]


def test_pack_sim_flush_suit_conversion_scores_positive() -> None:
    deck = _standard_deck()
    pack_cards = [{"key": "c_world", "label": "The World"}, {"key": "c_hermit", "label": "The Hermit"}]

    scores = evaluate_pack_choice(deck, pack_cards, "FLUSH", trials=200, seed_text="test-flush")

    assert scores[0] > 0.0
    assert scores[0] > scores[1]


def test_pack_sim_straight_strength_scores_positive() -> None:
    deck = _straight_strength_deck()
    pack_cards = [{"key": "c_strength", "label": "Strength"}, {"key": "c_hermit", "label": "The Hermit"}]

    scores = evaluate_pack_choice(deck, pack_cards, "STRAIGHT", trials=200, seed_text="test-straight")

    assert scores[0] > 0.0
    assert scores[0] > scores[1]


def test_pack_sim_pairs_death_scores_positive() -> None:
    deck = _pairs_death_deck()
    pack_cards = [{"key": "c_death", "label": "Death"}, {"key": "c_hermit", "label": "The Hermit"}]

    scores = evaluate_pack_choice(deck, pack_cards, "PAIRS", trials=600, seed_text="test-pairs")

    assert scores[0] > 0.0
    assert scores[0] > scores[1]


def test_pack_policy_prefers_simulated_intent_upgrade() -> None:
    deck = _standard_deck()
    pack_cards = [{"key": "c_world", "label": "The World"}, {"key": "c_hermit", "label": "The Hermit"}]
    cfg = Config(
        deck="RED",
        stake="WHITE",
        seed="TEST",
        max_steps=1,
        timeout=1.0,
        log_level="INFO",
        pause_at_menu=False,
        auto_start=False,
    )
    gs = {
        "state": "SMODS_BOOSTER_OPENED",
        "seed": "TEST",
        "cards": {"cards": deck},
        "pack": {"cards": pack_cards},
    }

    idx = pick_pack_card_with_simulation(gs, cfg, pack_cards, "FLUSH")

    assert idx == 0

