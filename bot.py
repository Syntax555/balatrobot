# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "requests",
# ]
# ///

from __future__ import annotations

import argparse
import itertools
import math
import os
import random
import time
from itertools import combinations
from typing import Any, Mapping, Sequence

import requests

JsonObject = dict[str, Any]


class BalatroBotError(RuntimeError):
    pass


class BalatroBotClient:
    def __init__(self, url: str, *, timeout_s: float = 10.0) -> None:
        self._url = url.rstrip("/")
        self._timeout_s = timeout_s
        self._session = requests.Session()
        self._request_ids = itertools.count(1)

    def rpc(self, method: str, params: JsonObject | None = None) -> JsonObject:
        payload: JsonObject = {
            "jsonrpc": "2.0",
            "method": method,
            "id": next(self._request_ids),
        }
        if params is not None:
            payload["params"] = params

        try:
            response = self._session.post(self._url, json=payload, timeout=self._timeout_s)
            response.raise_for_status()
        except requests.RequestException as exc:
            raise BalatroBotError(f"HTTP error calling {method!r}: {exc}") from exc

        try:
            data = response.json()
        except ValueError as exc:
            preview = response.text[:500].strip()
            raise BalatroBotError(
                f"Non-JSON response calling {method!r} (HTTP {response.status_code}): {preview}"
            ) from exc

        if not isinstance(data, dict):
            raise BalatroBotError(f"Malformed JSON-RPC response calling {method!r}: {data!r}")

        if "error" in data:
            error = data.get("error") or {}
            code = error.get("code")
            message = error.get("message", "Unknown error")
            details = error.get("data")
            raise BalatroBotError(f"RPC error calling {method!r}: {message} (code={code}, data={details})")

        result = data.get("result")
        if not isinstance(result, dict):
            raise BalatroBotError(f"Malformed JSON-RPC result calling {method!r}: {result!r}")

        return result


def _normalize_key(text: str) -> str:
    return "".join(ch for ch in text.upper() if ch.isalnum())


_RANK_CHIPS: dict[str, int] = {
    "2": 2,
    "3": 3,
    "4": 4,
    "5": 5,
    "6": 6,
    "7": 7,
    "8": 8,
    "9": 9,
    "10": 10,
    "J": 10,
    "Q": 10,
    "K": 10,
    "A": 11,
}

_RANK_STRAIGHT: dict[str, int] = {
    "2": 2,
    "3": 3,
    "4": 4,
    "5": 5,
    "6": 6,
    "7": 7,
    "8": 8,
    "9": 9,
    "10": 10,
    "J": 11,
    "Q": 12,
    "K": 13,
    "A": 14,
}

_HAND_BASE_FALLBACK: dict[str, tuple[int, int]] = {
    "HIGH_CARD": (5, 1),
    "PAIR": (10, 2),
    "TWO_PAIR": (20, 2),
    "THREE_OF_A_KIND": (30, 3),
    "STRAIGHT": (30, 4),
    "FLUSH": (35, 4),
    "FULL_HOUSE": (40, 4),
    "FOUR_OF_A_KIND": (60, 7),
    "STRAIGHT_FLUSH": (100, 8),
    "FIVE_OF_A_KIND": (120, 12),
    "FLUSH_HOUSE": (140, 14),
    "FLUSH_FIVE": (160, 16),
}


def _card_suit_rank(card: Mapping[str, Any]) -> tuple[str | None, str | None]:
    value = card.get("value")
    if isinstance(value, dict):
        suit = value.get("suit")
        rank = value.get("rank")
        if isinstance(suit, str) and isinstance(rank, str):
            return suit, rank

    key = card.get("key")
    if isinstance(key, str) and "_" in key:
        suit_key, rank_key = key.split("_", 1)
        return suit_key, rank_key

    return None, None


def _is_straight(rank_values: Sequence[int]) -> bool:
    unique_sorted = sorted(set(rank_values))
    if len(unique_sorted) != 5:
        return False

    is_wheel = unique_sorted == [2, 3, 4, 5, 14]
    if is_wheel:
        return True

    first = unique_sorted[0]
    return unique_sorted == list(range(first, first + 5))


