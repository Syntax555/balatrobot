from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from balatro_ai.actions import Action
from balatro_ai.policy_context import DecisionFrame, PolicyContext

logger = logging.getLogger(__name__)


class MenuDecider:
    def decide(self, gs: Mapping[str, Any], ctx: PolicyContext, frame: DecisionFrame) -> Action:
        if ctx.config.auto_start:
            logger.debug("MenuDecider: auto_start=True -> start")
            params: dict[str, Any] = {
                "deck": ctx.config.deck,
                "stake": ctx.config.stake,
            }
            if ctx.config.seed is not None:
                params["seed"] = ctx.config.seed
            return Action(kind="start", params=params)
        logger.debug("MenuDecider: auto_start=False -> gamestate")
        return Action(kind="gamestate", params={})

