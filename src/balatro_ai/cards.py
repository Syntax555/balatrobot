from __future__ import annotations

import re
from typing import Any, Mapping

_TOKEN_RE = re.compile(r"[a-z0-9]+")
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
    "s": "spades",
    "hearts": "hearts",
    "heart": "hearts",
    "h": "hearts",
    "diamonds": "diamonds",
    "diamond": "diamonds",
    "d": "diamonds",
    "clubs": "clubs",
    "club": "clubs",
    "c": "clubs",
}


def card_text(card: Mapping[str, Any]) -> str:
    """Return lowercase label or key text for a card."""
    label = card.get("label")
    if isinstance(label, str) and label:
        return label.lower()
    key = card.get("key")
    if isinstance(key, str) and key:
        return key.lower()
    return ""


def card_key(card: Mapping[str, Any]) -> str | None:
    """Return the card key when present."""
    key = card.get("key")
    if isinstance(key, str) and key:
        return key
    return None


def card_tokens(text: str) -> set[str]:
    """Tokenize a lowercase text string into simple alphanumerics."""
    if not text:
        return set()
    return set(_TOKEN_RE.findall(text.lower()))


def card_rank(card: Mapping[str, Any]) -> int:
    """Return a normalized rank value (A=14)."""
    for key in ("rank", "value", "rank_value"):
        value = card.get(key)
        parsed = _parse_rank_value(value)
        if parsed > 0:
            return parsed
    value = card.get("value")
    if isinstance(value, Mapping):
        nested = value.get("rank") or value.get("value")
        parsed = _parse_rank_value(nested)
        if parsed > 0:
            return parsed
    label = card.get("label")
    if isinstance(label, str):
        return _rank_from_text(label)
    return 0


def card_suit(card: Mapping[str, Any]) -> str | None:
    """Return a normalized suit string when available."""
    for key in ("suit", "suit_name", "suit_key"):
        value = card.get(key)
        if isinstance(value, str) and value:
            return _SUIT_TOKENS.get(value.lower(), value.lower())
    value = card.get("value")
    if isinstance(value, Mapping):
        nested = value.get("suit")
        if isinstance(nested, str) and nested:
            return _SUIT_TOKENS.get(nested.lower(), nested.lower())
    label = card.get("label")
    if isinstance(label, str):
        tokens = card_tokens(label)
        for token in tokens:
            if token in _SUIT_TOKENS:
                return _SUIT_TOKENS[token]
    return None


def _parse_rank_value(value: Any) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, str):
        return _rank_from_text(value)
    return 0


def _rank_from_text(text: str) -> int:
    lowered = text.lower()
    if "10" in lowered:
        return 10
    tokens = _TOKEN_RE.findall(lowered)
    for token in tokens:
        if token in _RANK_MAP:
            return _RANK_MAP[token]
        if token.isdigit():
            value = int(token)
            if 2 <= value <= 14:
                return value
    for char in lowered:
        if char in _RANK_MAP:
            return _RANK_MAP[char]
    return 0