def _classify_poker_hand(cards: Sequence[Mapping[str, Any]]) -> str:
    ranks: list[str] = []
    suits: list[str] = []

    for card in cards:
        modifier = card.get("modifier")
        enhancement = modifier.get("enhancement") if isinstance(modifier, dict) else None
        suit, rank = _card_suit_rank(card)

        if enhancement == "STONE" or suit is None or rank is None:
            continue

        ranks.append(rank)
        suits.append("WILD" if enhancement == "WILD" else suit)

    rank_counts: dict[str, int] = {}
    for rank in ranks:
        rank_counts[rank] = rank_counts.get(rank, 0) + 1
    counts = sorted(rank_counts.values(), reverse=True)

    flush = False
    if len(suits) == 5:
        non_wild_suits = {suit for suit in suits if suit != "WILD"}
        flush = len(non_wild_suits) <= 1

    straight = False
    if len(ranks) == 5:
        straight_values = [_RANK_STRAIGHT.get(rank) for rank in ranks]
        if all(isinstance(value, int) for value in straight_values):
            straight = _is_straight(straight_values)  # type: ignore[arg-type]

    if flush and counts == [5]:
        return "FLUSH_FIVE"
    if flush and counts == [3, 2]:
        return "FLUSH_HOUSE"
    if counts == [5]:
        return "FIVE_OF_A_KIND"
    if straight and flush:
        return "STRAIGHT_FLUSH"
    if counts and counts[0] == 4:
        return "FOUR_OF_A_KIND"
    if counts == [3, 2]:
        return "FULL_HOUSE"
    if flush:
        return "FLUSH"
    if straight:
        return "STRAIGHT"
    if counts and counts[0] == 3:
        return "THREE_OF_A_KIND"
    if counts == [2, 2, 1]:
        return "TWO_PAIR"
    if counts and counts[0] == 2:
        return "PAIR"
    return "HIGH_CARD"


def _hand_base_chips_mult(state: Mapping[str, Any], hand_type: str) -> tuple[float, float]:
    hands = state.get("hands")
    if isinstance(hands, dict):
        normalized = {_normalize_key(key): key for key in hands.keys() if isinstance(key, str)}
        match_key = normalized.get(_normalize_key(hand_type))
        if match_key is not None:
            info = hands.get(match_key)
            if isinstance(info, dict):
                chips = info.get("chips")
                mult = info.get("mult")
                if isinstance(chips, (int, float)) and isinstance(mult, (int, float)):
                    return float(chips), float(mult)

    chips, mult = _HAND_BASE_FALLBACK.get(hand_type, (0, 1))
    return float(chips), float(mult)


def _estimate_card_score(card: Mapping[str, Any]) -> tuple[float, float, float]:
    state = card.get("state")
    if isinstance(state, dict) and state.get("debuff") is True:
        return 0.0, 0.0, 1.0

    _, rank = _card_suit_rank(card)
    modifier = card.get("modifier")
    enhancement = modifier.get("enhancement") if isinstance(modifier, dict) else None
    edition = modifier.get("edition") if isinstance(modifier, dict) else None

    chips = float(_RANK_CHIPS.get(rank, 0)) if isinstance(rank, str) else 0.0
    mult_add = 0.0
    mult_mul = 1.0

    if enhancement == "BONUS":
        chips += 30.0
    elif enhancement == "MULT":
        mult_add += 4.0
    elif enhancement == "GLASS":
        mult_mul *= 2.0
    elif enhancement == "STONE":
        chips = 50.0
    elif enhancement == "LUCKY":
        pass
    elif enhancement == "STEEL":
        pass
    elif enhancement == "GOLD":
        pass
    elif enhancement == "WILD":
        pass
    elif enhancement is not None:
        pass

    if edition == "FOIL":
        chips += 50.0
    elif edition == "HOLO":
        mult_add += 10.0
    elif edition == "POLYCHROME":
        mult_mul *= 1.5

    return chips, mult_add, mult_mul


