from __future__ import annotations

import os
import tempfile
import uuid
from collections.abc import Mapping
from typing import Any

from balatro_ai.cards import card_key, card_rank, card_suit, card_text
from balatro_ai.gs import (
    gs_blind_score,
    gs_deck_cards,
    gs_discards_left,
    gs_hand_cards,
    gs_hands_left,
    gs_money,
    gs_pack_cards,
    gs_round_chips,
    gs_seed,
    gs_shop_cards,
    gs_shop_packs,
    gs_shop_vouchers,
    gs_state,
)
from balatro_ai.pack_policy import choose_targets, needs_targets, target_limit
from balatro_ai.rpc import BalatroRPC, BalatroRPCError


def determinism_probe(
    *, rpc: BalatroRPC, gs: Mapping[str, Any], kind: str
) -> tuple[bool, str | None]:
    """Return (ok, reason) for whether save/load appears deterministic enough for rollouts.

    The probe is designed to be side-effect free: it snapshots with save(), runs a small
    sequence of actions twice from the same snapshot, compares fingerprints, then restores.
    """
    state = gs_state(gs)
    save_path = _save_path()
    try:
        rpc.save(save_path)
        if kind == "shop" and state == "SHOP":
            ok = _probe_shop_reroll(rpc, save_path)
            return ok, None if ok else "shop_reroll_mismatch"
        if kind == "hand" and state == "SELECTING_HAND":
            ok = _probe_hand_play(rpc, save_path, gs)
            return ok, None if ok else "hand_play_mismatch"
        if kind == "pack" and state == "SMODS_BOOSTER_OPENED":
            ok = _probe_pack_pick(rpc, save_path, gs)
            return ok, None if ok else "pack_pick_mismatch"
        ok = _probe_roundtrip(rpc, save_path, gs)
        return ok, None if ok else "roundtrip_mismatch"
    except BalatroRPCError as exc:
        return False, f"rpc_error:{exc.code}"
    finally:
        try:
            os.remove(save_path)
        except OSError:
            pass


def _probe_roundtrip(rpc: BalatroRPC, save_path: str, gs: Mapping[str, Any]) -> bool:
    before = _state_fingerprint(gs)
    rpc.load(save_path)
    after = _state_fingerprint(rpc.gamestate())
    rpc.load(save_path)
    return before == after


def _probe_shop_reroll(rpc: BalatroRPC, save_path: str) -> bool:
    rpc.load(save_path)
    a = _shop_fingerprint(rpc.reroll())
    rpc.load(save_path)
    b = _shop_fingerprint(rpc.reroll())
    rpc.load(save_path)
    return a == b


def _probe_hand_play(rpc: BalatroRPC, save_path: str, gs: Mapping[str, Any]) -> bool:
    hand_cards = gs_hand_cards(gs)
    if not hand_cards:
        return True
    count = min(5, len(hand_cards))
    play = list(range(count))

    rpc.load(save_path)
    a = _hand_outcome_fingerprint(rpc.play(cards=play))
    rpc.load(save_path)
    b = _hand_outcome_fingerprint(rpc.play(cards=play))
    rpc.load(save_path)
    return a == b


def _probe_pack_pick(rpc: BalatroRPC, save_path: str, gs: Mapping[str, Any]) -> bool:
    pack_cards = gs_pack_cards(gs)
    if not pack_cards:
        return True
    first = pack_cards[0]
    params: dict[str, Any] = {"card": 0}
    if needs_targets(first):
        targets = choose_targets(gs, "", max_targets=target_limit(first))
        if not targets:
            params = {"skip": True}
        else:
            params["targets"] = targets

    rpc.load(save_path)
    a = _state_fingerprint(rpc.pack(**params))
    rpc.load(save_path)
    b = _state_fingerprint(rpc.pack(**params))
    rpc.load(save_path)
    return a == b


def _state_fingerprint(gs: Mapping[str, Any]) -> tuple:
    return (
        gs_state(gs),
        gs_seed(gs),
        gs_money(gs),
        gs_round_chips(gs),
        gs_blind_score(gs),
        gs_hands_left(gs),
        gs_discards_left(gs),
        len(gs_deck_cards(gs)),
        _hand_cards_fingerprint(gs_hand_cards(gs)),
        len(gs_shop_cards(gs)),
        len(gs_shop_vouchers(gs)),
        len(gs_shop_packs(gs)),
        len(gs_pack_cards(gs)),
    )


def _hand_outcome_fingerprint(gs: Mapping[str, Any]) -> tuple:
    return (
        gs_state(gs),
        gs_money(gs),
        gs_round_chips(gs),
        gs_blind_score(gs),
        gs_hands_left(gs),
        gs_discards_left(gs),
        _hand_cards_fingerprint(gs_hand_cards(gs)),
    )


def _hand_cards_fingerprint(cards: list[dict]) -> tuple[tuple[Any, ...], ...]:
    out: list[tuple[Any, ...]] = []
    for card in cards:
        modifier = card.get("modifier")
        seal = edition = enhancement = None
        if isinstance(modifier, Mapping):
            seal = modifier.get("seal")
            edition = modifier.get("edition")
            enhancement = modifier.get("enhancement")
        out.append((card_rank(card), card_suit(card), seal, edition, enhancement))
    return tuple(out)


def _shop_fingerprint(gs: Mapping[str, Any]) -> tuple:
    return (
        tuple(_item_fingerprint(item) for item in gs_shop_cards(gs)),
        tuple(_item_fingerprint(item) for item in gs_shop_vouchers(gs)),
        tuple(_item_fingerprint(item) for item in gs_shop_packs(gs)),
        gs_money(gs),
        gs_seed(gs),
    )


def _item_fingerprint(item: Mapping[str, Any]) -> tuple[Any, ...]:
    cost = item.get("cost")
    if isinstance(cost, bool) or not isinstance(cost, int):
        cost = None
    return (
        card_key(item) or "",
        card_text(item) or "",
        cost,
    )


def _save_path() -> str:
    filename = f"balatrobot_determinism_{uuid.uuid4().hex}.jkr"
    return os.path.join(tempfile.gettempdir(), filename)
