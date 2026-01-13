from __future__ import annotations

from balatro_ai.config import Config
from balatro_ai.policy_context import DecisionFrame, PolicyContext
from balatro_ai.policy_states.hand_selection import HandSelector


def test_hand_selector_prefers_minimal_pair_when_not_rollouting() -> None:
    cfg = Config(
        deck="RED",
        stake="WHITE",
        seed=None,
        max_steps=1,
        timeout=1.0,
        log_level="INFO",
        hand_rollout=False,
    )
    ctx = PolicyContext(config=cfg, run_memory={}, round_memory={})
    frame = DecisionFrame(state="SELECTING_HAND", last_state="SHOP", entering=False)
    gs = {
        "state": "SELECTING_HAND",
        "hand": {
            "cards": [
                {"rank": 2, "suit": "spades"},
                {"rank": 2, "suit": "hearts"},
                {"rank": 11, "suit": "clubs"},
                {"rank": 9, "suit": "diamonds"},
                {"rank": 7, "suit": "spades"},
            ]
        },
        "jokers": [],
    }
    action = HandSelector().decide(gs, ctx, frame)
    assert action.kind == "play"
    assert action.params.get("cards") == [0, 1]