def _estimate_play_score(state: Mapping[str, Any], played_cards: Sequence[Mapping[str, Any]]) -> float:
    hand_type = _classify_poker_hand(played_cards)
    hand_chips, hand_mult = _hand_base_chips_mult(state, hand_type)

    total_chips = hand_chips
    total_mult = hand_mult
    mult_multiplier = 1.0

    for card in played_cards:
        chips, mult_add, mult_mul = _estimate_card_score(card)
        total_chips += chips
        total_mult += mult_add
        mult_multiplier *= mult_mul

    total_mult *= mult_multiplier
    return float(total_chips) * float(total_mult)


def choose_cards_to_play(state: Mapping[str, Any], *, strategy: str) -> list[int]:
    hand_area = state.get("hand")
    if not isinstance(hand_area, dict):
        return []

    hand_cards = hand_area.get("cards")
    if not isinstance(hand_cards, list) or not hand_cards:
        return []

    highlighted_limit = hand_area.get("highlighted_limit")
    max_cards = int(highlighted_limit) if isinstance(highlighted_limit, int) else 5
    max_cards = max(1, min(5, max_cards, len(hand_cards)))

    if strategy == "first5":
        return list(range(max_cards))

    best_indices: tuple[int, ...] | None = None
    best_score = float("-inf")
    for indices in combinations(range(len(hand_cards)), max_cards):
        selected = [hand_cards[index] for index in indices if isinstance(hand_cards[index], dict)]
        if len(selected) != max_cards:
            continue
        score = _estimate_play_score(state, selected)
        if score > best_score:
            best_score = score
            best_indices = indices

    if best_indices is None:
        return list(range(max_cards))

    return list(best_indices)


def _round_chips(state: Mapping[str, Any]) -> float | None:
    round_info = state.get("round")
    if not isinstance(round_info, dict):
        return None
    chips = round_info.get("chips")
    if isinstance(chips, (int, float)):
        return float(chips)
    return None


def _round_hands_played(state: Mapping[str, Any]) -> int | None:
    round_info = state.get("round")
    if not isinstance(round_info, dict):
        return None
    hands_played = round_info.get("hands_played")
    if isinstance(hands_played, int):
        return hands_played
    return None


def _poll_gamestate_until(
    client: BalatroBotClient,
    predicate,
    *,
    poll_interval_s: float,
    timeout_s: float,
    initial_state: JsonObject | None = None,
) -> JsonObject:
    deadline = time.monotonic() + max(0.0, timeout_s)
    state = initial_state if initial_state is not None else client.rpc("gamestate")
    while True:
        if predicate(state):
            return state
        if time.monotonic() >= deadline:
            return state
        if poll_interval_s > 0:
            time.sleep(poll_interval_s)
        state = client.rpc("gamestate")


