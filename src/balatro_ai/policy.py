from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from balatro_ai.actions import Action
from balatro_ai.config import Config
from balatro_ai.gs import gs_hand_cards, gs_state
from balatro_ai.joker_order import maybe_reorder_jokers
from balatro_ai.shop_policy import ShopPolicy

JsonObject = dict[str, Any]


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

    def decide(self, gs: Mapping[str, Any], ctx: PolicyContext) -> Action:
        """Decide the next action based on the current game state."""
        state = gs_state(gs)
        last_state = ctx.run_memory.get("last_state")
        if last_state == "SHOP" and state != "SHOP":
            ctx.round_memory.pop("shop", None)
        entering = state != last_state
        if entering and state in {"SHOP", "SELECTING_HAND"}:
            reorder_action = maybe_reorder_jokers(gs, ctx)
            if reorder_action is not None:
                ctx.run_memory["last_state"] = state
                return reorder_action
        if state == "MENU":
            action = self._menu_action(ctx)
            ctx.run_memory["last_state"] = state
            return action
        if state == "BLIND_SELECT":
            ctx.run_memory["last_state"] = state
            return Action(kind="select", params={})
        if state == "SELECTING_HAND":
            action = self._hand_action(gs)
            ctx.run_memory["last_state"] = state
            return action
        if state == "ROUND_EVAL":
            ctx.run_memory["last_state"] = state
            return Action(kind="cash_out", params={})
        if state == "SHOP":
            reorder_action = maybe_reorder_jokers(gs, ctx)
            if reorder_action is not None:
                ctx.run_memory["last_state"] = state
                return reorder_action
            action = self._shop_policy.choose_action(gs, ctx.config, ctx)
            ctx.run_memory["last_state"] = state
            return action
        if state == "SMODS_BOOSTER_OPENED":
            ctx.run_memory["last_state"] = state
            return Action(kind="pack", params={"card": 0})
        ctx.run_memory["last_state"] = state
        return Action(kind="gamestate", params={})

    def _menu_action(self, ctx: PolicyContext) -> Action:
        if not ctx.run_memory.get("menu_sent"):
            ctx.run_memory["menu_sent"] = True
            return Action(kind="menu", params={})
        params: JsonObject = {"deck": ctx.config.deck, "stake": ctx.config.stake}
        if ctx.config.seed is not None:
            params["seed"] = ctx.config.seed
        return Action(kind="start", params=params)

    def _hand_action(self, gs: Mapping[str, Any]) -> Action:
        cards = gs_hand_cards(gs)
        count = min(5, len(cards))
        if count == 0:
            return Action(kind="gamestate", params={})
        indices = list(range(count))
        return Action(kind="play", params={"cards": indices})
