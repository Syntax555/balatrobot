from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping, TYPE_CHECKING

from balatro_ai.actions import Action
from balatro_ai.config import Config
from balatro_ai.gs import gs_hand_cards, gs_pack_cards, gs_state

if TYPE_CHECKING:
    from balatro_ai.policy import PolicyContext


_TOKEN_RE = re.compile(r"[a-z0-9]+")
_CHIPS_TOKENS = {"chips", "chip", "bonus"}
_MULT_TOKENS = {"mult", "multiplier", "if", "when", "each"}
_XMULT_TOKENS = {"xmult", "times"}
_TARGET_TOKENS = {"target", "select", "enhance", "convert", "destroy", "copy"}

_RANK_MAP = {
    "a": 14,
    "k": 13,
    "q": 12,
    "j": 11,
    "t": 10,
    "10": 10,
    "9": 9,
    "8": 8,
    "7": 7,
    "6": 6,
    "5": 5,
    "4": 4,
    "3": 3,
    "2": 2,
}
_SUIT_TOKENS = {
    "spades": "spades",
    "spade": "spades",
    "hearts": "hearts",
    "heart": "hearts",
    "diamonds": "diamonds",
    "diamond": "diamonds",
    "clubs": "clubs",
    "club": "clubs",
}


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
            return Action(kind="pack", params={"card": index, "targets": targets})
        return Action(kind="pack", params={"card": index})


def pack_card_text(c: dict) -> str:
    """Return lowercase text for a pack card, preferring label then key."""
    if not isinstance(c, Mapping):
        return ""
    label = c.get("label")
    if isinstance(label, str) and label:
        return label.lower()
    key = c.get("key")
    if isinstance(key, str) and key:
        return key.lower()
    return ""


def pick_pack_card(pack_cards: list[dict], intent: str) -> int:
    """Pick a pack card index using simple heuristics."""
    best_index = 0
    best_score = -1
    intent_key = intent.lower() if isinstance(intent, str) else ""
    for index, card in enumerate(pack_cards):
        text = pack_card_text(card)
        tokens = set(_TOKEN_RE.findall(text))
        score = 0
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
    tokens = set(_TOKEN_RE.findall(card_text.lower()))
    return bool(tokens & _TARGET_TOKENS)


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
        score = _rank_value(card)
        if suit_target and _card_suit(card) == suit_target:
            score += 5
        candidates.append(_TargetCandidate(index=index, score=score))
    if not candidates:
        for index, card in enumerate(hand_cards):
            score = _rank_value(card)
            if suit_target and _card_suit(card) == suit_target:
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


def _rank_value(card: Mapping[str, Any]) -> int:
    for key in ("rank", "value", "rank_value"):
        value = card.get(key)
        if isinstance(value, int) and not isinstance(value, bool):
            return value
        if isinstance(value, str):
            mapped = _RANK_MAP.get(value.lower())
            if mapped is not None:
                return mapped
    label = card.get("label")
    if isinstance(label, str):
        return _rank_from_text(label)
    return 0


def _rank_from_text(text: str) -> int:
    lowered = text.lower()
    if "10" in lowered:
        return 10
    tokens = _TOKEN_RE.findall(lowered)
    for token in tokens:
        if token in _RANK_MAP:
            return _RANK_MAP[token]
    for char in lowered:
        if char in _RANK_MAP:
            return _RANK_MAP[char]
    return 0


def _card_suit(card: Mapping[str, Any]) -> str | None:
    for key in ("suit", "suit_name", "suit_key"):
        value = card.get(key)
        if isinstance(value, str) and value:
            normalized = _SUIT_TOKENS.get(value.lower())
            return normalized or value.lower()
    label = card.get("label")
    if isinstance(label, str):
        tokens = _TOKEN_RE.findall(label.lower())
        for token in tokens:
            if token in _SUIT_TOKENS:
                return _SUIT_TOKENS[token]
    return None


def _majority_suit(cards: list[dict]) -> str | None:
    counts: dict[str, int] = {}
    for card in cards:
        suit = _card_suit(card)
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
