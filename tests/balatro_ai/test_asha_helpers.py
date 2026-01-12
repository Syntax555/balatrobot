from __future__ import annotations

from balatro_ai.asha_tune import _rung_seed_budget


def test_rung_seed_budget_increases_to_max() -> None:
    budgets = [
        _rung_seed_budget(r, min_seeds=6, max_seeds=50, rungs=4) for r in range(4)
    ]
    assert budgets[0] >= 6
    assert budgets[-1] <= 50
    assert budgets == sorted(budgets)

