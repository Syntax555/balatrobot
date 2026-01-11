from __future__ import annotations

from balatro_ai.actions import Action
from balatro_ai.config import Config
from balatro_ai.joker_order import find_best_joker_sequence, maybe_reorder_jokers
from balatro_ai.policy_context import PolicyContext


def _ctx() -> PolicyContext:
    return PolicyContext(
        config=Config(
            deck="RED",
            stake="WHITE",
            seed=None,
            max_steps=10,
            timeout=1.0,
            log_level="INFO",
            pause_at_menu=False,
            auto_start=False,
        ),
        run_memory={},
        round_memory={},
    )


def test_find_best_joker_sequence_prefers_multiplier_before_negative_mult() -> None:
    hand = [{"rank": 2, "suit": "spades"}]
    jokers = [{"label": "-5 Mult"}, {"label": "X2 Mult"}]
    hands_info = {"High Card": {"chips": 10, "mult": 10}}

    assert find_best_joker_sequence(hand, jokers, hands_info=hands_info) == [1, 0]


def test_maybe_reorder_jokers_returns_rearrange_action() -> None:
    gs = {
        "state": "SELECTING_HAND",
        "hand": {"cards": [{"rank": 2, "suit": "spades"}]},
        "hands": {"High Card": {"chips": 10, "mult": 10}},
        "jokers": [{"label": "-5 Mult"}, {"label": "X2 Mult"}],
    }
    ctx = _ctx()

    assert maybe_reorder_jokers(gs, ctx) == Action(kind="rearrange", params={"jokers": [1, 0]})

