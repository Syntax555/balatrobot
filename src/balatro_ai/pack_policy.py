from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from balatro_ai.actions import Action
from balatro_ai.cards import card_key, card_rank, card_suit, card_text, card_tokens
from balatro_ai.config import Config
from balatro_ai.gs import gs_deck_cards, gs_hand_cards, gs_pack_cards, gs_seed, gs_state
from balatro_ai.hand_stats import majority_suit
from balatro_ai.joker_rules import joker_rule
from balatro_ai.pack_sim import evaluate_pack_choice
from balatro_ai.token_utils import has_x_token

if TYPE_CHECKING:
    from balatro_ai.policy_context import PolicyContext

logger = logging.getLogger(__name__)


_CHIPS_TOKENS = {"chips", "chip", "bonus"}
_MULT_TOKENS = {"mult", "multiplier", "if", "when", "each"}
_XMULT_TOKENS = {"xmult", "times"}
_TARGET_TOKENS = {"target", "targets"}
_TARGET_ACTION_TOKENS = {"enhance", "convert", "destroy", "copy"}
_TARGET_CARD_TOKENS = {"card", "cards", "hand"}

INDEX_INITIAL = 0
SCORE_INITIAL = 0
BEST_SCORE_INITIAL = -1

PICK_XMULT_BONUS = 100
PICK_MULT_BONUS = 50
PICK_CHIPS_BONUS = 20

INTENT_FLUSH_BONUS = 40
INTENT_STRAIGHT_BONUS = 40
INTENT_PAIR_BONUS = 30

TARGET_SUIT_BONUS = 5
MAX_TARGETS = 2
_TARGET_MAX_BY_KEY: dict[str, int] = {
    # Tarots that can target 3 cards.
    "c_sun": 3,
    "c_moon": 3,
    "c_star": 3,
    "c_world": 3,
}

CATEGORY_SCORE_XMULT = 100
CATEGORY_SCORE_MULT = 50
CATEGORY_SCORE_CHIPS = 20
CATEGORY_SCORE_ECON = 0
CATEGORY_SCORE_DEFAULT = 0

TARGET_COUNT_NONE = 0
LENGTH_NONE = 0

SLICE_AFTER_FIRST_CHAR = 1

PACK_SIM_SCORE_WEIGHT = 200.0


@dataclass(frozen=True)
class _TargetCandidate:
    index: int
    score: int


class PackPolicy:
    """Policy for selecting a pack card or skipping."""

    def choose_action(
        self,
        gs: Mapping[str, Any],
        cfg: Config,
        ctx: PolicyContext,
        intent: str,
    ) -> Action:
        """Choose an action in SMODS_BOOSTER_OPENED state."""
        if gs_state(gs) != "SMODS_BOOSTER_OPENED":
            raise ValueError(
                f"PackPolicy used outside SMODS_BOOSTER_OPENED: {gs_state(gs)}"
            )
        pack_cards = gs_pack_cards(gs)
        logger.debug("PackPolicy: intent=%r pack_cards=%s", intent, len(pack_cards))
        if not pack_cards:
            logger.debug("PackPolicy: no pack cards -> skip")
            return Action(kind="pack", params={"skip": True})
        index = pick_pack_card_with_simulation(gs, cfg, pack_cards, intent, ctx=ctx)
        card = pack_cards[index]
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(
                "PackPolicy: picked card idx=%s key=%s text=%r",
                index,
                card_key(card),
                pack_card_text(card),
            )
        if needs_targets(card):
            targets = choose_targets(gs, intent, max_targets=target_limit(card))
            if not targets:
                logger.debug("PackPolicy: card needs targets but none selected -> skip")
                return Action(kind="pack", params={"skip": True})
            logger.debug("PackPolicy: card needs targets -> targets=%s", targets)
            return Action(kind="pack", params={"card": index, "targets": targets})
        logger.debug("PackPolicy: select card idx=%s (no targets)", index)
        return Action(kind="pack", params={"card": index})


def pack_card_text(c: Mapping[str, Any]) -> str:
    """Return lowercase text for a pack card, preferring label then key."""
    if not isinstance(c, Mapping):
        return ""
    return card_text(c)


