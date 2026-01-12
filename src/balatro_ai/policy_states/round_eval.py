from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from balatro_ai.actions import Action
from balatro_ai.policy_context import DecisionFrame, PolicyContext

logger = logging.getLogger(__name__)


class RoundEvalDecider:
    def decide(
        self, gs: Mapping[str, Any], ctx: PolicyContext, frame: DecisionFrame
    ) -> Action:
        logger.debug("RoundEvalDecider: -> cash_out")
        return Action(kind="cash_out", params={})
