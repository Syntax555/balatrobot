from __future__ import annotations

from balatro_ai.autotune import Params, _format_bot_flags


def test_autotune_bot_flags_include_intent_trials() -> None:
    params = Params(
        reserve_early=10,
        reserve_mid=20,
        reserve_late=25,
        max_rerolls_per_shop=1,
        rollout_k=30,
        discard_m=12,
        hand_rollout=True,
        rollout_time_budget_s=None,
        shop_rollout=False,
        shop_rollout_candidates=10,
        shop_rollout_time_budget_s=None,
        pack_rollout=False,
        pack_rollout_time_budget_s=None,
        intent_trials=200,
    )
    flags = _format_bot_flags(params)
    assert "--intent-trials=200" in flags
