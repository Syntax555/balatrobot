from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, TYPE_CHECKING

from balatro_ai.actions import Action
from balatro_ai.cards import card_key, card_rank, card_suit, card_text, card_tokens
from balatro_ai.config import Config
from balatro_ai.gs import gs_hand_cards, gs_pack_cards, gs_state
from balatro_ai.hand_stats import majority_suit
from balatro_ai.joker_rules import joker_rule
from balatro_ai.token_utils import has_x_token

if TYPE_CHECKING:
    from balatro_ai.policy import PolicyContext


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

CATEGORY_SCORE_XMULT = 100
CATEGORY_SCORE_MULT = 50
CATEGORY_SCORE_CHIPS = 20
CATEGORY_SCORE_ECON = 0
CATEGORY_SCORE_DEFAULT = 0

TARGET_COUNT_NONE = 0
LENGTH_NONE = 0

SLICE_AFTER_FIRST_CHAR = 1


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
        ctx: "PolicyContext",
        intent: str,
    ) -> Action:
        """Choose an action in SMODS_BOOSTER_OPENED state."""
        if gs_state(gs) != "SMODS_BOOSTER_OPENED":
            raise ValueError(f"PackPolicy used outside SMODS_BOOSTER_OPENED: {gs_state(gs)}")
        pack_cards = gs_pack_cards(gs)
        if not pack_cards:
            return Action(kind="pack", params={"skip": True})
        index = pick_pack_card(pack_cards, intent)
        card = pack_cards[index]
        if needs_targets(card):
            targets = choose_targets(gs, intent)
            if not targets:
                return Action(kind="pack", params={"skip": True})
            return Action(kind="pack", params={"card": index, "targets": targets})
        return Action(kind="pack", params={"card": index})


def pack_card_text(c: dict) -> str:
    """Return lowercase text for a pack card, preferring label then key."""
    if not isinstance(c, Mapping):
        return ""
    return card_text(c)


def pick_pack_card(pack_cards: list[dict], intent: str) -> int:
    """Pick a pack card index using simple heuristics."""
    best_index = INDEX_INITIAL
    best_score = BEST_SCORE_INITIAL
    intent_key = intent.lower() if isinstance(intent, str) else ""
    for index, card in enumerate(pack_cards):
        text = pack_card_text(card)
        tokens = card_tokens(text)
        score = SCORE_INITIAL
        key = card_key(card)
        rule = joker_rule(key) if key and key.startswith("j_") else None
        if rule is not None:
            score += _score_from_category(rule.category)
        if tokens & _XMULT_TOKENS or has_x_token(tokens, slice_after_first_char=SLICE_AFTER_FIRST_CHAR):
            score += PICK_XMULT_BONUS
        if tokens & _MULT_TOKENS:
            score += PICK_MULT_BONUS
        if tokens & _CHIPS_TOKENS:
            score += PICK_CHIPS_BONUS
        if intent_key:
            if "flush" in intent_key and "flush" in tokens:
                score += INTENT_FLUSH_BONUS
            if "straight" in intent_key and "straight" in tokens:
                score += INTENT_STRAIGHT_BONUS
            if "pair" in intent_key and "pair" in tokens:
                score += INTENT_PAIR_BONUS
        if score > best_score:
            best_score = score
            best_index = index
    return best_index


def needs_targets(card: Mapping[str, Any]) -> bool:
    """Return True if the card likely needs target selection."""
    structured = _structured_targets(card)
    if structured is not None:
        return structured
    text = pack_card_text(card)
    if not text:
        return False
    tokens = card_tokens(text)
    if tokens & _TARGET_TOKENS:
        return True
    if "select" in tokens and tokens & _TARGET_CARD_TOKENS:
        return True
    if tokens & _TARGET_ACTION_TOKENS and tokens & _TARGET_CARD_TOKENS:
        return True
    return False


def choose_targets(gs: Mapping[str, Any], intent: str) -> list[int]:
    """Choose 1-2 target indices from the hand."""
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
    top = candidates[:MAX_TARGETS]
    return [item.index for item in top]


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
