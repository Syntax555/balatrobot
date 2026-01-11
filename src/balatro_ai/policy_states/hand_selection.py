from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from balatro_ai.actions import Action
from balatro_ai.joker_order import maybe_reorder_jokers
from balatro_ai.policy_context import DecisionFrame, PolicyContext

logger = logging.getLogger(__name__)


class HandSelector:
    def decide(self, gs: Mapping[str, Any], ctx: PolicyContext, frame: DecisionFrame) -> Action:
        if frame.entering:
            reorder_action = maybe_reorder_jokers(gs, ctx)
            if reorder_action is not None:
                logger.debug(
                    "HandSelector: joker reorder action=%s params=%s",
                    reorder_action.kind,
                    reorder_action.params,
                )
                return reorder_action
        logger.debug("HandSelector: -> rollout")
        return Action(kind="rollout", params={})

