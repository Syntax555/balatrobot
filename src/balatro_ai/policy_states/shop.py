from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from balatro_ai.actions import Action
from balatro_ai.joker_order import maybe_reorder_jokers
from balatro_ai.policy_context import DecisionFrame, PolicyContext
from balatro_ai.shop_policy import ShopPolicy

logger = logging.getLogger(__name__)


class ShopAdvisor:
    def __init__(self, shop_policy: ShopPolicy | None = None) -> None:
        self._shop_policy = shop_policy or ShopPolicy()

    def decide(self, gs: Mapping[str, Any], ctx: PolicyContext, frame: DecisionFrame) -> Action:
        reorder_action = maybe_reorder_jokers(gs, ctx)
        if reorder_action is not None:
            logger.debug(
                "ShopAdvisor: joker reorder action=%s params=%s",
                reorder_action.kind,
                reorder_action.params,
            )
            return reorder_action
        if ctx.config.shop_rollout:
            logger.debug("ShopAdvisor: shop_rollout=True -> shop_rollout action")
            return Action(kind="shop_rollout", params={})
        action = self._shop_policy.choose_action(gs, ctx.config, ctx)
        logger.debug("ShopAdvisor: action=%s params=%s", action.kind, action.params)
        return action
