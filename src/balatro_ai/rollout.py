from __future__ import annotations

import math
import os
import tempfile
import uuid
from dataclasses import dataclass
from itertools import combinations
from typing import Any, Iterable, Mapping, TYPE_CHECKING

from balatro_ai.actions import Action
from balatro_ai.build_intent import BuildIntent, infer_intent
from balatro_ai.cards import card_rank, card_suit
from balatro_ai.config import Config
from balatro_ai.gs import (
    gs_blind_score,
    gs_discards_left,
    gs_hand_cards,
    gs_hands_left,
    gs_jokers,
    gs_money,
    gs_round_chips,
    gs_state,
)
from balatro_ai.poker_eval import HandType, evaluate_candidate
from balatro_ai.rpc import BalatroRPC, BalatroRPCError

if TYPE_CHECKING:
    from balatro_ai.policy import PolicyContext


@dataclass(frozen=True)
class _ScoredCandidate:
    action: Action
    score: int


@dataclass(frozen=True)
class _EvalResult:
    action: Action
    reward: float


def rollout_step(
    gs: Mapping[str, Any],
    cfg: Config,
    ctx: "PolicyContext",
    rpc: BalatroRPC,
) -> dict:
    """Evaluate play/discard candidates using save/load and apply the best action."""
    if gs_state(gs) != "SELECTING_HAND":
        raise ValueError(f"rollout_step requires SELECTING_HAND, got {gs_state(gs)}")
    hand_cards = gs_hand_cards(gs)
    if not hand_cards:
        return rpc.gamestate()
    intent = _intent_from_ctx(gs, ctx)
    play_candidates = _generate_play_candidates(hand_cards, gs_jokers(gs), intent, cfg.rollout_k)
    discard_candidates = _generate_discard_candidates(hand_cards, intent, cfg, gs)
    save_path = _save_path()
    before_chips = gs_round_chips(gs)
    before_money = gs_money(gs)
    try:
        rpc.save(save_path)
    except BalatroRPCError:
        fallback = play_candidates[0] if play_candidates else Action(kind="gamestate", params={})
        return _apply_action(rpc, fallback)
    try:
        candidates = [candidate.action for candidate in play_candidates] + discard_candidates
        best = _evaluate_candidates(
            rpc,
            save_path,
            candidates,
            intent,
            cfg,
            before_chips,
            before_money,
        )
        if best is None:
            if play_candidates:
                return _apply_action(rpc, play_candidates[0].action)
            return rpc.gamestate()
        rpc.load(save_path)
        return _apply_action(rpc, best.action)
    finally:
        try:
            os.remove(save_path)
        except OSError:
            pass


def _apply_action(rpc: BalatroRPC, action: Action) -> dict:
    if action.kind == "play":
        return rpc.play(cards=action.params.get("cards", []))
    if action.kind == "discard":
        return rpc.discard(cards=action.params.get("cards", []))
    if action.kind == "gamestate":
        return rpc.gamestate()
    raise BalatroRPCError(
        code=-32601,
        message="Unsupported rollout action",
        data={"action": action.kind},
        method=action.kind,
        params=action.params,
    )


def _generate_play_candidates(
    hand_cards: list[dict],
    jokers: list[dict],
    intent: BuildIntent,
    rollout_k: int,
) -> list[_ScoredCandidate]:
    candidates: list[_ScoredCandidate] = []
    hand_size = len(hand_cards)
    priority = _priority_indices(hand_cards)
    for size in range(5, 0, -1):
        if size > hand_size:
            continue
        combos = _combinations_bounded(list(range(hand_size)), size, max_count=80, priority=priority)
        for combo in combos:
            cards = [hand_cards[i] for i in combo]
            evaluation = evaluate_candidate(cards, jokers)
            score = _score_candidate(evaluation, intent)
            candidates.append(
                _ScoredCandidate(action=Action(kind="play", params={"cards": list(combo)}), score=score)
            )
    candidates.sort(key=lambda candidate: candidate.score, reverse=True)
    return candidates[: max(1, rollout_k)]


def _generate_discard_candidates(
    hand_cards: list[dict],
    intent: BuildIntent,
    cfg: Config,
    gs: Mapping[str, Any],
) -> list[Action]:
    if gs_discards_left(gs) <= 0:
        return []
    indices = _discard_priority_indices(hand_cards, intent)
    if not indices:
        return []
    max_candidates = max(0, cfg.discard_m)
    results: list[Action] = []
    for size in range(1, 4):
        for combo in combinations(indices, size):
            results.append(Action(kind="discard", params={"cards": list(combo)}))
            if len(results) >= max_candidates:
                return results
    return results


