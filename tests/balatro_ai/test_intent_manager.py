from __future__ import annotations

import random

from balatro_ai.build_intent import BuildIntent
from balatro_ai.intent_manager import IntentManager, _simulate_deck_values


def test_simulate_deck_values_returns_all_intents() -> None:
    deck = [
        {"rank": 2, "suit": "spades"},
        {"rank": 3, "suit": "spades"},
        {"rank": 4, "suit": "spades"},
        {"rank": 5, "suit": "spades"},
        {"rank": 6, "suit": "spades"},
        {"rank": 7, "suit": "hearts"},
        {"rank": 8, "suit": "diamonds"},
        {"rank": 9, "suit": "clubs"},
        {"rank": 10, "suit": "clubs"},
        {"rank": 11, "suit": "hearts"},
    ]
    values = _simulate_deck_values(deck, jokers=[], trials=10, rng=random.Random(0))
    assert set(values) == set(BuildIntent)
    for intent, value in values.items():
        assert isinstance(intent, BuildIntent)
        assert isinstance(value, float)


def test_intent_manager_evaluate_smoke() -> None:
    deck = [
        {"rank": 2, "suit": "spades"},
        {"rank": 3, "suit": "spades"},
        {"rank": 4, "suit": "spades"},
        {"rank": 5, "suit": "spades"},
        {"rank": 6, "suit": "spades"},
        {"rank": 7, "suit": "hearts"},
        {"rank": 8, "suit": "diamonds"},
        {"rank": 9, "suit": "clubs"},
        {"rank": 10, "suit": "clubs"},
        {"rank": 11, "suit": "hearts"},
    ]
    evaluation = IntentManager(trials=25).evaluate({"seed": "X", "jokers": []}, deck)
    assert evaluation.intent in BuildIntent
    assert set(evaluation.scores) == set(BuildIntent)
    assert set(evaluation.raw_values) == set(BuildIntent)
    assert set(evaluation.baseline_values) == set(BuildIntent)
