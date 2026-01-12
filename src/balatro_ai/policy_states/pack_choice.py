from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from balatro_ai.actions import Action
from balatro_ai.intent_utils import ctx_intent_text_nonempty
from balatro_ai.pack_policy import PackPolicy
from balatro_ai.policy_context import DecisionFrame, PolicyContext

logger = logging.getLogger(__name__)


class PackChoiceDecider:
    def __init__(self, pack_policy: PackPolicy | None = None) -> None:
        self._pack_policy = pack_policy or PackPolicy()

    def decide(
        self, gs: Mapping[str, Any], ctx: PolicyContext, frame: DecisionFrame
    ) -> Action:
        intent = ctx_intent_text_nonempty(ctx)
        logger.debug("PackChoiceDecider: intent=%r", intent)
        if ctx.config.pack_rollout:
            logger.debug("PackChoiceDecider: pack_rollout=True -> pack_rollout action")
            return Action(kind="pack_rollout", params={})
        action = self._pack_policy.choose_action(gs, ctx.config, ctx, intent)
        logger.debug(
            "PackChoiceDecider: action=%s params=%s", action.kind, action.params
        )
        return action