def _evaluate_candidates(
    rpc: BalatroRPC,
    save_path: str,
    actions: list[Action],
    intent: BuildIntent,
    cfg: Config,
    before_chips: int | None,
    before_money: int,
) -> _EvalResult | None:
    best: _EvalResult | None = None
    for action in actions:
        try:
            rpc.load(save_path)
            if action.kind == "discard":
                reward, terminal = _evaluate_discard_candidate(
                    rpc,
                    action,
                    intent,
                    cfg,
                    before_chips,
                    before_money,
                )
            else:
                gs2 = _apply_action(rpc, action)
                reward = _reward(gs2, before_chips, before_money)
                terminal = gs_state(gs2) == "ROUND_EVAL"
        except BalatroRPCError:
            reward = -1_000_000_000.0
            terminal = False
        if best is None or reward > best.reward:
            best = _EvalResult(action=action, reward=reward)
        if terminal:
            return best
    return best


def _evaluate_discard_candidate(
    rpc: BalatroRPC,
    action: Action,
    intent: BuildIntent,
    cfg: Config,
    before_chips: int | None,
    before_money: int,
) -> tuple[float, bool]:
    gs2 = _apply_action(rpc, action)
    state = gs_state(gs2)
    if state in {"ROUND_EVAL", "GAME_OVER"}:
        return _reward(gs2, before_chips, before_money), True
    hand_cards = gs_hand_cards(gs2)
    if not hand_cards:
        return _reward(gs2, before_chips, before_money), False
    play_candidates = _generate_play_candidates(hand_cards, gs_jokers(gs2), intent, cfg.rollout_k)
    if not play_candidates:
        return _reward(gs2, before_chips, before_money), False
    best_play = play_candidates[0].action
    gs3 = _apply_action(rpc, best_play)
    return _reward(gs3, before_chips, before_money), gs_state(gs3) == "ROUND_EVAL"


def _reward(gs: Mapping[str, Any], before_chips: int | None, before_money: int) -> float:
    reward = 0.0
    state = gs_state(gs)
    if state == "ROUND_EVAL":
        reward += 1_000_000.0
    if state == "GAME_OVER":
        reward -= 1_000_000.0
    blind_score = gs_blind_score(gs)
    round_chips = gs_round_chips(gs)
    if blind_score and before_chips is not None and round_chips is not None:
        delta = round_chips - before_chips
        reward += 50.0 * delta / max(1, blind_score)
    reward += 50.0 * gs_hands_left(gs)
    reward += 10.0 * gs_discards_left(gs)
    reward += float(gs_money(gs) - before_money)
    return reward


def _intent_from_ctx(gs: Mapping[str, Any], ctx: "PolicyContext") -> BuildIntent:
    memory_intent = ctx.memory.get("intent")
    intent = _coerce_intent(memory_intent)
    if intent is not None:
        return intent
    inferred, _ = infer_intent(gs)
    return inferred


def _coerce_intent(value: Any) -> BuildIntent | None:
    if isinstance(value, BuildIntent):
        return value
    if isinstance(value, str):
        try:
            return BuildIntent[value.upper()]
        except KeyError:
            return None
    return None


def _score_candidate(evaluation: Mapping[str, Any], intent: BuildIntent) -> int:
    hand_type = evaluation.get("hand_type", HandType.HIGH_CARD)
    if not isinstance(hand_type, HandType):
        hand_type = HandType.HIGH_CARD
    tier_score = _hand_tier(hand_type) * 1000
    intent_bonus = _intent_bonus(hand_type, intent)
    features = evaluation.get("features", {})
    flush_count = _safe_int(features.get("flush_count"))
    max_dupe = _safe_int(features.get("max_dupe"))
    straight_quality = _safe_int(features.get("straight_quality"))
    high_rank_sum = _safe_int(features.get("high_rank_sum"))
    feature_score = flush_count * 5 + max_dupe * 10 + straight_quality * 6 + high_rank_sum
    return tier_score + intent_bonus + feature_score


def _intent_bonus(hand_type: HandType, intent: BuildIntent) -> int:
    if intent == BuildIntent.FLUSH and hand_type in {HandType.FLUSH, HandType.STRAIGHT_FLUSH}:
        return 500
    if intent == BuildIntent.STRAIGHT and hand_type in {HandType.STRAIGHT, HandType.STRAIGHT_FLUSH}:
        return 500
    if intent == BuildIntent.PAIRS and hand_type in {
        HandType.PAIR,
        HandType.TWO_PAIR,
        HandType.THREE_KIND,
        HandType.FULL_HOUSE,
        HandType.FOUR_KIND,
    }:
        return 500
    return 0


def _hand_tier(hand_type: HandType) -> int:
    order = [
        HandType.HIGH_CARD,
        HandType.PAIR,
        HandType.TWO_PAIR,
        HandType.THREE_KIND,
        HandType.STRAIGHT,
        HandType.FLUSH,
        HandType.FULL_HOUSE,
        HandType.FOUR_KIND,
        HandType.STRAIGHT_FLUSH,
    ]
    try:
        return order.index(hand_type) + 1
    except ValueError:
        return 1


