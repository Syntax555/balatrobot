from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from balatro_ai.actions import Action
from balatro_ai.config import Config
from balatro_ai.decision_log import DecisionLogger
from balatro_ai.determinism import determinism_probe
from balatro_ai.gs import (
    gs_ante,
    gs_hand_cards,
    gs_money,
    gs_round_num,
    gs_seed,
    gs_state,
    gs_won,
)
from balatro_ai.intent_utils import ctx_intent_text
from balatro_ai.pacing import BackoffPacer
from balatro_ai.pack_rollout import pack_rollout_step
from balatro_ai.policy import Policy, PolicyContext
from balatro_ai.rollout import rollout_step
from balatro_ai.rpc import BalatroRPC, BalatroRPCError
from balatro_ai.shop_rollout import shop_rollout_step

GameState = dict[str, Any]

_IDLE_STATES = {"MENU", "GAME_OVER"}
_KNOWN_STATES = {
    "MENU",
    "BLIND_SELECT",
    "SELECTING_HAND",
    "ROUND_EVAL",
    "SHOP",
    "SMODS_BOOSTER_OPENED",
    "GAME_OVER",
}
_PACE_RESET = "reset"
_PACE_BUMP = "bump"
_PACE_BUMP_HARD = "bump_hard"
_HARD_BACKOFF_FACTOR = 2.5
_RETRYABLE_RPC_CODES = {-32098, -32097, -32000}