def pick_pack_card(pack_cards: list[dict], intent: str) -> int:
    """Pick a pack card index using simple heuristics."""
    best_index = INDEX_INITIAL
    best_score = BEST_SCORE_INITIAL
    intent_key = intent.lower() if isinstance(intent, str) else ""
    if logger.isEnabledFor(logging.DEBUG):
        logger.debug(
            "pick_pack_card: intent_key=%r cards=%s", intent_key, len(pack_cards)
        )
    for index, card in enumerate(pack_cards):
        score, debug = _heuristic_score_pack_card(card, intent_key)
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(
                "pick_pack_card option: idx=%s score=%s (cat=%s xmult=%s mult=%s chips=%s intent_bonus=%s) key=%s text=%r",
                index,
                score,
                debug["category_score"],
                debug["xmult_hit"],
                debug["mult_hit"],
                debug["chips_hit"],
                debug["intent_bonus"],
                debug["key"],
                debug["text"],
            )
        if score > best_score:
            best_score = score
            best_index = index
    logger.debug("pick_pack_card: best_idx=%s best_score=%s", best_index, best_score)
    return best_index


def pick_pack_card_with_simulation(
    gs: Mapping[str, Any],
    cfg: Config,
    pack_cards: list[dict],
    intent: str,
    *,
    ctx: PolicyContext | None = None,
) -> int:
    """Pick a pack card index using simulation + heuristics."""
    intent_key = intent.lower() if isinstance(intent, str) else ""
    if not intent_key:
        return pick_pack_card(pack_cards, intent)

    deck_cards = gs_deck_cards(gs)
    seed = gs_seed(gs) or cfg.seed or ""
    seed_text = f"{seed}|{cfg.deck}|{cfg.stake}|{intent_key}"
    sim_scores = evaluate_pack_choice(
        deck_cards, pack_cards, intent, seed_text=seed_text
    )
    if not any(abs(score) > 1e-12 for score in sim_scores):
        return pick_pack_card(pack_cards, intent)

    best_index = INDEX_INITIAL
    best_score = float("-inf")
    trace_options: list[dict[str, Any]] = []
    for index, (card, sim_score) in enumerate(
        zip(pack_cards, sim_scores, strict=False)
    ):
        heur_score, debug = _heuristic_score_pack_card(card, intent_key)
        combined = float(heur_score) + PACK_SIM_SCORE_WEIGHT * sim_score
        trace_options.append(
            {
                "index": index,
                "key": debug.get("key"),
                "text": debug.get("text"),
                "heuristic": heur_score,
                "sim": float(sim_score),
                "combined": combined,
            }
        )
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(
                "pick_pack_card sim option: idx=%s combined=%.2f heur=%s sim=%.4f key=%s text=%r",
                index,
                combined,
                heur_score,
                sim_score,
                debug["key"],
                debug["text"],
            )
        if combined > best_score:
            best_score = combined
            best_index = index
    if ctx is not None:
        ctx.round_memory["pack_trace"] = {
            "intent": intent,
            "seed_text": seed_text,
            "options": trace_options,
            "chosen": {"index": best_index, "combined": best_score},
        }
    logger.debug(
        "pick_pack_card_with_simulation: best_idx=%s best_score=%.2f",
        best_index,
        best_score,
    )
    return best_index


def needs_targets(card: Mapping[str, Any]) -> bool:
    """Return True if the card likely needs target selection."""
    structured = _structured_targets(card)
    if structured is not None:
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(
                "needs_targets: structured=%s key=%s text=%r",
                structured,
                card_key(card),
                pack_card_text(card),
            )
        return structured
    text = pack_card_text(card)
    if not text:
        return False
    tokens = card_tokens(text)
    if tokens & _TARGET_TOKENS:
        logger.debug("needs_targets: tokens include target -> True (%r)", text)
        return True
    if "select" in tokens and tokens & _TARGET_CARD_TOKENS:
        logger.debug("needs_targets: tokens include select + card -> True (%r)", text)
        return True
    if tokens & _TARGET_ACTION_TOKENS and tokens & _TARGET_CARD_TOKENS:
        logger.debug("needs_targets: tokens include action + card -> True (%r)", text)
        return True
    return False


def target_limit(card: Mapping[str, Any]) -> int:
    """Return a best-effort max target count for `card`."""
    for key in ("target_count", "target_max", "targets_required"):
        value = card.get(key)
        if isinstance(value, int) and not isinstance(value, bool):
            return max(1, min(5, int(value)))
    nested = card.get("targets")
    if isinstance(nested, int) and not isinstance(nested, bool):
        return max(1, min(5, int(nested)))
    key = card_key(card) or ""
    if key in _TARGET_MAX_BY_KEY:
        return _TARGET_MAX_BY_KEY[key]
    return MAX_TARGETS


