from __future__ import annotations

from balatro_ai.config import Config
from balatro_ai.shop_policy import _budget, _joker_category_scores, _score_joker


def test_budget_uses_configured_thresholds() -> None:
    cfg = Config(
        deck="RED",
        stake="WHITE",
        seed=None,
        max_steps=1,
        timeout=1.0,
        log_level="INFO",
        buy_threshold_early=11,
        reroll_threshold_early=22,
        cost_weight_early=3.3,
    )
    gs = {
        "ante_num": 1,
        "money": 0,
        "round_num": 1,
        "round": {"blind": {"score": 0}},
    }
    budget = _budget(cfg, gs, "HIGH_CARD", 0)
    assert budget.buy_threshold == 11
    assert budget.reroll_threshold == 22
    assert budget.cost_weight == 3.3


def test_score_joker_uses_configured_category_scores() -> None:
    cfg = Config(
        deck="RED",
        stake="WHITE",
        seed=None,
        max_steps=1,
        timeout=1.0,
        log_level="INFO",
        joker_score_xmult=123,
        joker_score_mult=4,
        joker_score_chips=5,
        joker_score_econ=-2,
        joker_score_default=7,
    )
    joker = {"key": "j_new_content", "label": "x2 mult"}
    score = _score_joker(
        joker,
        ante=1,
        intent="HIGH_CARD",
        existing_jokers=[],
        category_scores=_joker_category_scores(cfg),
    )
    assert score == 123
