from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, TYPE_CHECKING

from balatro_ai.actions import Action
from balatro_ai.cards import card_key, card_rank, card_suit, card_text, card_tokens
from balatro_ai.config import Config
from balatro_ai.gs import gs_hand_cards, gs_pack_cards, gs_state
from balatro_ai.joker_rules import joker_rule

if TYPE_CHECKING:
    from balatro_ai.policy import PolicyContext


_CHIPS_TOKENS = {"chips", "chip", "bonus"}
_MULT_TOKENS = {"mult", "multiplier", "if", "when", "each"}
_XMULT_TOKENS = {"xmult", "times"}
_TARGET_TOKENS = {"target", "select", "enhance", "convert", "destroy", "copy"}


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
        text = pack_card_text(pack_cards[index])
        if needs_targets(text):
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
    best_index = 0
    best_score = -1
    intent_key = intent.lower() if isinstance(intent, str) else ""
    for index, card in enumerate(pack_cards):
        text = pack_card_text(card)
        tokens = card_tokens(text)
        score = 0
        key = card_key(card)
        rule = joker_rule(key) if key and key.startswith("j_") else None
        if rule is not None:
            score += _score_from_category(rule.category)
        if tokens & _XMULT_TOKENS or _has_x_token(tokens):
            score += 100
        if tokens & _MULT_TOKENS:
            score += 50
        if tokens & _CHIPS_TOKENS:
            score += 20
        if intent_key:
            if "flush" in intent_key and "flush" in tokens:
                score += 40
            if "straight" in intent_key and "straight" in tokens:
                score += 40
            if "pair" in intent_key and "pair" in tokens:
                score += 30
        if score > best_score:
            best_score = score
            best_index = index
    return best_index


def needs_targets(card_text: str) -> bool:
    """Return True if the card likely needs target selection."""
    if not card_text:
        return False
    return bool(card_tokens(card_text) & _TARGET_TOKENS)


def choose_targets(gs: Mapping[str, Any], intent: str) -> list[int]:
    """Choose 1-2 target indices from the hand."""
    hand_cards = gs_hand_cards(gs)
    if not hand_cards:
        return []
    intent_key = intent.lower() if isinstance(intent, str) else ""
    suit_target = _majority_suit(hand_cards) if "flush" in intent_key else None
    candidates: list[_TargetCandidate] = []
    for index, card in enumerate(hand_cards):
        if _is_hidden_or_debuffed(card):
            continue
        score = card_rank(card)
        if suit_target and card_suit(card) == suit_target:
            score += 5
        candidates.append(_TargetCandidate(index=index, score=score))
    if not candidates:
        for index, card in enumerate(hand_cards):
            score = card_rank(card)
            if suit_target and card_suit(card) == suit_target:
                score += 5
            candidates.append(_TargetCandidate(index=index, score=score))
    if not candidates:
        return []
    candidates.sort(key=lambda item: item.score, reverse=True)
    top = candidates[:2]
    return [item.index for item in top]


def _has_x_token(tokens: set[str]) -> bool:
    if "x" in tokens:
        return True
    for token in tokens:
        if token.startswith("x") and token[1:].isdigit():
            return True
    return False


def _score_from_category(category: str) -> int:
    if category == "xmult":
        return 100
    if category == "mult":
        return 50
    if category == "chips":
        return 20
    if category == "econ":
        return 0
    return 0


def _majority_suit(cards: list[dict]) -> str | None:
    counts: dict[str, int] = {}
    for card in cards:
        suit = card_suit(card)
        if not suit:
            continue
        counts[suit] = counts.get(suit, 0) + 1
    if not counts:
        return None
    return max(counts.items(), key=lambda item: item[1])[0]


def _is_hidden_or_debuffed(card: Mapping[str, Any]) -> bool:
    for key in ("debuffed", "debuff", "hidden", "face_down", "disabled"):
        value = card.get(key)
        if isinstance(value, bool) and value:
            return True
    return False
