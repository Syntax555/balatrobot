from __future__ import annotations

import logging
from typing import Any, Mapping

from balatro_ai.actions import Action
from balatro_ai.config import Config
from balatro_ai.gs import (
    gs_ante,
    gs_hand_cards,
    gs_money,
    gs_round_num,
    gs_state,
    gs_won,
)
from balatro_ai.policy import Policy, PolicyContext
from balatro_ai.rpc import BalatroRPC, BalatroRPCError

GameState = dict[str, Any]


class BotRunner:
    """Runs a BalatroBot loop until game over or step limit."""

    def __init__(self, config: Config, base_url: str) -> None:
        self._config = config
        self._logger = logging.getLogger("balatro_ai")
        self._client = BalatroRPC(
            base_url=base_url,
            timeout=config.timeout,
        )
        self._policy = Policy()
        self._context = PolicyContext(
            config=config,
            run_memory={},
            round_memory={},
        )

    def run(self) -> int:
        """Run the bot loop and return an exit code."""
        steps = 0
        try:
            state = self._client.gamestate()
            self._sync_round_context(state)
            while steps < self._config.max_steps and gs_state(state) != "GAME_OVER":
                state, steps = self._step(state, steps)
            return self._exit_code(state, steps)
        finally:
            self._client.close()

    def _step(self, state: Mapping[str, Any], steps: int) -> tuple[GameState, int]:
        if steps >= self._config.max_steps:
            return dict(state), steps
        action = self._policy.decide(state, self._context)
        try:
            new_state = self.execute_action(action, state)
            steps += 1
        except BalatroRPCError as exc:
            error_name = self._error_name(exc)
            if error_name == "INVALID_STATE":
                self._logger.warning("Invalid state. Refreshing and retrying decision.")
                refreshed = self._client.gamestate()
                self._sync_round_context(refreshed)
                action = self._policy.decide(refreshed, self._context)
                if steps >= self._config.max_steps:
                    return dict(refreshed), steps
                new_state = self.execute_action(action, refreshed)
                steps += 1
            elif error_name == "NOT_ALLOWED":
                self._logger.warning("Action not allowed. Falling back to safe action.")
                fallback = self._safe_action(state)
                if steps >= self._config.max_steps:
                    return dict(state), steps
                new_state = self.execute_action(fallback, state)
                steps += 1
            else:
                raise
        self._sync_round_context(new_state)
        return dict(new_state), steps

    def execute_action(self, action: Action, gs: Mapping[str, Any]) -> GameState:
        """Execute a single action and return the new game state."""
        self._log_action(gs, action)
        return self._dispatch_action(action)

    def _dispatch_action(self, action: Action) -> GameState:
        params = action.params
        if action.kind == "menu":
            return self._client.menu()
        if action.kind == "start":
            return self._client.start(
                deck=self._require_param(params, "deck"),
                stake=self._require_param(params, "stake"),
                seed=params.get("seed"),
            )
        if action.kind == "select":
            return self._client.select()
        if action.kind == "skip":
            return self._client.skip()
        if action.kind == "play":
            return self._client.play(cards=self._require_list(params, "cards"))
        if action.kind == "discard":
            return self._client.discard(cards=self._require_list(params, "cards"))
        if action.kind == "cash_out":
            return self._client.cash_out()
        if action.kind == "next_round":
            return self._client.next_round()
        if action.kind == "reroll":
            return self._client.reroll()
        if action.kind == "buy":
            return self._client.buy(
                card=params.get("card"),
                voucher=params.get("voucher"),
                pack=params.get("pack"),
            )
        if action.kind == "sell":
            return self._client.sell(
                joker=params.get("joker"),
                consumable=params.get("consumable"),
            )
        if action.kind == "pack":
            return self._client.pack(
                card=params.get("card"),
                targets=params.get("targets"),
                skip=params.get("skip"),
            )
        if action.kind == "rearrange":
            return self._client.rearrange(
                hand=params.get("hand"),
                jokers=params.get("jokers"),
                consumables=params.get("consumables"),
            )
        if action.kind == "use":
            return self._client.use(
                consumable=self._require_param(params, "consumable"),
                cards=params.get("cards"),
            )
        if action.kind == "save":
            return self._client.save(path=self._require_param(params, "path"))
        if action.kind == "load":
            return self._client.load(path=self._require_param(params, "path"))
        if action.kind == "gamestate":
            return self._client.gamestate()
        raise BalatroRPCError(
            code=-32601,
            message="Method not found",
            data={"method": action.kind},
            method=action.kind,
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

    def _error_name(self, exc: BalatroRPCError) -> str | None:
        data = exc.data or {}
        if isinstance(data, Mapping):
            name = data.get("name")
            return str(name) if name is not None else None
        return None

    def _safe_action(self, gs: Mapping[str, Any]) -> Action:
        state = gs_state(gs)
        if state == "MENU":
            return Action(kind="menu", params={})
        if state == "BLIND_SELECT":
            return Action(kind="select", params={})
        if state == "SELECTING_HAND":
            cards = gs_hand_cards(gs)
            count = min(5, len(cards))
            if count == 0:
                return Action(kind="gamestate", params={})
            indices = list(range(count))
            return Action(kind="play", params={"cards": indices})
        if state == "ROUND_EVAL":
            return Action(kind="cash_out", params={})
        if state == "SHOP":
            return Action(kind="next_round", params={})
        if state == "SMODS_BOOSTER_OPENED":
            return Action(kind="pack", params={"card": 0})
        return Action(kind="gamestate", params={})

    def _sync_round_context(self, gs: Mapping[str, Any]) -> None:
        round_num = gs_round_num(gs)
        last_round = self._context.run_memory.get("round_num")
        if last_round != round_num:
            self._context.round_memory.clear()
            self._context.run_memory["round_num"] = round_num

    def _log_action(self, state: Mapping[str, Any], action: Action) -> None:
        self._logger.info(
            "Action",
            extra={
                "state": gs_state(state),
                "ante": gs_ante(state),
                "round": gs_round_num(state),
                "money": gs_money(state),
                "action_kind": action.kind,
            },
        )

    def _exit_code(self, state: Mapping[str, Any], steps: int) -> int:
        if gs_state(state) == "GAME_OVER":
            return 0 if gs_won(state) else 1
        self._logger.warning(
            "Stopped after max steps (%s) without GAME_OVER.",
            steps,
        )
        return 2
