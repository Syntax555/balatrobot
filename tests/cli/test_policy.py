from __future__ import annotations

from balatro_ai.actions import Action
from balatro_ai.config import Config
from balatro_ai.policy import Policy, PolicyContext


def _cfg(*, auto_start: bool, seed: str | None = None) -> Config:
    return Config(
        deck="RED",
        stake="WHITE",
        seed=seed,
        max_steps=10,
        timeout=1.0,
        log_level="INFO",
        pause_at_menu=False,
        auto_start=auto_start,
    )


def test_policy_menu_auto_start_includes_seed() -> None:
    policy = Policy()
    ctx = PolicyContext(config=_cfg(auto_start=True, seed="TESTSEED"), run_memory={}, round_memory={})

    action = policy.decide({"state": "MENU"}, ctx)

    assert action == Action(kind="start", params={"deck": "RED", "stake": "WHITE", "seed": "TESTSEED"})
    assert ctx.run_memory["last_state"] == "MENU"


def test_policy_menu_no_auto_start_gamestate() -> None:
    policy = Policy()
    ctx = PolicyContext(config=_cfg(auto_start=False), run_memory={}, round_memory={})

    action = policy.decide({"state": "MENU"}, ctx)

    assert action == Action(kind="gamestate", params={})
    assert ctx.run_memory["last_state"] == "MENU"


def test_policy_transition_clears_shop_round_memory_on_exit() -> None:
    policy = Policy()
    ctx = PolicyContext(
        config=_cfg(auto_start=False),
        run_memory={"last_state": "SHOP"},
        round_memory={"shop": {"rerolls_used": 1}},
    )

    action = policy.decide({"state": "BLIND_SELECT"}, ctx)

    assert action == Action(kind="select", params={})
    assert "shop" not in ctx.round_memory
    assert ctx.run_memory["last_state"] == "BLIND_SELECT"


def test_policy_selecting_hand_reorder_only_on_enter(monkeypatch) -> None:
    import balatro_ai.policy_states.hand_selection as hand_selection

    def fake_reorder(gs, ctx):
        return Action(kind="rearrange", params={"jokers": [1, 0]})

    monkeypatch.setattr(hand_selection, "maybe_reorder_jokers", fake_reorder)

    policy = Policy()
    ctx = PolicyContext(config=_cfg(auto_start=False), run_memory={"last_state": "MENU"}, round_memory={})

    first = policy.decide({"state": "SELECTING_HAND", "jokers": [{}, {}]}, ctx)
    second = policy.decide({"state": "SELECTING_HAND", "jokers": [{}, {}]}, ctx)

    assert first.kind == "rearrange"
    assert second == Action(kind="rollout", params={})


def test_policy_unknown_state_uses_default() -> None:
    policy = Policy()
    ctx = PolicyContext(config=_cfg(auto_start=False), run_memory={}, round_memory={})

    action = policy.decide({"state": "SOME_NEW_STATE"}, ctx)

    assert action == Action(kind="gamestate", params={})
    assert ctx.run_memory["last_state"] == "SOME_NEW_STATE"
