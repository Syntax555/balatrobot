from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from typing import Any

from balatro_ai.actions import Action
from balatro_ai.gs import gs_ante, gs_money, gs_round_num, gs_state
from balatro_ai.policy_context import DecisionFrame, PolicyContext
from balatro_ai.policy_states import (
    BlindSelectDecider,
    DefaultDecider,
    HandSelector,
    MenuDecider,
    PackChoiceDecider,
    RoundEvalDecider,
    ShopAdvisor,
    TransitionManager,
)

logger = logging.getLogger(__name__)


class Policy:
    """Policy that mirrors the temporary baseline behavior."""

    def __init__(self) -> None:
        self._transitions = TransitionManager()
        self._menu = MenuDecider()
        self._blind_select = BlindSelectDecider()
        self._hand_selector = HandSelector()
        self._round_eval = RoundEvalDecider()
        self._shop_advisor = ShopAdvisor()
        self._pack_choice = PackChoiceDecider()
        self._default = DefaultDecider()
        self._dispatch: dict[str, Callable[[Mapping[str, Any], PolicyContext, DecisionFrame], Action]] = {
            "MENU": self.decide_in_menu,
            "BLIND_SELECT": self.decide_in_blind_select,
            "SELECTING_HAND": self.decide_in_selecting_hand,
            "ROUND_EVAL": self.decide_in_round_eval,
            "SHOP": self.decide_in_shop,
            "SMODS_BOOSTER_OPENED": self.decide_in_pack_choice,
        }

    def decide(self, gs: Mapping[str, Any], ctx: PolicyContext) -> Action:
        """Decide the next action based on the current game state."""
        state = gs_state(gs)
        last_state = ctx.run_memory.get("last_state")
        frame = DecisionFrame(state=state, last_state=last_state, entering=state != last_state)
        self._transitions.before_decide(frame, ctx)
        logger.debug(
            "Policy.decide: state=%s last_state=%s entering=%s ante=%s round=%s money=%s",
            state,
            last_state,
            frame.entering,
            gs_ante(gs),
            gs_round_num(gs),
            gs_money(gs),
        )
        dispatch = self._dispatch.get(state, self.decide_in_default)
        action = dispatch(gs, ctx, frame)
        ctx.run_memory["last_state"] = state
        return action

    def decide_in_menu(
        self,
        gs: Mapping[str, Any],
        ctx: PolicyContext,
        frame: DecisionFrame | None = None,
    ) -> Action:
        if frame is None:
            state = gs_state(gs)
            last_state = ctx.run_memory.get("last_state")
            frame = DecisionFrame(state=state, last_state=last_state, entering=state != last_state)
        return self._menu.decide(gs, ctx, frame)

    def decide_in_blind_select(
        self,
        gs: Mapping[str, Any],
        ctx: PolicyContext,
        frame: DecisionFrame | None = None,
    ) -> Action:
        if frame is None:
            state = gs_state(gs)
            last_state = ctx.run_memory.get("last_state")
            frame = DecisionFrame(state=state, last_state=last_state, entering=state != last_state)
        return self._blind_select.decide(gs, ctx, frame)

    def decide_in_selecting_hand(
        self,
        gs: Mapping[str, Any],
        ctx: PolicyContext,
        frame: DecisionFrame | None = None,
    ) -> Action:
        if frame is None:
            state = gs_state(gs)
            last_state = ctx.run_memory.get("last_state")
            frame = DecisionFrame(state=state, last_state=last_state, entering=state != last_state)
        return self._hand_selector.decide(gs, ctx, frame)

    def decide_in_round_eval(
        self,
        gs: Mapping[str, Any],
        ctx: PolicyContext,
        frame: DecisionFrame | None = None,
    ) -> Action:
        if frame is None:
            state = gs_state(gs)
            last_state = ctx.run_memory.get("last_state")
            frame = DecisionFrame(state=state, last_state=last_state, entering=state != last_state)
        return self._round_eval.decide(gs, ctx, frame)

    def decide_in_shop(
        self,
        gs: Mapping[str, Any],
        ctx: PolicyContext,
        frame: DecisionFrame | None = None,
    ) -> Action:
        if frame is None:
            state = gs_state(gs)
            last_state = ctx.run_memory.get("last_state")
            frame = DecisionFrame(state=state, last_state=last_state, entering=state != last_state)
        return self._shop_advisor.decide(gs, ctx, frame)

    def decide_in_pack_choice(
        self,
        gs: Mapping[str, Any],
        ctx: PolicyContext,
        frame: DecisionFrame | None = None,
    ) -> Action:
        if frame is None:
            state = gs_state(gs)
            last_state = ctx.run_memory.get("last_state")
            frame = DecisionFrame(state=state, last_state=last_state, entering=state != last_state)
        return self._pack_choice.decide(gs, ctx, frame)

    def decide_in_default(
        self,
        gs: Mapping[str, Any],
        ctx: PolicyContext,
        frame: DecisionFrame | None = None,
    ) -> Action:
        if frame is None:
            state = gs_state(gs)
            last_state = ctx.run_memory.get("last_state")
            frame = DecisionFrame(state=state, last_state=last_state, entering=state != last_state)
        return self._default.decide(gs, ctx, frame)
