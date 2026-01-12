from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from typing import Any

from balatro_ai.actions import Action
from balatro_ai.build_intent import BuildIntent
from balatro_ai.cards import card_key, card_rank, card_suit, card_text
from balatro_ai.gs import (
    gs_ante,
    gs_deck_cards,
    gs_jokers,
    gs_money,
    gs_round_num,
    gs_state,
)
from balatro_ai.intent_manager import IntentManager
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


_INTENT_RESET_STATES = {"MENU", "GAME_OVER"}
_INTENT_REEVAL_ENTER_STATES = {"BLIND_SELECT", "SHOP"}


class Policy:
    """Policy that mirrors the temporary baseline behavior."""

    def __init__(self) -> None:
        self._intent_manager = IntentManager()
        self._transitions = TransitionManager()
        self._menu = MenuDecider()
        self._blind_select = BlindSelectDecider()
        self._hand_selector = HandSelector()
        self._round_eval = RoundEvalDecider()
        self._shop_advisor = ShopAdvisor()
        self._pack_choice = PackChoiceDecider()
        self._default = DefaultDecider()
        self._dispatch: dict[
            str, Callable[[Mapping[str, Any], PolicyContext, DecisionFrame], Action]
        ] = {
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
        frame = DecisionFrame(
            state=state, last_state=last_state, entering=state != last_state
        )
        self._transitions.before_decide(frame, ctx)
        self._maybe_update_intent(gs, ctx, frame)
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

    def _make_frame(self, gs: Mapping[str, Any], ctx: PolicyContext) -> DecisionFrame:
        state = gs_state(gs)
        last_state = ctx.run_memory.get("last_state")
        return DecisionFrame(
            state=state, last_state=last_state, entering=state != last_state
        )

    def _maybe_update_intent(
        self, gs: Mapping[str, Any], ctx: PolicyContext, frame: DecisionFrame
    ) -> None:
        if frame.entering and frame.state in _INTENT_RESET_STATES:
            for key in (
                "intent",
                "intent_scores",
                "intent_raw_values",
                "intent_baseline_values",
                "intent_confidence",
                "intent_probabilities",
                "intent_eval_key",
                "intent_signature",
                "intent_last_round_num",
                "intent_last_ante_num",
            ):
                ctx.run_memory.pop(key, None)
            return

        deck_cards = gs_deck_cards(gs)
        signature = _intent_signature(deck_cards, gs_jokers(gs))
        round_num = gs_round_num(gs)
        ante_num = gs_ante(gs)

        last_round = ctx.run_memory.get("intent_last_round_num")
        last_ante = ctx.run_memory.get("intent_last_ante_num")
        last_signature = ctx.run_memory.get("intent_signature")

        reason: str | None = None
        if ctx.run_memory.get("intent") is None:
            reason = "init"
        if last_round != round_num or last_ante != ante_num:
            reason = "round"
        elif frame.entering and frame.state in _INTENT_REEVAL_ENTER_STATES:
            reason = f"enter:{frame.state}"
        if last_signature is not None and last_signature != signature:
            reason = reason or "deck_or_jokers"

        if reason is None:
            return

        eval_key = (ante_num, round_num, frame.state, signature)
        if ctx.run_memory.get("intent_eval_key") == eval_key:
            return

        current_intent = _coerce_intent(ctx.run_memory.get("intent"))
        evaluation = self._intent_manager.evaluate(gs, deck_cards)
        probabilities = self._intent_manager.estimate_intent_probabilities(
            gs, deck_cards
        )

        ctx.run_memory["intent_last_round_num"] = round_num
        ctx.run_memory["intent_last_ante_num"] = ante_num
        ctx.run_memory["intent_signature"] = signature
        ctx.run_memory["intent_eval_key"] = eval_key
        ctx.run_memory["intent_scores"] = {
            intent.value: score for intent, score in evaluation.scores.items()
        }
        ctx.run_memory["intent_raw_values"] = {
            intent.value: value for intent, value in evaluation.raw_values.items()
        }
        ctx.run_memory["intent_baseline_values"] = {
            intent.value: value for intent, value in evaluation.baseline_values.items()
        }
        ctx.run_memory["intent_confidence"] = evaluation.confidence
        ctx.run_memory["intent_probabilities"] = {
            intent.value: prob for intent, prob in probabilities.items()
        }

        if current_intent is None:
            ctx.run_memory["intent"] = evaluation.intent
            logger.info(
                "Intent %s (conf=%.2f reason=%s)",
                evaluation.intent.value,
                evaluation.confidence,
                reason,
            )
            return

        if self._intent_manager.should_switch(
            current=current_intent, evaluation=evaluation
        ):
            from_score = evaluation.scores.get(current_intent, 0.0)
            to_score = evaluation.scores.get(evaluation.intent, 0.0)
            ctx.run_memory["intent"] = evaluation.intent
            logger.info(
                "Switching intent from %s to %s (%.3f -> %.3f conf=%.2f reason=%s)",
                current_intent.value,
                evaluation.intent.value,
                from_score,
                to_score,
                evaluation.confidence,
                reason,
            )

    def decide_in_menu(
        self,
        gs: Mapping[str, Any],
        ctx: PolicyContext,
        frame: DecisionFrame | None = None,
    ) -> Action:
        if frame is None:
            frame = self._make_frame(gs, ctx)
        return self._menu.decide(gs, ctx, frame)

    def decide_in_blind_select(
        self,
        gs: Mapping[str, Any],
        ctx: PolicyContext,
        frame: DecisionFrame | None = None,
    ) -> Action:
        if frame is None:
            frame = self._make_frame(gs, ctx)
        return self._blind_select.decide(gs, ctx, frame)

    def decide_in_selecting_hand(
        self,
        gs: Mapping[str, Any],
        ctx: PolicyContext,
        frame: DecisionFrame | None = None,
    ) -> Action:
        if frame is None:
            frame = self._make_frame(gs, ctx)
        return self._hand_selector.decide(gs, ctx, frame)

    def decide_in_round_eval(
        self,
        gs: Mapping[str, Any],
        ctx: PolicyContext,
        frame: DecisionFrame | None = None,
    ) -> Action:
        if frame is None:
            frame = self._make_frame(gs, ctx)
        return self._round_eval.decide(gs, ctx, frame)

    def decide_in_shop(
        self,
        gs: Mapping[str, Any],
        ctx: PolicyContext,
        frame: DecisionFrame | None = None,
    ) -> Action:
        if frame is None:
            frame = self._make_frame(gs, ctx)
        return self._shop_advisor.decide(gs, ctx, frame)

    def decide_in_pack_choice(
        self,
        gs: Mapping[str, Any],
        ctx: PolicyContext,
        frame: DecisionFrame | None = None,
    ) -> Action:
        if frame is None:
            frame = self._make_frame(gs, ctx)
        return self._pack_choice.decide(gs, ctx, frame)

    def decide_in_default(
        self,
        gs: Mapping[str, Any],
        ctx: PolicyContext,
        frame: DecisionFrame | None = None,
    ) -> Action:
        if frame is None:
            frame = self._make_frame(gs, ctx)
        return self._default.decide(gs, ctx, frame)


def _coerce_intent(value: Any) -> BuildIntent | None:
    if isinstance(value, BuildIntent):
        return value
    if isinstance(value, str):
        try:
            return BuildIntent[value.upper()]
        except KeyError:
            return None
    return None


def _intent_signature(deck_cards: list[dict], jokers: list[dict]) -> tuple:
    deck_counts: dict[tuple[int, str | None], int] = {}
    for card in deck_cards:
        rank = card_rank(card)
        suit = card_suit(card)
        if rank <= 0 or suit is None:
            continue
        key = (rank, suit)
        deck_counts[key] = deck_counts.get(key, 0) + 1

    joker_keys: list[str] = []
    for joker in jokers:
        key = card_key(joker)
        if key:
            joker_keys.append(key.lower())
        else:
            text = card_text(joker)
            if text:
                joker_keys.append(text.lower())
    joker_keys.sort()

    deck_tuple = tuple(
        sorted((rank, suit, count) for (rank, suit), count in deck_counts.items())
    )
    return (deck_tuple, tuple(joker_keys))