def _discard_priority_indices(hand_cards: list[dict], intent: BuildIntent) -> list[int]:
    if intent == BuildIntent.FLUSH:
        return _discard_for_flush(hand_cards)
    if intent == BuildIntent.STRAIGHT:
        return _discard_for_straight(hand_cards)
    if intent == BuildIntent.PAIRS:
        return _discard_for_pairs(hand_cards)
    return _discard_low_ranks(hand_cards)


def _discard_for_flush(hand_cards: list[dict]) -> list[int]:
    suits = [card_suit(card) for card in hand_cards]
    counts: dict[str, int] = {}
    for suit in suits:
        if not suit:
            continue
        counts[suit] = counts.get(suit, 0) + 1
    majority = max(counts.items(), key=lambda item: item[1])[0] if counts else None
    off_suit = [i for i, suit in enumerate(suits) if suit != majority]
    if off_suit:
        return off_suit
    return _discard_low_ranks(hand_cards)


def _discard_for_straight(hand_cards: list[dict]) -> list[int]:
    ranks = [card_rank(card) for card in hand_cards]
    target = _best_straight_ranks(ranks)
    if not target:
        return _discard_low_ranks(hand_cards)
    target_set = set(target)
    indices = []
    for index, rank in enumerate(ranks):
        normalized = 1 if rank == 14 and 1 in target_set else rank
        if normalized not in target_set:
            indices.append(index)
    if indices:
        return indices
    return _discard_low_ranks(hand_cards)


def _discard_for_pairs(hand_cards: list[dict]) -> list[int]:
    ranks = [card_rank(card) for card in hand_cards]
    counts: dict[int, int] = {}
    for rank in ranks:
        counts[rank] = counts.get(rank, 0) + 1
    indices = [i for i, rank in enumerate(ranks) if counts.get(rank, 0) == 1]
    if indices:
        return indices
    return _discard_low_ranks(hand_cards)


def _discard_low_ranks(hand_cards: list[dict]) -> list[int]:
    ranks = [card_rank(card) for card in hand_cards]
    ranked = sorted(range(len(ranks)), key=lambda idx: ranks[idx])
    return ranked


def _best_straight_ranks(ranks: list[int]) -> list[int]:
    unique = sorted({rank for rank in ranks if rank > 0})
    if not unique:
        return []
    if 14 in unique:
        unique.append(1)
        unique = sorted(set(unique))
    best: list[int] = []
    for start in unique:
        end = start + 4
        window = [rank for rank in range(start, end + 1)]
        if all(rank in unique for rank in window):
            if not best or end > max(best):
                best = window
    return best


def _combinations_bounded(
    indices: list[int],
    size: int,
    max_count: int,
    priority: list[int] | None = None,
) -> Iterable[tuple[int, ...]]:
    total = math.comb(len(indices), size)
    if total <= max_count:
        return list(combinations(indices, size))
    priority_order = priority or indices
    selected: list[tuple[int, ...]] = []
    seen: set[tuple[int, ...]] = set()
    for order in _priority_orders(priority_order):
        stride = max(1, total // max_count)
        for idx, combo in enumerate(combinations(order, size)):
            if idx % stride != 0:
                continue
            normalized = tuple(sorted(combo))
            if normalized in seen:
                continue
            seen.add(normalized)
            selected.append(normalized)
            if len(selected) >= max_count:
                return selected
    return selected


def _save_path() -> str:
    filename = f"balatrobot_rollout_{uuid.uuid4().hex}.jkr"
    return os.path.join(tempfile.gettempdir(), filename)


def _safe_int(value: Any) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return 0


def _priority_indices(hand_cards: list[dict]) -> list[int]:
    suits = [card_suit(card) for card in hand_cards]
    suit_counts: dict[str, int] = {}
    for suit in suits:
        if not suit:
            continue
        suit_counts[suit] = suit_counts.get(suit, 0) + 1
    ranks = [card_rank(card) for card in hand_cards]
    rank_counts: dict[int, int] = {}
    for rank in ranks:
        rank_counts[rank] = rank_counts.get(rank, 0) + 1
    def score_index(idx: int) -> tuple[int, int, int]:
        suit = suits[idx]
        suit_score = suit_counts.get(suit, 0) if suit else 0
        rank = ranks[idx]
        dup_score = rank_counts.get(rank, 0)
        return (dup_score, suit_score, rank)
    return sorted(range(len(hand_cards)), key=score_index, reverse=True)


def _priority_orders(order: list[int]) -> list[list[int]]:
    orders = [order]
    reversed_order = list(reversed(order))
    if reversed_order != order:
        orders.append(reversed_order)
    return orders
