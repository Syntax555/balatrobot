from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from balatro_ai.actions import Action
from balatro_ai.joker_order import maybe_reorder_jokers
from balatro_ai.gs import gs_hand_cards
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
        if ctx.config.hand_rollout:
            logger.debug("HandSelector: hand_rollout=True -> rollout")
            return Action(kind="rollout", params={})
        cards = gs_hand_cards(gs)
        count = min(5, len(cards))
        if count <= 0:
            return Action(kind="gamestate", params={})
        logger.debug("HandSelector: hand_rollout=False -> play first %s", count)
        return Action(kind="play", params={"cards": list(range(count))})
