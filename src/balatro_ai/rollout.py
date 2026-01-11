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
from balatro_ai.hand_stats import (
    majority_suit_from_suits,
    max_rank_count_from_ranks,
    max_straight_window_count_from_ranks,
    max_suit_count,
    rank_counts_from_ranks,
    suit_counts_from_suits,
)
from balatro_ai.poker_eval import HandType, evaluate_candidate
from balatro_ai.rpc import BalatroRPC, BalatroRPCError

if TYPE_CHECKING:
    from balatro_ai.policy import PolicyContext


JSONRPC_UNSUPPORTED_ACTION_CODE = -32601

ZERO = 0
ONE = 1
FIRST_INDEX = 0

ACE_HIGH_RANK = 14
ACE_LOW_RANK = 1
RANK_UNKNOWN = 0
STRAIGHT_WINDOW_SPAN = 4
STRAIGHT_WINDOW_INCLUSIVE_OFFSET = 1

DISCARD_PRIORITY_POSITION_WEIGHT = 10
DISCARD_BASE_SCORE = 900
DISCARD_SIZE_WEIGHT = 25

COMBINATIONS_MAX_COUNT = 80
MIN_ROLLOUT_CANDIDATES = 1

DISCARD_MIN_SIZE = 1
DISCARD_MAX_SIZE_EXCLUSIVE = 4

EVAL_FAILURE_REWARD = -1_000_000_000.0

REWARD_INITIAL = 0.0
REWARD_ROUND_EVAL_BONUS = 1_000_000.0
REWARD_GAME_OVER_PENALTY = 1_000_000.0
REWARD_CHIPS_DELTA_WEIGHT = 50.0
REWARD_HANDS_LEFT_WEIGHT = 50.0
REWARD_DISCARDS_LEFT_WEIGHT = 10.0
REWARD_BLIND_SCORE_MIN = 1

TIER_SCORE_MULTIPLIER = 1000
INTENT_BONUS_SCORE = 500
INTENT_BONUS_NONE = 0

FEATURE_FLUSH_COUNT_WEIGHT = 5
FEATURE_MAX_DUPE_WEIGHT = 10
FEATURE_STRAIGHT_QUALITY_WEIGHT = 6

HAND_MAX_PLAY_SIZE = 5
HAND_TIER_BASE = 1

MIN_SIZE_DEFAULT = 1
MIN_SIZE_WEAK = 2
MIN_SIZE_MEDIUM = 3
MIN_SIZE_STRONG = 4



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
        fallback = _fallback_action_on_save_error(
            play_candidates,
            discard_candidates,
            hand_cards,
            intent,
        )
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
                return _apply_action(rpc, play_candidates[FIRST_INDEX].action)
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
        code=JSONRPC_UNSUPPORTED_ACTION_CODE,
        message="Unsupported rollout action",
        data={"action": action.kind},
        method=action.kind,
        params=action.params,
    )


def _fallback_action_on_save_error(
    play_candidates: list[_ScoredCandidate],
    discard_candidates: list[Action],
    hand_cards: list[dict],
    intent: BuildIntent,
) -> Action:
    best_play = play_candidates[FIRST_INDEX] if play_candidates else None
    best_discard = _best_discard_candidate(discard_candidates, hand_cards, intent)
    if best_discard is not None and (best_play is None or best_discard.score > best_play.score):
        return best_discard.action
    if best_play is not None:
        return best_play.action
    if best_discard is not None:
        return best_discard.action
    return Action(kind="gamestate", params={})


def _best_discard_candidate(
    discard_candidates: list[Action],
    hand_cards: list[dict],
    intent: BuildIntent,
) -> _ScoredCandidate | None:
    if not discard_candidates:
        return None
    priority = _discard_priority_indices(hand_cards, intent)
    weights = {
        idx: (len(priority) - pos) * DISCARD_PRIORITY_POSITION_WEIGHT
        for pos, idx in enumerate(priority)
    }
    best: _ScoredCandidate | None = None
    for action in discard_candidates:
        cards = action.params.get("cards", [])
        if not isinstance(cards, list) or not cards:
            continue
        score = DISCARD_BASE_SCORE + DISCARD_SIZE_WEIGHT * len(cards)
        for card in cards:
            score += weights.get(card, ZERO)
        candidate = _ScoredCandidate(action=action, score=score)
        if best is None or candidate.score > best.score:
            best = candidate
    return best


