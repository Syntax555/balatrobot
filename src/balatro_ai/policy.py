from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

JsonObject = dict[str, Any]


@dataclass(frozen=True)
class Action:
    """Represents a JSON-RPC action to execute."""

    method: str
    params: JsonObject | None = None


class SimplePolicy:
    """Policy that mirrors the temporary baseline behavior."""

    def __init__(self, deck: str, stake: str, seed: str | None) -> None:
        self._deck = deck
        self._stake = stake
        self._seed = seed

    def next_actions(self, state: Mapping[str, Any]) -> list[Action]:
        """Return the next action(s) to take for the current state."""
        game_state = state.get("state")
        if game_state == "MENU":
            return [
                Action(method="menu"),
                Action(method="start", params=self._start_params()),
            ]
        if game_state == "BLIND_SELECT":
            return [Action(method="select")]
        if game_state == "SELECTING_HAND":
            return [self._hand_action(state)]
        if game_state == "ROUND_EVAL":
            return [Action(method="cash_out")]
        if game_state == "SHOP":
            return [Action(method="next_round")]
        if game_state == "SMODS_BOOSTER_OPENED":
            return [Action(method="pack", params={"card": 0})]
        return [Action(method="gamestate")]

    def fallback_actions(self, state: Mapping[str, Any]) -> list[Action]:
        """Return a deterministic safe fallback action for the current state."""
        return self.next_actions(state)

    def _start_params(self) -> JsonObject:
        params: JsonObject = {"deck": self._deck, "stake": self._stake}
        if self._seed:
            params["seed"] = self._seed
        return params

    def _hand_action(self, state: Mapping[str, Any]) -> Action:
        hand = state.get("hand")
        cards = hand.get("cards", []) if isinstance(hand, Mapping) else []
        if not isinstance(cards, list):
            return Action(method="gamestate")
        count = min(5, len(cards))
        if count == 0:
            return Action(method="gamestate")
        indices = list(range(count))
        return Action(method="play", params={"cards": indices})
