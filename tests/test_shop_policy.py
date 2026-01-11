from __future__ import annotations

from balatro_ai.actions import Action
from balatro_ai.config import Config
from balatro_ai.policy_context import PolicyContext
from balatro_ai.shop_policy import ShopPolicy


def _cfg(*, max_rerolls_per_shop: int = 1) -> Config:
    return Config(
        deck="RED",
        stake="WHITE",
        seed=None,
        max_steps=10,
        timeout=1.0,
        log_level="INFO",
        reserve_early=10,
        reserve_mid=20,
        reserve_late=25,
        max_rerolls_per_shop=max_rerolls_per_shop,
        pause_at_menu=False,
        auto_start=False,
    )


def _ctx(*, intent: str, max_rerolls_per_shop: int = 1) -> PolicyContext:
    return PolicyContext(
        config=_cfg(max_rerolls_per_shop=max_rerolls_per_shop),
        run_memory={"intent": intent},
        round_memory={},
    )


def test_shop_policy_intent_values_suit_joker_for_flush_not_straight() -> None:
    gs_base = {
        "state": "SHOP",
        "money": 50,
        "ante_num": 1,
        "round_num": 1,
        "joker_slots": 5,
        "jokers": [],
        "shop": {
            "cards": [
                {"key": "j_smeared", "label": "Smeared Joker", "cost": {"buy": 5}},
                {"key": "j_crazy", "label": "Crazy Joker", "cost": {"buy": 5}},
            ],
            "vouchers": [],
            "packs": [],
            "reroll_cost": 5,
        },
        "blind": {"score": 300},
    }

    flush_ctx = _ctx(intent="FLUSH")
    straight_ctx = _ctx(intent="STRAIGHT")
    policy = ShopPolicy()

    assert policy.choose_action(gs_base, flush_ctx.config, flush_ctx) == Action(kind="buy", params={"card": 0})
    assert policy.choose_action(gs_base, straight_ctx.config, straight_ctx) == Action(kind="buy", params={"card": 1})


def test_shop_policy_plans_two_purchases_when_affordable() -> None:
    gs = {
        "state": "SHOP",
        "money": 50,
        "ante_num": 1,
        "round_num": 1,
        "joker_slots": 5,
        "jokers": [],
        "shop": {
            "cards": [{"key": "j_smeared", "label": "Smeared Joker", "cost": {"buy": 5}}],
            "vouchers": [{"key": "v_antimatter", "label": "Antimatter", "cost": {"buy": 10}}],
            "packs": [],
            "reroll_cost": 5,
        },
        "blind": {"score": 300},
    }
    ctx = _ctx(intent="FLUSH")
    policy = ShopPolicy()

    assert policy.choose_action(gs, ctx.config, ctx) == Action(kind="buy", params={"card": 0})
    pending = ctx.round_memory.get("shop", {}).get("pending_actions")
    assert isinstance(pending, list)
    assert len(pending) == 1

    gs_after = {
        **gs,
        "money": 45,
        "shop": {
            **gs["shop"],
            "cards": [],
            "vouchers": [{"key": "v_antimatter", "label": "Antimatter", "cost": {"buy": 10}}],
        },
    }
    assert policy.choose_action(gs_after, ctx.config, ctx) == Action(kind="buy", params={"voucher": 0})


def test_shop_policy_rerolls_when_no_items_fit_intent() -> None:
    gs = {
        "state": "SHOP",
        "money": 50,
        "ante_num": 1,
        "round_num": 1,
        "joker_slots": 5,
        "jokers": [],
        "shop": {
            "cards": [{"key": "j_smeared", "label": "Smeared Joker", "cost": {"buy": 5}}],
            "vouchers": [],
            "packs": [],
            "reroll_cost": 5,
        },
        "blind": {"score": 300},
    }
    ctx = _ctx(intent="STRAIGHT", max_rerolls_per_shop=1)
    policy = ShopPolicy()

    assert policy.choose_action(gs, ctx.config, ctx) == Action(kind="reroll", params={})


def test_shop_policy_spends_more_aggressively_when_boss_soon() -> None:
    policy = ShopPolicy()

    gs_base = {
        "state": "SHOP",
        "money": 12,
        "ante_num": 1,
        "joker_slots": 5,
        "jokers": [],
        "shop": {
            "cards": [{"key": "j_crazy", "label": "Crazy Joker", "cost": {"buy": 5}}],
            "vouchers": [],
            "packs": [],
            "reroll_cost": 5,
        },
        "blind": {"score": 300},
    }

    ctx = _ctx(intent="STRAIGHT", max_rerolls_per_shop=0)
    gs_not_boss_soon = {**gs_base, "round_num": 1}
    gs_boss_soon = {**gs_base, "round_num": 2}

    assert policy.choose_action(gs_not_boss_soon, ctx.config, ctx) == Action(kind="next_round", params={})
    assert policy.choose_action(gs_boss_soon, ctx.config, ctx) == Action(kind="buy", params={"card": 0})

