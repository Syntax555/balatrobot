from __future__ import annotations

import logging
import re
from collections.abc import Iterable, Mapping
from typing import Any

from balatro_ai.actions import Action
from balatro_ai.build_intent import BuildIntent
from balatro_ai.cards import card_suit, card_tokens
from balatro_ai.gs import gs_deck_cards
from balatro_ai.policy_context import DecisionFrame, PolicyContext

logger = logging.getLogger(__name__)


class BlindSelectDecider:
    def decide(self, gs: Mapping[str, Any], ctx: PolicyContext, frame: DecisionFrame) -> Action:
        options = _extract_boss_blind_options(gs)
        if len(options) >= 2:
            intent = _coerce_intent(ctx.run_memory.get("intent"))
            primary_suit = _primary_flush_suit(gs_deck_cards(gs)) if intent == BuildIntent.FLUSH else None
            scored: list[tuple[float, int, dict[str, Any]]] = []
            for index, option in enumerate(options):
                score = _boss_blind_pain_score(option, intent=intent, primary_flush_suit=primary_suit)
                scored.append((score, index, option))
            scored.sort(key=lambda item: (item[0], item[1]))
            best_score, best_index, best_option = scored[0]
            best_name = _blind_option_name(best_option) or "<unknown>"
            logger.info(
                "BlindSelectDecider: choosing boss option index=%s name=%s pain=%.2f (intent=%s primary_suit=%s)",
                best_index,
                best_name,
                best_score,
                intent.value if intent else None,
                primary_suit,
            )
            ctx.run_memory["boss_blind_choice"] = {
                "index": best_index,
                "name": best_name,
                "pain": best_score,
                "intent": intent.value if intent else None,
                "primary_suit": primary_suit,
            }
            return Action(
                kind="select",
                params={
                    "boss_option": best_index,
                    "boss_name": best_name,
                },
            )

        logger.debug("BlindSelectDecider: -> select")
        return Action(kind="select", params={})


def _extract_boss_blind_options(gs: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Return boss-blind option dictionaries when the gamestate exposes multiple choices.

    The vanilla Balatro blind screen has a single Boss blind, but some mods expose multiple
    boss options. Since the exact shape is mod-dependent, we try a few common locations and
    accept any list of mappings.
    """

    candidates: list[Any] = []
    for key in ("boss_options", "blind_options", "boss_blinds", "blind_choices"):
        candidates.append(gs.get(key))

    blinds = gs.get("blinds")
    if isinstance(blinds, Mapping):
        boss = blinds.get("boss")
        if isinstance(boss, Mapping):
            candidates.append(boss.get("options"))
            candidates.append(boss.get("choices"))

    for value in candidates:
        options = _as_list_of_dicts(value)
        if options:
            return options
    return []


def _as_list_of_dicts(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    out: list[dict[str, Any]] = []
    for item in value:
        if isinstance(item, Mapping):
            out.append(dict(item))
    return out


def _coerce_intent(value: Any) -> BuildIntent | None:
    if isinstance(value, BuildIntent):
        return value
    if isinstance(value, str):
        try:
            return BuildIntent[value.upper()]
        except KeyError:
            return None
    return None


def _primary_flush_suit(deck_cards: Iterable[Mapping[str, Any]]) -> str | None:
    counts: dict[str, int] = {}
    for card in deck_cards:
        suit = card_suit(card)
        if not suit:
            continue
        counts[suit] = counts.get(suit, 0) + 1
    if not counts:
        return None
    return max(counts.items(), key=lambda item: item[1])[0]


_BOSS_BASE_PAIN_BY_NAME: dict[str, float] = {
    # Suit debuffs tend to be more manageable unless we're committed to a flush.
    "the head": 4.0,
    "the club": 4.0,
    "the goad": 4.0,
    "the window": 4.0,
    # Known generally harsh bosses.
    "the wall": 9.0,
    "the needle": 8.0,
    "the manacle": 7.0,
    "the water": 7.0,
}


_SUIT_TOKENS = {"hearts", "diamonds", "clubs", "spades"}


def _boss_blind_pain_score(
    option: Mapping[str, Any],
    *,
    intent: BuildIntent | None,
    primary_flush_suit: str | None,
) -> float:
    """Return a heuristic pain score (lower is better)."""

    name = (_blind_option_name(option) or "").strip().lower()
    effect = (_blind_option_effect(option) or "").strip().lower()

    score = _BOSS_BASE_PAIN_BY_NAME.get(name, 6.0)

    tokens = card_tokens(effect) | card_tokens(name)
    suits_mentioned = _SUIT_TOKENS.intersection(tokens)
    if suits_mentioned:
        flush_bonus = 0.0
        if intent == BuildIntent.FLUSH and primary_flush_suit:
            # If a boss targets our primary suit, treat it as substantially worse.
            if primary_flush_suit in suits_mentioned:
                flush_bonus += 10.0
            else:
                flush_bonus += 2.0
        else:
            flush_bonus += 1.0
        score += flush_bonus

    if "debuff" in tokens or "debuffed" in tokens or "disabled" in tokens:
        score += 2.0

    # Hand-type specific blockers.
    if intent == BuildIntent.FLUSH and "flush" in tokens:
        score += 6.0
    if intent == BuildIntent.STRAIGHT and "straight" in tokens:
        score += 6.0
    if intent == BuildIntent.PAIRS and ("pair" in tokens or "pairs" in tokens or "kind" in tokens):
        score += 4.0
    if intent == BuildIntent.HIGH_CARD and ("high" in tokens and "card" in tokens):
        score += 4.0

    # Try to catch "1 hand" style effects.
    if _matches_single_hand(effect):
        score += 8.0

    # Prefer weaker penalties if we can't parse anything meaningful.
    return float(score)


_ONE_HAND_RE = re.compile(r"\b(1|one)\s+hand(s)?\b")


def _matches_single_hand(effect_text: str) -> bool:
    return bool(_ONE_HAND_RE.search(effect_text))


def _blind_option_name(option: Mapping[str, Any]) -> str | None:
    for key in ("name", "blind_name", "title"):
        value = option.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return None


def _blind_option_effect(option: Mapping[str, Any]) -> str | None:
    for key in ("effect", "description", "desc", "text"):
        value = option.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return None