def _generate_play_candidates(
    hand_cards: list[dict],
    jokers: list[dict],
    intent: BuildIntent,
    rollout_k: int,
) -> list[_ScoredCandidate]:
    candidates: list[_ScoredCandidate] = []
    hand_size = len(hand_cards)
    priority = _priority_indices(hand_cards)
    eval_cache: dict[tuple[int, ...], Mapping[str, Any]] = {}
    for size in _candidate_sizes(hand_cards, intent):
        if size > hand_size:
            continue
        combos = _combinations_bounded(
            list(range(hand_size)),
            size,
            max_count=COMBINATIONS_MAX_COUNT,
            priority=priority,
        )
        for combo in combos:
            combo_key = tuple(combo)
            evaluation = eval_cache.get(combo_key)
            if evaluation is None:
                cards = [hand_cards[i] for i in combo]
                evaluation = evaluate_candidate(cards, jokers)
                eval_cache[combo_key] = evaluation
            score = _score_candidate(evaluation, intent)
            candidates.append(
                _ScoredCandidate(action=Action(kind="play", params={"cards": list(combo)}), score=score)
            )
    candidates.sort(key=lambda candidate: candidate.score, reverse=True)
    return candidates[: max(MIN_ROLLOUT_CANDIDATES, rollout_k)]


def _generate_discard_candidates(
    hand_cards: list[dict],
    intent: BuildIntent,
    cfg: Config,
    gs: Mapping[str, Any],
) -> list[Action]:
    if gs_discards_left(gs) <= ZERO:
        return []
    indices = _discard_priority_indices(hand_cards, intent)
    if not indices:
        return []
    max_candidates = max(ZERO, cfg.discard_m)
    results: list[Action] = []
    for size in range(DISCARD_MIN_SIZE, DISCARD_MAX_SIZE_EXCLUSIVE):
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
            reward = EVAL_FAILURE_REWARD
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
    best_play = play_candidates[FIRST_INDEX].action
    gs3 = _apply_action(rpc, best_play)
    return _reward(gs3, before_chips, before_money), gs_state(gs3) == "ROUND_EVAL"


def _reward(gs: Mapping[str, Any], before_chips: int | None, before_money: int) -> float:
    reward = REWARD_INITIAL
    state = gs_state(gs)
    if state == "ROUND_EVAL":
        reward += REWARD_ROUND_EVAL_BONUS
    if state == "GAME_OVER":
        reward -= REWARD_GAME_OVER_PENALTY
    blind_score = gs_blind_score(gs)
    round_chips = gs_round_chips(gs)
    if blind_score and before_chips is not None and round_chips is not None:
        delta = round_chips - before_chips
        reward += REWARD_CHIPS_DELTA_WEIGHT * delta / max(REWARD_BLIND_SCORE_MIN, blind_score)
    reward += REWARD_HANDS_LEFT_WEIGHT * gs_hands_left(gs)
    reward += REWARD_DISCARDS_LEFT_WEIGHT * gs_discards_left(gs)
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
    tier_score = _hand_tier(hand_type) * TIER_SCORE_MULTIPLIER
    intent_bonus = _intent_bonus(hand_type, intent)
    features = evaluation.get("features", {})
    flush_count = _safe_int(features.get("flush_count"))
    max_dupe = _safe_int(features.get("max_dupe"))
    straight_quality = _safe_int(features.get("straight_quality"))
    high_rank_sum = _safe_int(features.get("high_rank_sum"))
    feature_score = (
        flush_count * FEATURE_FLUSH_COUNT_WEIGHT
        + max_dupe * FEATURE_MAX_DUPE_WEIGHT
        + straight_quality * FEATURE_STRAIGHT_QUALITY_WEIGHT
        + high_rank_sum
    )
    return tier_score + intent_bonus + feature_score


def _intent_bonus(hand_type: HandType, intent: BuildIntent) -> int:
    if intent == BuildIntent.FLUSH and hand_type in {HandType.FLUSH, HandType.STRAIGHT_FLUSH}:
        return INTENT_BONUS_SCORE
    if intent == BuildIntent.STRAIGHT and hand_type in {HandType.STRAIGHT, HandType.STRAIGHT_FLUSH}:
        return INTENT_BONUS_SCORE
    if intent == BuildIntent.PAIRS and hand_type in {
        HandType.PAIR,
        HandType.TWO_PAIR,
        HandType.THREE_KIND,
        HandType.FULL_HOUSE,
        HandType.FOUR_KIND,
    }:
        return INTENT_BONUS_SCORE
    return INTENT_BONUS_NONE


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
        return order.index(hand_type) + HAND_TIER_BASE
    except ValueError:
        return HAND_TIER_BASE


def _discard_priority_indices(hand_cards: list[dict], intent: BuildIntent) -> list[int]:
    if intent == BuildIntent.FLUSH:
        return _discard_for_flush(hand_cards)
    if intent == BuildIntent.STRAIGHT:
        return _discard_for_straight(hand_cards)
    if intent == BuildIntent.PAIRS:
        return _discard_for_pairs(hand_cards)
    return _discard_low_ranks(hand_cards)


