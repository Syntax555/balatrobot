from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from balatro_ai.actions import Action
from balatro_ai.build_intent import infer_intent
from balatro_ai.gs import gs_hand_cards, gs_jokers
from balatro_ai.joker_order import maybe_reorder_jokers
from balatro_ai.policy_context import DecisionFrame, PolicyContext
from balatro_ai.rollout import best_play_action

logger = logging.getLogger(__name__)


class HandSelector:
    def decide(
        self, gs: Mapping[str, Any], ctx: PolicyContext, frame: DecisionFrame
    ) -> Action:
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
        hand_cards = gs_hand_cards(gs)
        if not hand_cards:
            return Action(kind="gamestate", params={})
        try:
            intent, _confidence = infer_intent(gs)
            jokers = gs_jokers(gs)
            chosen = best_play_action(hand_cards, jokers, intent, rollout_k=1)
            if chosen is not None:
                logger.debug(
                    "HandSelector: hand_rollout=False -> heuristic play cards=%s",
                    chosen.params.get("cards"),
                )
                return chosen
        except Exception:
            logger.debug(
                "HandSelector: hand_rollout=False -> heuristic failed; fallback",
                exc_info=True,
            )
        count = min(1, len(hand_cards))
        return Action(kind="play", params={"cards": list(range(count))})
