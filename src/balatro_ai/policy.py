from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from balatro_ai.actions import Action
from balatro_ai.config import BotConfig
from balatro_ai.gs import gs_hand_cards, gs_state

JsonObject = dict[str, Any]


@dataclass
class PolicyContext:
    """Context for policy decisions."""

    config: BotConfig
    run_memory: dict[str, Any]
    round_memory: dict[str, Any]


class Policy:
    """Policy that mirrors the temporary baseline behavior."""

    def decide(self, gs: Mapping[str, Any], ctx: PolicyContext) -> Action:
        """Decide the next action based on the current game state."""
        state = gs_state(gs)
        if state == "MENU":
            return self._menu_action(ctx)
        if state == "BLIND_SELECT":
            return Action(kind="select", params={})
        if state == "SELECTING_HAND":
            return self._hand_action(gs)
        if state == "ROUND_EVAL":
            return Action(kind="cash_out", params={})
        if state == "SHOP":
            return Action(kind="next_round", params={})
        if state == "SMODS_BOOSTER_OPENED":
            return Action(kind="pack", params={"card": 0})
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