def choose_cards_to_play_api(
    client: BalatroBotClient,
    state: Mapping[str, Any],
    *,
    save_path: str,
    poll_interval_s: float,
    settle_timeout_s: float,
    max_combos: int | None,
) -> list[int]:
    hand_area = state.get("hand")
    if not isinstance(hand_area, dict):
        return []

    hand_cards = hand_area.get("cards")
    if not isinstance(hand_cards, list) or not hand_cards:
        return []

    highlighted_limit = hand_area.get("highlighted_limit")
    max_cards = int(highlighted_limit) if isinstance(highlighted_limit, int) else 5
    max_cards = max(1, min(5, max_cards, len(hand_cards)))

    n_cards = len(hand_cards)
    combo_count = math.comb(n_cards, max_cards)

    if max_combos is not None and combo_count > max_combos:
        rng = random.Random()
        rng.seed(f"{state.get('seed')}-{state.get('ante_num')}-{state.get('round_num')}-{_round_chips(state)}")
        combos: set[tuple[int, ...]] = set()
        attempts = 0
        max_attempts = max_combos * 20
        while len(combos) < max_combos and attempts < max_attempts:
            combos.add(tuple(sorted(rng.sample(range(n_cards), max_cards))))
            attempts += 1
        combo_iter: Sequence[tuple[int, ...]] = tuple(combos)
    else:
        combo_iter = combinations(range(n_cards), max_cards)

    abs_save_path = os.path.abspath(save_path)
    save_dir = os.path.dirname(abs_save_path)
    if save_dir:
        os.makedirs(save_dir, exist_ok=True)

    client.rpc("save", {"path": abs_save_path})

    best_indices: tuple[int, ...] | None = None
    best_delta = float("-inf")

    try:
        for indices in combo_iter:
            client.rpc("load", {"path": abs_save_path})
            loaded = _poll_gamestate_until(
                client,
                lambda s: s.get("state") == "SELECTING_HAND",
                poll_interval_s=poll_interval_s,
                timeout_s=settle_timeout_s,
            )
            before_chips = _round_chips(loaded)
            before_hands_played = _round_hands_played(loaded)
            if before_chips is None or before_hands_played is None:
                continue

            after = client.rpc("play", {"cards": list(indices)})
            after = _poll_gamestate_until(
                client,
                lambda s: _round_hands_played(s) != before_hands_played,
                poll_interval_s=poll_interval_s,
                timeout_s=settle_timeout_s,
                initial_state=after,
            )
            after_chips = _round_chips(after)
            if after_chips is None:
                continue

            delta = after_chips - before_chips
            if delta > best_delta:
                best_delta = delta
                best_indices = indices
    finally:
        try:
            client.rpc("load", {"path": abs_save_path})
            _poll_gamestate_until(
                client,
                lambda s: s.get("state") == "SELECTING_HAND",
                poll_interval_s=poll_interval_s,
                timeout_s=settle_timeout_s,
            )
        except BalatroBotError:
            pass

    if best_indices is None:
        return choose_cards_to_play(state, strategy="best")

    return list(best_indices)


def play_game(
    client: BalatroBotClient,
    *,
    deck: str,
    stake: str,
    seed: str | None,
    strategy: str,
    buy_jokers: bool,
    poll_interval_s: float,
    sim_save_path: str,
    sim_settle_timeout_s: float,
    sim_max_combos: int | None,
    max_steps: int,
) -> bool:
    client.rpc("menu")
    start_params: JsonObject = {"deck": deck, "stake": stake}
    if seed is not None:
        start_params["seed"] = seed

    state = client.rpc("start", start_params)
    run_seed = state.get("seed")
    print(f"Started game (deck={deck}, stake={stake}, seed={run_seed})")

    steps = 0
    while state.get("state") != "GAME_OVER":
        steps += 1
        if steps > max_steps:
            raise BalatroBotError(f"Exceeded max steps ({max_steps}). Last state: {state.get('state')!r}")

        match state.get("state"):
            case "BLIND_SELECT":
                state = client.rpc("select")

            case "SELECTING_HAND":
                if strategy == "api":
                    try:
                        cards = choose_cards_to_play_api(
                            client,
                            state,
                            save_path=sim_save_path,
                            poll_interval_s=poll_interval_s,
                            settle_timeout_s=sim_settle_timeout_s,
                            max_combos=sim_max_combos,
                        )
                    except BalatroBotError as exc:
                        print(f"API strategy failed ({exc}); falling back to heuristic.")
                        cards = choose_cards_to_play(state, strategy="best")
                else:
                    cards = choose_cards_to_play(state, strategy=strategy)
                if not cards:
                    state = client.rpc("gamestate")
                else:
                    state = client.rpc("play", {"cards": cards})

            case "ROUND_EVAL":
                state = client.rpc("cash_out")

            case "SHOP":
                if buy_jokers:
                    state = _shop_buy_first_affordable_joker_then_next_round(client, state)
                else:
                    state = client.rpc("next_round")

            case "SMODS_BOOSTER_OPENED":
                state = client.rpc("pack", {"skip": True})

            case _:
                if poll_interval_s > 0:
                    time.sleep(poll_interval_s)
                state = client.rpc("gamestate")

    if state.get("won") is True:
        print(f"Victory! Final ante: {state.get('ante_num')}")
        return True

    print(f"Game over at ante {state.get('ante_num')}, round {state.get('round_num')}")
    return False