class BotRunner:
    """Runs a BalatroBot loop with adaptive pacing."""

    def __init__(self, config: Config, base_url: str) -> None:
        self._config = config
        self._logger = logging.getLogger("balatro_ai")
        self._client = BalatroRPC(
            base_url=base_url,
            timeout=config.timeout,
        )
        self._decision_logger = DecisionLogger.from_config(
            path=config.decision_log_path,
            include_state=config.decision_log_include_state,
        )
        self._policy = Policy()
        self._context = PolicyContext(
            config=config,
            run_memory={},
            round_memory={},
        )
        self._pacer = BackoffPacer(
            min_delay=0.1,
            max_delay=2.0,
            factor=1.5,
            jitter=0.05,
        )
        self._rollouts_checked = False
        self._rollouts_allowed = True
        self._rollouts_disabled_reason: str | None = None
        self._rollouts_checked_kinds: set[str] = set()

    def run(self) -> int:
        """Run the bot loop indefinitely."""
        steps = 0
        limit_logged = False
        menu_paused_logged = False
        try:
            state = self._fetch_gamestate_forever()
            self._sync_round_context(state)
            while True:
                state_name = gs_state(state)
                if (
                    state_name == "MENU"
                    and self._config.pause_at_menu
                    and not self._config.auto_start
                ):
                    if not menu_paused_logged:
                        self._logger.info(
                            "At MENU with pause_at_menu=True. Pausing actions until MENU changes "
                            "(use --auto-start to start automatically, or --no-pause-at-menu to act immediately).",
                        )
                        menu_paused_logged = True
                    state, changed, idle_pace = self._idle_tick_safe(state)
                    self._apply_pace(idle_pace if not changed else _PACE_RESET)
                    continue
                menu_paused_logged = False
                if state_name in _IDLE_STATES or steps >= self._config.max_steps:
                    if steps >= self._config.max_steps and not limit_logged:
                        self._logger.warning(
                            "Reached max steps (%s). Pausing actions.",
                            steps,
                        )
                        limit_logged = True
                    state, changed, idle_pace = self._idle_tick_safe(state)
                    self._apply_pace(idle_pace if not changed else _PACE_RESET)
                    continue
                limit_logged = False
                try:
                    state, steps, pace = self._step(state, steps)
                    self._apply_pace(pace)
                except BalatroRPCError as exc:
                    if not self._is_retryable_rpc_error(exc):
                        raise
                    self._log_rpc_error(state, exc)
                    self._logger.warning(
                        "RPC error during run loop. Backing off and retrying.",
                    )
                    self._apply_pace(_PACE_BUMP_HARD)
                    state = self._fetch_gamestate_forever()
            return 0
        finally:
            self.close()

    def close(self) -> None:
        if self._decision_logger is not None:
            self._decision_logger.close()
            self._decision_logger = None
        self._client.close()

    def run_one(
        self,
        *,
        deck: str | None = None,
        stake: str | None = None,
        seed: str | None = None,
        max_steps: int | None = None,
    ) -> tuple[int, GameState, int]:
        """Run a single seeded game and stop at GAME_OVER or max_steps.

        Returns: (exit_code, final_gamestate, steps_executed)
        """
        self._context.run_memory.clear()
        self._context.round_memory.clear()

        state = self._client.menu()
        state = self._client.start(
            deck=deck or self._config.deck,
            stake=stake or self._config.stake,
            seed=seed,
        )
        if self._decision_logger is not None:
            self._decision_logger.begin_run(
                seed=gs_seed(state) or seed,
                deck=deck or self._config.deck,
                stake=stake or self._config.stake,
            )
        self._sync_round_context(state)

        steps = 0
        limit = (
            max_steps
            if isinstance(max_steps, int) and max_steps > 0
            else self._config.max_steps
        )
        while steps < limit and gs_state(state) != "GAME_OVER":
            state, steps, pace = self._step(state, steps)
            self._apply_pace(pace)
        if self._decision_logger is not None:
            self._decision_logger.end_run(final_state=dict(state))
        return self._exit_code(state, steps), dict(state), steps

    def _fetch_gamestate_forever(self) -> GameState:
        """Fetch gamestate, retrying forever with adaptive backoff."""
        while True:
            try:
                gs = self._client.gamestate()
                self._pacer.reset()
                return dict(gs)
            except BalatroRPCError as exc:
                if not self._is_retryable_rpc_error(exc):
                    raise
                self._logger.warning(
                    "Failed to fetch gamestate (%s). Backing off and retrying.",
                    exc,
                )
                self._apply_pace(_PACE_BUMP_HARD)

    def _idle_tick_safe(self, state: Mapping[str, Any]) -> tuple[GameState, bool, str]:
        """Idle polling that backs off on transient RPC errors."""
        try:
            refreshed = self._client.gamestate()
            self._sync_round_context(refreshed)
            changed = gs_state(refreshed) != gs_state(state)
            pace = _PACE_RESET if changed else _PACE_BUMP
            return dict(refreshed), changed, pace
        except BalatroRPCError as exc:
            if not self._is_retryable_rpc_error(exc):
                raise
            self._log_rpc_error(state, exc)
            return dict(state), False, _PACE_BUMP_HARD

    def _apply_pace(self, pace: str) -> None:
        if pace == _PACE_RESET:
            self._pacer.reset()
        elif pace == _PACE_BUMP:
            self._pacer.bump()
        elif pace == _PACE_BUMP_HARD:
            self._pacer.bump(factor=_HARD_BACKOFF_FACTOR)
        else:
            self._pacer.reset()
        self._pacer.sleep()

    def _step(self, state: Mapping[str, Any], steps: int) -> tuple[GameState, int, str]:
        state_name = gs_state(state)
        if not isinstance(state_name, str) or state_name not in _KNOWN_STATES:
            self._logger.warning(
                "Unknown game state %s. Polling gamestate until it stabilizes.",
                state_name or "UNKNOWN",
                extra={
                    "state": state_name,
                    "ante": gs_ante(state),
                    "round": gs_round_num(state),
                    "money": gs_money(state),
                    "action_kind": "unknown_state",
                },
            )
            refreshed = self._fetch_gamestate_forever()
            self._sync_round_context(refreshed)
            return dict(refreshed), steps, _PACE_BUMP_HARD

        decision_step = steps
        try:
            action = self._policy.decide(state, self._context)
        except Exception as exc:
            if self._decision_logger is not None:
                self._decision_logger.log_error(
                    step=decision_step, gs=state, action=None, error=exc
                )
            self._logger.warning(
                "Policy error. Falling back to gamestate.",
                exc_info=True,
                extra={
                    "state": state_name,
                    "ante": gs_ante(state),
                    "round": gs_round_num(state),
                    "money": gs_money(state),
                    "action_kind": "policy_error",
                },
            )
            action = Action(kind="gamestate", params={})
        action = self._ensure_legal_action(action, state)
        if self._decision_logger is not None:
            self._decision_logger.log_decision(
                step=decision_step,
                gs=state,
                action=action,
                run_memory=self._context.run_memory,
                round_memory=self._context.round_memory,
            )
        try:
            new_state = self.execute_action(action, state)
            if action.kind != "gamestate":
                steps += 1
            if self._decision_logger is not None:
                self._decision_logger.log_result(
                    step=decision_step,
                    before=state,
                    action=action,
                    after=new_state,
                    run_memory=self._context.run_memory,
                    round_memory=self._context.round_memory,
                )
        except BalatroRPCError as exc:
            if self._decision_logger is not None:
                self._decision_logger.log_error(
                    step=decision_step, gs=state, action=action, error=exc
                )
            self._log_rpc_error(state, exc)
            error_name = self._error_name(exc)
            if error_name in {"INVALID_STATE", "NOT_ALLOWED"}:
                self._logger.warning(
                    "RPC %s. Backing off before retrying.",
                    error_name or "UNKNOWN",
                )
                refreshed = self._client.gamestate()
                self._sync_round_context(refreshed)
                return dict(refreshed), steps, _PACE_BUMP_HARD
            raise
        except Exception as exc:
            if self._decision_logger is not None:
                self._decision_logger.log_error(
                    step=decision_step, gs=state, action=action, error=exc
                )
            self._logger.warning(
                "Unexpected error executing action=%s params=%s. Falling back to gamestate.",
                action.kind,
                action.params,
                exc_info=True,
                extra={
                    "state": state_name,
                    "ante": gs_ante(state),
                    "round": gs_round_num(state),
                    "money": gs_money(state),
                    "action_kind": "execute_error",
                },
            )
            refreshed = self._fetch_gamestate_forever()
            self._sync_round_context(refreshed)
            return dict(refreshed), steps, _PACE_BUMP_HARD
        self._sync_round_context(new_state)
        pace = _PACE_RESET if gs_state(new_state) != gs_state(state) else _PACE_BUMP
        return dict(new_state), steps, pace

    def execute_action(self, action: Action, gs: Mapping[str, Any]) -> GameState:
        """Execute a single action and return the new game state."""
        self._log_action(gs, action)
        return self._dispatch_action(action, gs)

    def _dispatch_action(self, action: Action, gs: Mapping[str, Any]) -> GameState:
        params = action.params
        if action.kind == "menu":
            return self._client.menu()
        if action.kind == "start":
            state = self._client.start(
                deck=self._require_param(params, "deck"),
                stake=self._require_param(params, "stake"),
                seed=params.get("seed"),
            )
            self._rollouts_checked = False
            self._rollouts_allowed = True
            self._rollouts_disabled_reason = None
            self._rollouts_checked_kinds.clear()
            if self._decision_logger is not None:
                self._decision_logger.begin_run(
                    seed=gs_seed(state) or params.get("seed"),
                    deck=params.get("deck"),
                    stake=params.get("stake"),
                )
            return state
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
        if action.kind == "rollout":
            if not self._rollouts_safe(gs, kind="hand"):
                fallback = self._fallback_not_allowed(gs)
                if fallback.kind == "gamestate":
                    return self._client.gamestate()
                return self._dispatch_action(fallback, gs)
            try:
                return rollout_step(gs, self._config, self._context, self._client)
            except Exception:
                self._logger.warning(
                    "rollout_step failed. Falling back to safe action.",
                    exc_info=True,
                    extra={
                        "state": gs_state(gs),
                        "ante": gs_ante(gs),
                        "round": gs_round_num(gs),
                        "money": gs_money(gs),
                        "action_kind": "rollout_error",
                    },
                )
                fallback = self._fallback_not_allowed(gs)
                if fallback.kind == "gamestate":
                    return self._client.gamestate()
                return self._dispatch_action(fallback, gs)
        if action.kind == "shop_rollout":
            if not self._rollouts_safe(gs, kind="shop"):
                from balatro_ai.shop_policy import ShopPolicy

                action = ShopPolicy().choose_action(gs, self._config, self._context)
                return self._dispatch_action(action, gs)
            try:
                return shop_rollout_step(gs, self._config, self._context, self._client)
            except Exception:
                self._logger.warning(
                    "shop_rollout_step failed. Falling back to SHOP policy.",
                    exc_info=True,
                    extra={
                        "state": gs_state(gs),
                        "ante": gs_ante(gs),
                        "round": gs_round_num(gs),
                        "money": gs_money(gs),
                        "action_kind": "shop_rollout_error",
                    },
                )
                from balatro_ai.shop_policy import ShopPolicy

                action = ShopPolicy().choose_action(gs, self._config, self._context)
                return self._dispatch_action(action, gs)
        if action.kind == "pack_rollout":
            if not self._rollouts_safe(gs, kind="pack"):
                from balatro_ai.pack_policy import PackPolicy

                action = PackPolicy().choose_action(
                    gs,
                    self._config,
                    self._context,
                    ctx_intent_text(self._context) or "",
                )
                return self._dispatch_action(action, gs)
            try:
                return pack_rollout_step(gs, self._config, self._context, self._client)
            except Exception:
                self._logger.warning(
                    "pack_rollout_step failed. Falling back to pack policy.",
                    exc_info=True,
                    extra={
                        "state": gs_state(gs),
                        "ante": gs_ante(gs),
                        "round": gs_round_num(gs),
                        "money": gs_money(gs),
                        "action_kind": "pack_rollout_error",
                    },
                )
                from balatro_ai.pack_policy import PackPolicy

                action = PackPolicy().choose_action(
                    gs,
                    self._config,
                    self._context,
                    ctx_intent_text(self._context) or "",
                )
                return self._dispatch_action(action, gs)
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

    def _is_retryable_rpc_error(self, exc: BalatroRPCError) -> bool:
        return exc.code in _RETRYABLE_RPC_CODES

    def _fallback_not_allowed(self, gs: Mapping[str, Any]) -> Action:
        state = gs_state(gs)
        if state == "MENU":
            return Action(kind="gamestate", params={})
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
            return Action(kind="pack", params={"skip": True})
        return Action(kind="gamestate", params={})

    def _ensure_legal_action(self, action: Action, gs: Mapping[str, Any]) -> Action:
        state = gs_state(gs)
        if self._is_action_legal(action, state):
            return action
        self._logger.warning(
            "Illegal action %s in state %s. Using gamestate.",
            action.kind,
            state or "UNKNOWN",
            extra={
                "state": state,
                "ante": gs_ante(gs),
                "round": gs_round_num(gs),
                "money": gs_money(gs),
                "action_kind": "illegal",
            },
        )
        return Action(kind="gamestate", params={})

    def _is_action_legal(self, action: Action, state: str) -> bool:
        if action.kind in {"menu", "start", "gamestate"}:
            return True
        required = _REQUIRED_STATES.get(action.kind)
        if required is not None:
            return state in required
        if action.kind == "rearrange":
            return self._rearrange_allowed(action, state)
        return False

    def _rearrange_allowed(self, action: Action, state: str) -> bool:
        params = action.params
        hand = params.get("hand")
        jokers = params.get("jokers")
        consumables = params.get("consumables")
        flags = [
            hand is not None,
            jokers is not None,
            consumables is not None,
        ]
        if sum(1 for flag in flags if flag) != 1:
            return False
        if hand is not None:
            return state in {"SELECTING_HAND", "SMODS_BOOSTER_OPENED"}
        return state in {"SHOP", "SELECTING_HAND", "SMODS_BOOSTER_OPENED"}

    def _sync_round_context(self, gs: Mapping[str, Any]) -> None:
        round_num = gs_round_num(gs)
        ante_num = gs_ante(gs)
        last_round = self._context.run_memory.get("round_num")
        last_ante = self._context.run_memory.get("ante_num")
        if last_round != round_num or last_ante != ante_num:
            self._context.round_memory.clear()
            self._context.run_memory["round_num"] = round_num
            self._context.run_memory["ante_num"] = ante_num
        # Intent is updated centrally by Policy.decide(), not here.

    def _rollouts_safe(self, gs: Mapping[str, Any], *, kind: str) -> bool:
        if not self._config.determinism_check:
            return True
        if not self._rollouts_allowed:
            return False
        if kind in self._rollouts_checked_kinds:
            return True
        try:
            ok, reason = determinism_probe(
                rpc=self._client,
                gs=dict(gs),
                kind=kind,
            )
        except Exception as exc:
            ok, reason = False, f"probe_error:{type(exc).__name__}"
        self._rollouts_checked = True
        if ok:
            self._rollouts_checked_kinds.add(kind)
            if not self._context.run_memory.get("rollouts_determinism_checked"):
                self._context.run_memory["rollouts_determinism_checked"] = True
                self._context.run_memory["rollouts_deterministic"] = True
                self._logger.info(
                    "Determinism probe passed; save/load rollouts enabled."
                )
            return True

        self._rollouts_allowed = False
        self._rollouts_disabled_reason = reason or "non_deterministic"
        self._context.run_memory["rollouts_determinism_checked"] = True
        self._context.run_memory["rollouts_deterministic"] = False
        self._context.run_memory["rollouts_disabled_reason"] = (
            self._rollouts_disabled_reason
        )
        self._logger.warning(
            "Disabling save/load rollouts due to non-deterministic behavior (%s).",
            self._rollouts_disabled_reason,
        )
        return False

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

    def _log_rpc_error(self, state: Mapping[str, Any], exc: BalatroRPCError) -> None:
        name = self._error_name(exc)
        self._logger.warning(
            "RPC error code=%s message=%s name=%s",
            exc.code,
            exc.message,
            name or "UNKNOWN",
            extra={
                "state": gs_state(state),
                "ante": gs_ante(state),
                "round": gs_round_num(state),
                "money": gs_money(state),
                "action_kind": "error",
            },
        )


_REQUIRED_STATES: dict[str, set[str]] = {
    "select": {"BLIND_SELECT"},
    "skip": {"BLIND_SELECT"},
    "play": {"SELECTING_HAND"},
    "discard": {"SELECTING_HAND"},
    "cash_out": {"ROUND_EVAL"},
    "buy": {"SHOP"},
    "sell": {"SHOP"},
    "reroll": {"SHOP"},
    "next_round": {"SHOP"},
    "pack": {"SMODS_BOOSTER_OPENED"},
    "rollout": {"SELECTING_HAND"},
    "shop_rollout": {"SHOP"},
    "pack_rollout": {"SMODS_BOOSTER_OPENED"},
}
