from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Mapping

from balatro_ai.rpc import BalatroRPC, BalatroRPCError
from balatro_ai.policy import Action, SimplePolicy

GameState = dict[str, Any]


@dataclass(frozen=True)
class BotConfig:
    """Configuration for running the bot."""

    base_url: str
    deck: str
    stake: str
    seed: str | None
    max_steps: int
    timeout: float


class BotRunner:
    """Runs a BalatroBot loop until game over or step limit."""

    def __init__(self, config: BotConfig) -> None:
        self._config = config
        self._logger = logging.getLogger(__name__)
        self._client = BalatroRPC(
            base_url=config.base_url,
            timeout=config.timeout,
        )
        self._policy = SimplePolicy(
            deck=config.deck,
            stake=config.stake,
            seed=config.seed,
        )

    def run(self) -> int:
        """Run the bot loop and return an exit code."""
        steps = 0
        try:
            state = self._client.gamestate()
            while steps < self._config.max_steps and state.get("state") != "GAME_OVER":
                actions = self._policy.next_actions(state)
                state, steps = self._execute_actions_with_fallback(state, actions, steps)
            return self._exit_code(state, steps)
        finally:
            self._client.close()

    def _execute_actions_with_fallback(
        self,
        state: Mapping[str, Any],
        actions: list[Action],
        steps: int,
    ) -> tuple[GameState, int]:
        current_state: GameState = dict(state)
        for action in actions:
            if steps >= self._config.max_steps:
                break
            try:
                self._log_action(current_state, action)
                current_state = self._dispatch_action(action)
                steps += 1
            except BalatroRPCError as exc:
                self._logger.warning("Action failed: %s. Applying fallback.", exc)
                refreshed = self._client.gamestate()
                fallback_actions = self._policy.fallback_actions(refreshed)
                return self._execute_actions(refreshed, fallback_actions, steps)
        return current_state, steps

    def _execute_actions(
        self,
        state: Mapping[str, Any],
        actions: list[Action],
        steps: int,
    ) -> tuple[GameState, int]:
        current_state: GameState = dict(state)
        for action in actions:
            if steps >= self._config.max_steps:
                break
            self._log_action(current_state, action)
            current_state = self._dispatch_action(action)
            steps += 1
        return current_state, steps

    def _dispatch_action(self, action: Action) -> GameState:
        params = action.params or {}
        if action.method == "menu":
            return self._client.menu()
        if action.method == "start":
            return self._client.start(
                deck=self._require_param(params, "deck"),
                stake=self._require_param(params, "stake"),
                seed=params.get("seed"),
            )
        if action.method == "select":
            return self._client.select()
        if action.method == "play":
            return self._client.play(cards=self._require_list(params, "cards"))
        if action.method == "cash_out":
            return self._client.cash_out()
        if action.method == "next_round":
            return self._client.next_round()
        if action.method == "pack":
            return self._client.pack(
                card=params.get("card"),
                targets=params.get("targets"),
                skip=params.get("skip"),
            )
        if action.method == "gamestate":
            return self._client.gamestate()
        raise BalatroRPCError(
            code=-32601,
            message="Method not found",
            data={"method": action.method},
            method=action.method,
            params=params,
        )

    def _require_param(self, params: Mapping[str, Any], key: str) -> Any:
        if key not in params:
            raise BalatroRPCError(
                code=-32602,
                message="Invalid params",
                data={"reason": f"Missing {key}"},
                method=None,
                params=params,
            )
        return params[key]

    def _require_list(self, params: Mapping[str, Any], key: str) -> list[int]:
        value = self._require_param(params, key)
        if not isinstance(value, list):
            raise BalatroRPCError(
                code=-32602,
                message="Invalid params",
                data={"reason": f"{key} must be a list"},
                method=None,
                params=params,
            )
        return value

    def _log_action(self, state: Mapping[str, Any], action: Action) -> None:
        self._logger.info(
            "State=%s ante=%s round=%s money=%s action=%s params=%s",
            state.get("state"),
            state.get("ante_num"),
            state.get("round_num"),
            state.get("money"),
            action.method,
            action.params,
        )

    def _exit_code(self, state: Mapping[str, Any], steps: int) -> int:
        if state.get("state") == "GAME_OVER":
            return 0 if state.get("won") else 1
        self._logger.warning(
            "Stopped after max steps (%s) without GAME_OVER.",
            steps,
        )
        return 2