def _candidate_sizes(hand_cards: list[dict], intent: BuildIntent) -> list[int]:
    hand_size = len(hand_cards)
    max_size = min(HAND_MAX_PLAY_SIZE, hand_size)
    if max_size <= ZERO:
        return []
    sizes = list(range(max_size, ZERO, -ONE))
    min_size = MIN_SIZE_DEFAULT
    if intent == BuildIntent.FLUSH:
        max_suit = _max_suit_count(hand_cards)
        if max_suit >= MIN_SIZE_STRONG:
            min_size = MIN_SIZE_STRONG
        elif max_suit == MIN_SIZE_MEDIUM:
            min_size = MIN_SIZE_MEDIUM
        else:
            min_size = MIN_SIZE_WEAK
    elif intent == BuildIntent.STRAIGHT:
        max_window = _max_straight_window(hand_cards)
        if max_window >= MIN_SIZE_STRONG:
            min_size = MIN_SIZE_STRONG
        elif max_window == MIN_SIZE_MEDIUM:
            min_size = MIN_SIZE_MEDIUM
        else:
            min_size = MIN_SIZE_WEAK
    elif intent == BuildIntent.PAIRS:
        min_size = MIN_SIZE_WEAK
    filtered = [size for size in sizes if size >= min_size]
    return filtered or sizes


def _max_suit_count(hand_cards: list[dict]) -> int:
    return max_suit_count(hand_cards)


def _max_dup_count(hand_cards: list[dict]) -> int:
    return max_rank_count_from_ranks(
        (card_rank(card) for card in hand_cards),
        include_unknown=False,
        unknown_rank=RANK_UNKNOWN,
    )


def _max_straight_window(hand_cards: list[dict]) -> int:
    return max_straight_window_count_from_ranks(
        (card_rank(card) for card in hand_cards),
        window_span=STRAIGHT_WINDOW_SPAN,
        ace_high_rank=ACE_HIGH_RANK,
        ace_low_rank=ACE_LOW_RANK,
        unknown_rank=RANK_UNKNOWN,
    )


def _discard_for_flush(hand_cards: list[dict]) -> list[int]:
    suits = [card_suit(card) for card in hand_cards]
    majority = majority_suit_from_suits(suits)
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
        normalized = ACE_LOW_RANK if rank == ACE_HIGH_RANK and ACE_LOW_RANK in target_set else rank
        if normalized not in target_set:
            indices.append(index)
    if indices:
        return indices
    return _discard_low_ranks(hand_cards)


def _discard_for_pairs(hand_cards: list[dict]) -> list[int]:
    ranks = [card_rank(card) for card in hand_cards]
    counts = rank_counts_from_ranks(ranks)
    indices = [i for i, rank in enumerate(ranks) if counts.get(rank, ZERO) == ONE]
    if indices:
        return indices
    return _discard_low_ranks(hand_cards)


def _discard_low_ranks(hand_cards: list[dict]) -> list[int]:
    ranks = [card_rank(card) for card in hand_cards]
    ranked = sorted(range(len(ranks)), key=lambda idx: ranks[idx])
    return ranked


def _best_straight_ranks(ranks: list[int]) -> list[int]:
    unique = sorted({rank for rank in ranks if rank > RANK_UNKNOWN})
    if not unique:
        return []
    if ACE_HIGH_RANK in unique:
        unique.append(ACE_LOW_RANK)
        unique = sorted(set(unique))
    best: list[int] = []
    for start in unique:
        end = start + STRAIGHT_WINDOW_SPAN
        window = [rank for rank in range(start, end + STRAIGHT_WINDOW_INCLUSIVE_OFFSET)]
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
        stride = max(ONE, total // max_count)
        for idx, combo in enumerate(combinations(order, size)):
            if idx % stride != ZERO:
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
    return ZERO


def _priority_indices(hand_cards: list[dict]) -> list[int]:
    suits = [card_suit(card) for card in hand_cards]
    suit_counts = suit_counts_from_suits(suits)
    ranks = [card_rank(card) for card in hand_cards]
    rank_counts = rank_counts_from_ranks(ranks)
    def score_index(idx: int) -> tuple[int, int, int]:
        suit = suits[idx]
        suit_score = suit_counts.get(suit, ZERO) if suit else ZERO
        rank = ranks[idx]
        dup_score = rank_counts.get(rank, ZERO)
        return (dup_score, suit_score, rank)
    return sorted(range(len(hand_cards)), key=score_index, reverse=True)


def _priority_orders(order: list[int]) -> list[list[int]]:
    orders = [order]
    reversed_order = list(reversed(order))
    if reversed_order != order:
        orders.append(reversed_order)
    return orders