def _shop_buy_first_affordable_joker_then_next_round(
    client: BalatroBotClient, state: Mapping[str, Any]
) -> JsonObject:
    money = state.get("money")
    if not isinstance(money, (int, float)):
        return client.rpc("next_round")

    jokers = state.get("jokers")
    if not isinstance(jokers, dict):
        return client.rpc("next_round")

    limit = jokers.get("limit")
    count = jokers.get("count")
    if not isinstance(limit, int) or not isinstance(count, int):
        return client.rpc("next_round")

    slots_available = limit - count
    if slots_available <= 0:
        return client.rpc("next_round")

    shop_area = state.get("shop")
    if not isinstance(shop_area, dict):
        return client.rpc("next_round")

    shop_cards = shop_area.get("cards")
    if not isinstance(shop_cards, list) or not shop_cards:
        return client.rpc("next_round")

    for index, card in enumerate(shop_cards):
        if not isinstance(card, dict):
            continue

        key = card.get("key")
        if not (isinstance(key, str) and key.startswith("j_")):
            continue

        cost_info = card.get("cost")
        cost = cost_info.get("buy") if isinstance(cost_info, dict) else None
        if not isinstance(cost, (int, float)) or cost > money:
            continue

        try:
            return client.rpc("buy", {"card": index})
        except BalatroBotError:
            break

    return client.rpc("next_round")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="A minimal BalatroBot client script.")

    url_group = parser.add_mutually_exclusive_group()
    url_group.add_argument("--url", default=None, help="BalatroBot JSON-RPC endpoint URL")
    url_group.add_argument("--host", default=None, help="BalatroBot host (default from BALATROBOT_HOST)")

    parser.add_argument("--port", type=int, default=None, help="BalatroBot port (default from BALATROBOT_PORT)")
    parser.add_argument("--timeout", type=float, default=10.0, help="HTTP timeout in seconds")

    parser.add_argument("--deck", default="RED", help="Deck to use (e.g., RED, BLUE, ...)")
    parser.add_argument("--stake", default="WHITE", help="Stake to use (e.g., WHITE, RED, ...)")
    parser.add_argument("--seed", default=None, help="Optional run seed")

    parser.add_argument(
        "--strategy",
        choices=["first5", "best", "api"],
        default="best",
        help="Card selection strategy during SELECTING_HAND",
    )
    parser.add_argument(
        "--sim-save-path",
        default=os.path.join("saves", f"_bot_sim_{os.getpid()}.jkr"),
        help="Save path used by --strategy api (overwritten as needed).",
    )
    parser.add_argument(
        "--sim-settle-timeout",
        type=float,
        default=2.0,
        help="Seconds to wait for save/load/play to settle when using --strategy api.",
    )
    parser.add_argument(
        "--sim-max-combos",
        type=int,
        default=None,
        help="Limit combinations tested per hand for --strategy api (random sample when limited).",
    )
    parser.add_argument("--buy-jokers", action="store_true", help="Buy the first affordable joker each shop")
    parser.add_argument("--poll-interval", type=float, default=0.05, help="Sleep time between gamestate polls")
    parser.add_argument("--max-steps", type=int, default=50_000, help="Safety limit to prevent infinite loops")
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()

    if args.url is not None:
        url = args.url
    else:
        host = args.host or os.environ.get("BALATROBOT_HOST", "127.0.0.1")
        port = args.port or int(os.environ.get("BALATROBOT_PORT", "12346"))
        url = f"http://{host}:{port}"

    client = BalatroBotClient(url, timeout_s=args.timeout)
    play_game(
        client,
        deck=args.deck,
        stake=args.stake,
        seed=args.seed,
        strategy=args.strategy,
        buy_jokers=args.buy_jokers,
        poll_interval_s=args.poll_interval,
        sim_save_path=args.sim_save_path,
        sim_settle_timeout_s=args.sim_settle_timeout,
        sim_max_combos=args.sim_max_combos,
        max_steps=args.max_steps,
    )