def choose_targets(
    gs: Mapping[str, Any], intent: str, *, max_targets: int = MAX_TARGETS
) -> list[int]:
    """Choose up to `max_targets` target indices from the hand."""
    hand_cards = gs_hand_cards(gs)
    if not hand_cards:
        return []
    intent_key = intent.lower() if isinstance(intent, str) else ""
    suit_target = majority_suit(hand_cards) if "flush" in intent_key else None
    candidates: list[_TargetCandidate] = []
    for index, card in enumerate(hand_cards):
        if _is_hidden_or_debuffed(card):
            continue
        score = card_rank(card)
        if suit_target and card_suit(card) == suit_target:
            score += TARGET_SUIT_BONUS
        candidates.append(_TargetCandidate(index=index, score=score))
    if not candidates:
        for index, card in enumerate(hand_cards):
            score = card_rank(card)
            if suit_target and card_suit(card) == suit_target:
                score += TARGET_SUIT_BONUS
            candidates.append(_TargetCandidate(index=index, score=score))
    if not candidates:
        return []
    candidates.sort(key=lambda item: item.score, reverse=True)
    limit = max(1, min(int(max_targets), len(candidates)))
    top = candidates[:limit]
    chosen = [item.index for item in top]
    if logger.isEnabledFor(logging.DEBUG):
        logger.debug(
            "choose_targets: intent=%r suit_target=%s candidates=%s chosen=%s",
            intent,
            suit_target,
            [(c.index, c.score) for c in candidates],
            chosen,
        )
    return chosen


def _structured_targets(card: Mapping[str, Any]) -> bool | None:
    for key in (
        "requires_target",
        "requires_targets",
        "needs_targets",
        "target_required",
    ):
        value = card.get(key)
        if isinstance(value, bool):
            return value
    for key in ("target_count", "target_min", "target_max", "targets_required"):
        value = card.get(key)
        if isinstance(value, int) and not isinstance(value, bool):
            return value > TARGET_COUNT_NONE
    if "targets" in card:
        value = card.get("targets")
        if isinstance(value, bool):
            return value
        if isinstance(value, int) and not isinstance(value, bool):
            return value > TARGET_COUNT_NONE
        if isinstance(value, list):
            return len(value) > LENGTH_NONE
    return None


def _score_from_category(category: str) -> int:
    if category == "xmult":
        return CATEGORY_SCORE_XMULT
    if category == "mult":
        return CATEGORY_SCORE_MULT
    if category == "chips":
        return CATEGORY_SCORE_CHIPS
    if category == "econ":
        return CATEGORY_SCORE_ECON
    return CATEGORY_SCORE_DEFAULT


def _is_hidden_or_debuffed(card: Mapping[str, Any]) -> bool:
    for key in ("debuffed", "debuff", "hidden", "face_down", "disabled"):
        value = card.get(key)
        if isinstance(value, bool) and value:
            return True
    return False


def _heuristic_score_pack_card(
    card: dict, intent_key: str
) -> tuple[int, dict[str, Any]]:
    text = pack_card_text(card)
    tokens = card_tokens(text)
    score = SCORE_INITIAL
    key = card_key(card)
    rule = joker_rule(key, text) if key and key.startswith("j_") else None
    category_score = SCORE_INITIAL
    if rule is not None:
        category_score = _score_from_category(rule.category)
        score += category_score
    xmult_hit = bool(tokens & _XMULT_TOKENS) or has_x_token(
        tokens,
        slice_after_first_char=SLICE_AFTER_FIRST_CHAR,
    )
    if xmult_hit:
        score += PICK_XMULT_BONUS
    mult_hit = bool(tokens & _MULT_TOKENS)
    if mult_hit:
        score += PICK_MULT_BONUS
    chips_hit = bool(tokens & _CHIPS_TOKENS)
    if chips_hit:
        score += PICK_CHIPS_BONUS
    intent_bonus = SCORE_INITIAL
    if intent_key:
        if "flush" in intent_key and "flush" in tokens:
            intent_bonus += INTENT_FLUSH_BONUS
        if "straight" in intent_key and "straight" in tokens:
            intent_bonus += INTENT_STRAIGHT_BONUS
        if "pair" in intent_key and "pair" in tokens:
            intent_bonus += INTENT_PAIR_BONUS
    score += intent_bonus
    return score, {
        "text": text,
        "key": key,
        "category_score": category_score,
        "xmult_hit": xmult_hit,
        "mult_hit": mult_hit,
        "chips_hit": chips_hit,
        "intent_bonus": intent_bonus,
    }
