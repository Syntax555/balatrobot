from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypedDict


class BlindState(TypedDict, total=False):
    score: int


class RoundState(TypedDict, total=False):
    hands_left: int
    hands: int
    discards_left: int
    discards: int
    chips: int
    blind: BlindState


class HandState(TypedDict, total=False):
    cards: list[dict]


class ShopState(TypedDict, total=False):
    cards: list[dict]
    vouchers: list[dict]
    packs: list[dict]
    reroll_cost: int


class PackState(TypedDict, total=False):
    cards: list[dict]


class GameState(TypedDict, total=False):
    state: str
    seed: str
    money: int
    ante_num: int
    round_num: int
    won: bool
    round: RoundState
    blind: BlindState
    hand: HandState
    cards: dict
    jokers: list[dict]
    consumables: list[dict]
    shop: ShopState
    pack: PackState


def safe_get(gs: Mapping[str, Any], path: list[str], default: Any = None) -> Any:
    """Safely walk a nested mapping using a list of keys."""
    current: Any = gs
    for key in path:
        if not isinstance(current, Mapping):
            return default
        if key not in current:
            return default
        current = current[key]
    return current


def require_state(gs: Mapping[str, Any], expected: str) -> None:
    """Require the game state to match the expected state."""
    actual = gs_state(gs)
    if actual != expected:
        raise ValueError(f"Expected state {expected}, got {actual or 'UNKNOWN'}")


def gs_state(gs: Mapping[str, Any]) -> str:
    """Return the current game state string."""
    value = safe_get(gs, ["state"], "")
    return value if isinstance(value, str) else ""


def gs_seed(gs: Mapping[str, Any]) -> str | None:
    """Return the run seed when available."""
    value = safe_get(gs, ["seed"], None)
    return value if isinstance(value, str) else None


def gs_money(gs: Mapping[str, Any]) -> int:
    """Return the current money amount."""
    return _int_or_default(safe_get(gs, ["money"], 0), 0)


def gs_ante(gs: Mapping[str, Any]) -> int:
    """Return the current ante number."""
    return _int_or_default(safe_get(gs, ["ante_num"], 0), 0)


def gs_round_num(gs: Mapping[str, Any]) -> int:
    """Return the current round number."""
    return _int_or_default(safe_get(gs, ["round_num"], 0), 0)


def gs_won(gs: Mapping[str, Any]) -> bool:
    """Return whether the run was won."""
    value = safe_get(gs, ["won"], False)
    return bool(value) if isinstance(value, bool) else False


def gs_round(gs: Mapping[str, Any]) -> dict:
    """Return the round state dictionary."""
    value = safe_get(gs, ["round"], {})
    return dict(value) if isinstance(value, Mapping) else {}


def gs_hands_left(gs: Mapping[str, Any]) -> int:
    """Return the number of hands remaining."""
    value = safe_get(gs, ["round", "hands_left"], None)
    if value is None:
        value = safe_get(gs, ["round", "hands"], 0)
    return _int_or_default(value, 0)


def gs_discards_left(gs: Mapping[str, Any]) -> int:
    """Return the number of discards remaining."""
    value = safe_get(gs, ["round", "discards_left"], None)
    if value is None:
        value = safe_get(gs, ["round", "discards"], 0)
    return _int_or_default(value, 0)


def gs_reroll_cost(gs: Mapping[str, Any]) -> int:
    """Return the shop reroll cost."""
    value = safe_get(gs, ["shop", "reroll_cost"], 0)
    return _int_or_default(value, 0)


def gs_round_chips(gs: Mapping[str, Any]) -> int | None:
    """Return the current round chips, if present."""
    value = safe_get(gs, ["round", "chips"], None)
    return _int_or_none(value)


def gs_blind(gs: Mapping[str, Any]) -> dict | None:
    """Return the blind dictionary if present."""
    blind = safe_get(gs, ["round", "blind"], None)
    if not isinstance(blind, Mapping):
        blind = safe_get(gs, ["blind"], None)
    return dict(blind) if isinstance(blind, Mapping) else None


def gs_blind_score(gs: Mapping[str, Any]) -> int | None:
    """Return the blind score if present."""
    blind = gs_blind(gs)
    if not blind:
        return None
    return _int_or_none(blind.get("score"))


def gs_hand_cards(gs: Mapping[str, Any]) -> list[dict]:
    """Return the list of hand cards."""
    value = safe_get(gs, ["hand", "cards"], [])
    return _list_of_dicts(value)


def gs_jokers(gs: Mapping[str, Any]) -> list[dict]:
    """Return the list of jokers."""
    value = safe_get(gs, ["jokers"], [])
    return _list_of_dicts(value)


def gs_consumables(gs: Mapping[str, Any]) -> list[dict]:
    """Return the list of consumables."""
    value = safe_get(gs, ["consumables"], [])
    return _list_of_dicts(value)


def gs_shop_cards(gs: Mapping[str, Any]) -> list[dict]:
    """Return the list of shop cards."""
    value = safe_get(gs, ["shop", "cards"], [])
    return _list_of_dicts(value)


def gs_shop_vouchers(gs: Mapping[str, Any]) -> list[dict]:
    """Return the list of shop vouchers."""
    value = safe_get(gs, ["shop", "vouchers"], [])
    return _list_of_dicts(value)


def gs_shop_packs(gs: Mapping[str, Any]) -> list[dict]:
    """Return the list of shop packs."""
    value = safe_get(gs, ["shop", "packs"], [])
    return _list_of_dicts(value)


def gs_pack_cards(gs: Mapping[str, Any]) -> list[dict]:
    """Return the list of cards in the opened pack."""
    value = safe_get(gs, ["pack", "cards"], [])
    return _list_of_dicts(value)


def gs_deck_cards(gs: Mapping[str, Any]) -> list[dict]:
    """Return the list of cards remaining in the deck pile."""
    value = safe_get(gs, ["cards", "cards"], [])
    return _list_of_dicts(value)


def _int_or_default(value: Any, default: int) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    return default


def _int_or_none(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None


def _list_of_dicts(value: Any) -> list[dict]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, Mapping)]
