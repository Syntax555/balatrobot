from __future__ import annotations

import argparse
import os
import tempfile
import uuid
from typing import Any

from balatro_ai.cards import card_key, card_text
from balatro_ai.gs import (
    gs_ante,
    gs_deck_cards,
    gs_money,
    gs_round_num,
    gs_seed,
    gs_shop_cards,
    gs_shop_packs,
    gs_shop_vouchers,
    gs_state,
)
from balatro_ai.rpc import BalatroRPC


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Best-effort save/load determinism checks via BalatroBot API.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=12346)
    parser.add_argument(
        "--mode",
        choices=("roundtrip", "shop_reroll"),
        default="roundtrip",
        help="Which check to run.",
    )
    parser.add_argument("--save-path", default="", help="Optional explicit path to save to (otherwise uses temp).")
    return parser


def _temp_save_path() -> str:
    filename = f"balatrobot_repro_{uuid.uuid4().hex}.jkr"
    return os.path.join(tempfile.gettempdir(), filename)


def _state_brief(gs: dict[str, Any]) -> dict[str, Any]:
    return {
        "state": gs_state(gs),
        "seed": gs_seed(gs),
        "ante": gs_ante(gs),
        "round": gs_round_num(gs),
        "money": gs_money(gs),
        "deck_size": len(gs_deck_cards(gs)),
    }


def _shop_fingerprint(gs: dict[str, Any]) -> dict[str, Any]:
    def ident(item: dict[str, Any]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        key = card_key(item)
        if key:
            out["key"] = key
        label = card_text(item)
        if label:
            out["label"] = label
        cost = item.get("cost")
        if isinstance(cost, int) and not isinstance(cost, bool):
            out["cost"] = cost
        return out

    return {
        "cards": [ident(c) for c in gs_shop_cards(gs)],
        "vouchers": [ident(v) for v in gs_shop_vouchers(gs)],
        "packs": [ident(p) for p in gs_shop_packs(gs)],
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    base_url = f"http://{args.host}:{args.port}"
    rpc = BalatroRPC(base_url=base_url, timeout=30.0)
    save_path = args.save_path.strip() if isinstance(args.save_path, str) else ""
    if not save_path:
        save_path = _temp_save_path()

    try:
        gs0 = dict(rpc.gamestate())
        rpc.save(save_path)
        rpc.load(save_path)
        gs1 = dict(rpc.gamestate())

        if args.mode == "roundtrip":
            brief0 = _state_brief(gs0)
            brief1 = _state_brief(gs1)
            ok = brief0 == brief1
            print("before:", brief0)
            print("after :", brief1)
            print("match :", ok)
            return 0 if ok else 1

        if gs_state(gs0) != "SHOP":
            print("mode=shop_reroll requires state=SHOP. Current:", _state_brief(gs0))
            return 2

        fp0 = _shop_fingerprint(gs0)
        rpc.load(save_path)
        gs_a = dict(rpc.reroll())
        fp_a = _shop_fingerprint(gs_a)
        rpc.load(save_path)
        gs_b = dict(rpc.reroll())
        fp_b = _shop_fingerprint(gs_b)

        ok = fp_a == fp_b
        print("base :", fp0)
        print("reroll A:", fp_a)
        print("reroll B:", fp_b)
        print("match :", ok)
        return 0 if ok else 1
    finally:
        try:
            os.remove(save_path)
        except OSError:
            pass
        rpc.close()


if __name__ == "__main__":
    raise SystemExit(main())

