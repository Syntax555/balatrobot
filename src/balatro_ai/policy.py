from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Mapping

from balatro_ai.actions import Action
from balatro_ai.config import Config
from balatro_ai.gs import gs_ante, gs_money, gs_round_num, gs_state
from balatro_ai.joker_order import maybe_reorder_jokers
from balatro_ai.pack_policy import PackPolicy
from balatro_ai.shop_policy import ShopPolicy

JsonObject = dict[str, Any]

logger = logging.getLogger(__name__)


@dataclass
class PolicyContext:
    """Context for policy decisions."""

    config: Config
    run_memory: dict[str, Any]
    round_memory: dict[str, Any]

    @property
    def memory(self) -> dict[str, Any]:
        return self.run_memory


class Policy:
    """Policy that mirrors the temporary baseline behavior."""

    def __init__(self) -> None:
        self._shop_policy = ShopPolicy()
        self._pack_policy = PackPolicy()

    def decide(self, gs: Mapping[str, Any], ctx: PolicyContext) -> Action:
        """Decide the next action based on the current game state."""
        state = gs_state(gs)
        last_state = ctx.run_memory.get("last_state")
        if last_state == "SHOP" and state != "SHOP":
            ctx.round_memory.pop("shop", None)
        entering = state != last_state
        logger.debug(
            "Policy.decide: state=%s last_state=%s entering=%s ante=%s round=%s money=%s",
            state,
            last_state,
            entering,
            gs_ante(gs),
            gs_round_num(gs),
            gs_money(gs),
        )
        if entering and state in {"SHOP", "SELECTING_HAND"}:
            reorder_action = maybe_reorder_jokers(gs, ctx)
            if reorder_action is not None:
                logger.debug(
                    "Policy.decide: joker reorder action=%s params=%s",
                    reorder_action.kind,
                    reorder_action.params,
                )
                ctx.run_memory["last_state"] = state
                return reorder_action
        if state == "MENU":
            return self.decide_in_menu(gs, ctx)
        if state == "BLIND_SELECT":
            return self.decide_in_blind_select(gs, ctx)
        if state == "SELECTING_HAND":
            return self.decide_in_selecting_hand(gs, ctx)
        if state == "ROUND_EVAL":
            return self.decide_in_round_eval(gs, ctx)
        if state == "SHOP":
            return self.decide_in_shop(gs, ctx)
        if state == "SMODS_BOOSTER_OPENED":
            return self.decide_in_pack_choice(gs, ctx)
        return self.decide_in_default(gs, ctx)

    def decide_in_menu(self, gs: Mapping[str, Any], ctx: PolicyContext) -> Action:
        ctx.run_memory["last_state"] = "MENU"
        if ctx.config.auto_start:
            logger.debug("Policy.decide: MENU auto_start=True -> start")
            params: JsonObject = {
                "deck": ctx.config.deck,
                "stake": ctx.config.stake,
            }
            if ctx.config.seed is not None:
                params["seed"] = ctx.config.seed
            return Action(kind="start", params=params)
        logger.debug("Policy.decide: MENU auto_start=False -> gamestate")
        return Action(kind="gamestate", params={})

    def decide_in_blind_select(self, gs: Mapping[str, Any], ctx: PolicyContext) -> Action:
        ctx.run_memory["last_state"] = "BLIND_SELECT"
        logger.debug("Policy.decide: BLIND_SELECT -> select")
        return Action(kind="select", params={})

    def decide_in_selecting_hand(self, gs: Mapping[str, Any], ctx: PolicyContext) -> Action:
        ctx.run_memory["last_state"] = "SELECTING_HAND"
        logger.debug("Policy.decide: SELECTING_HAND -> rollout")
        return Action(kind="rollout", params={})

    def decide_in_round_eval(self, gs: Mapping[str, Any], ctx: PolicyContext) -> Action:
        ctx.run_memory["last_state"] = "ROUND_EVAL"
        logger.debug("Policy.decide: ROUND_EVAL -> cash_out")
        return Action(kind="cash_out", params={})

    def decide_in_shop(self, gs: Mapping[str, Any], ctx: PolicyContext) -> Action:
        reorder_action = maybe_reorder_jokers(gs, ctx)
        if reorder_action is not None:
            logger.debug(
                "Policy.decide: SHOP joker reorder action=%s params=%s",
                reorder_action.kind,
                reorder_action.params,
            )
            ctx.run_memory["last_state"] = "SHOP"
            return reorder_action
        action = self._shop_policy.choose_action(gs, ctx.config, ctx)
        logger.debug(
            "Policy.decide: SHOP action=%s params=%s",
            action.kind,
            action.params,
        )
        ctx.run_memory["last_state"] = "SHOP"
        return action

    def decide_in_pack_choice(self, gs: Mapping[str, Any], ctx: PolicyContext) -> Action:
        ctx.run_memory["last_state"] = "SMODS_BOOSTER_OPENED"
        intent = self._intent(ctx)
        logger.debug("Policy.decide: SMODS_BOOSTER_OPENED intent=%r", intent)
        action = self._pack_policy.choose_action(gs, ctx.config, ctx, intent)
        logger.debug(
            "Policy.decide: SMODS_BOOSTER_OPENED action=%s params=%s",
            action.kind,
            action.params,
        )
        return action

    def decide_in_default(self, gs: Mapping[str, Any], ctx: PolicyContext) -> Action:
        ctx.run_memory["last_state"] = gs_state(gs)
        logger.debug("Policy.decide: default -> gamestate")
        return Action(kind="gamestate", params={})

    def _intent(self, ctx: PolicyContext) -> str:
        intent = ctx.round_memory.get("intent")
        intent_text = _intent_to_text(intent)
        if intent_text:
            return intent_text
        intent = ctx.run_memory.get("intent")
        intent_text = _intent_to_text(intent)
        if intent_text:
            return intent_text
        return ""


def _intent_to_text(intent: Any) -> str:
    if isinstance(intent, str):
        return intent
    value = getattr(intent, "value", None)
    if isinstance(value, str):
        return value
    return ""
