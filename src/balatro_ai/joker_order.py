from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Mapping

from balatro_ai.actions import Action
from balatro_ai.cards import card_key, card_text, card_tokens
from balatro_ai.gs import gs_jokers, gs_state
from balatro_ai.joker_rules import joker_rule
from balatro_ai.token_utils import has_x_token

if TYPE_CHECKING:
    from balatro_ai.policy import PolicyContext

logger = logging.getLogger(__name__)


_ECON_TOKENS = {"money", "interest", "discount", "coupon", "sell", "shop"}
_CHIPS_TOKENS = {"chips", "chip", "bonus"}
_MULT_TOKENS = {"mult", "multiplier", "mults"}
_XMULT_TOKENS = {"xmult", "times", "retrigger", "again"}


def joker_text(j: dict) -> str:
    """Return lowercase text for a joker, preferring label then key."""
    if not isinstance(j, Mapping):
        return ""
    return card_text(j)


def classify_joker_bucket(text: str, key: str | None = None) -> int:
    """Return the bucket index for the provided joker text."""
    rule = joker_rule(key)
    if rule is not None:
        return _category_bucket(rule.category)
    if not text:
        return 2
    lowered = text.lower()
    tokens = card_tokens(lowered)
    if "$" in lowered or tokens & _ECON_TOKENS:
        return 0
    if tokens & _CHIPS_TOKENS:
        return 1
    if tokens & _XMULT_TOKENS or _has_x_token(tokens):
        return 3
    if tokens & _MULT_TOKENS:
        return 2
    return 2


def compute_joker_permutation(jokers: list[dict]) -> list[int]:
    """Compute a stable permutation ordering jokers by bucket."""
    indexed = list(enumerate(jokers))
    ordered = sorted(
        indexed,
        key=lambda item: classify_joker_bucket(joker_text(item[1]), card_key(item[1])),
    )
    return [index for index, _ in ordered]


def maybe_reorder_jokers(gs: Mapping[str, Any], ctx: "PolicyContext") -> Action | None:
    """Return a rearrange action when jokers should be reordered."""
    state = gs_state(gs)
    if state not in {"SHOP", "SELECTING_HAND", "SMODS_BOOSTER_OPENED"}:
        logger.debug("maybe_reorder_jokers: state=%s not eligible", state)
        return None
    jokers = gs_jokers(gs)
    if len(jokers) < 2:
        logger.debug("maybe_reorder_jokers: state=%s jokers=%s (no reorder needed)", state, len(jokers))
        return None
    permutation = compute_joker_permutation(jokers)
    if permutation == list(range(len(jokers))):
        logger.debug("maybe_reorder_jokers: already ordered (perm=%s)", permutation)
        return None
    perm_hash = tuple(permutation)
    if ctx.memory.get("last_joker_perm_hash") == perm_hash:
        logger.debug("maybe_reorder_jokers: repeated perm hash (perm=%s) -> skip", permutation)
        return None
    if logger.isEnabledFor(logging.DEBUG):
        buckets = [classify_joker_bucket(joker_text(j), card_key(j)) for j in jokers]
        logger.debug(
            "maybe_reorder_jokers: state=%s buckets=%s perm=%s",
            state,
            buckets,
            permutation,
        )
    ctx.memory["last_joker_perm_hash"] = perm_hash
    return Action(kind="rearrange", params={"jokers": permutation})


def _has_x_token(tokens: set[str]) -> bool:
    return has_x_token(tokens, slice_after_first_char=1)


def _category_bucket(category: str) -> int:
    if category == "econ":
        return 0
    if category == "chips":
        return 1
    if category == "mult":
        return 2
    if category == "xmult":
        return 3
    return 2
