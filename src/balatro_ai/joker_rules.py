from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class JokerRule:
    """Data-driven hints for known joker keys.

    This module is intentionally "configuration-first": adding support for new jokers
    should primarily be a matter of extending `_RULES`, not changing scoring logic.

    Fields are optional so unknown/new content can safely fall back to text-token
    heuristics in higher-level policies.
    """

    category: str
    effect_type: str = ""
    base_score: int | None = None
    flat_bonus: int = 0
    intent_bonus: tuple[tuple[str, int], ...] = ()
    tags: frozenset[str] = frozenset()

    def resolved_base_score(self, *, category_scores: Mapping[str, int]) -> int:
        if self.base_score is not None:
            return self.base_score
        return category_scores.get(self.category, category_scores.get("default", 0))

    def bonus_for_intent(self, intent: str) -> int:
        for intent_key, bonus in self.intent_bonus:
            if intent_key == intent:
                return bonus
        return 0


JOKER_CATEGORY_BASE_SCORES: dict[str, int] = {
    "xmult": 100,
    "mult": 50,
    "chips": 20,
    "econ": 0,
    "default": 0,
}

_ALIASES: dict[str, str] = {
    # Historical misspelling seen in some builds.
    "j_gluttenous_joker": "j_gluttonous_joker",
}


_RULES: dict[str, JokerRule] = {
    "j_joker": JokerRule(category="mult", effect_type="mult"),
    "j_greedy_joker": JokerRule(category="mult", effect_type="mult"),
    "j_lusty_joker": JokerRule(category="mult", effect_type="mult"),
    "j_wrathful_joker": JokerRule(category="mult", effect_type="mult"),
    "j_gluttenous_joker": JokerRule(category="mult", effect_type="mult"),
    "j_gluttonous_joker": JokerRule(category="mult", effect_type="mult"),
    "j_jolly": JokerRule(
        category="mult", effect_type="mult", tags=frozenset({"pairs_payoff"})
    ),
    "j_zany": JokerRule(
        category="mult", effect_type="mult", tags=frozenset({"pairs_payoff"})
    ),
    "j_mad": JokerRule(
        category="mult", effect_type="mult", tags=frozenset({"pairs_payoff"})
    ),
    "j_crazy": JokerRule(
        category="mult", effect_type="mult", tags=frozenset({"straight_payoff"})
    ),
    "j_droll": JokerRule(
        category="mult", effect_type="mult", tags=frozenset({"flush_payoff"})
    ),
    "j_half": JokerRule(category="mult", effect_type="mult"),
    "j_misprint": JokerRule(category="mult", effect_type="mult"),
    "j_abstract": JokerRule(category="mult", effect_type="mult"),
    "j_raised_fist": JokerRule(category="mult", effect_type="mult"),
    "j_fibonacci": JokerRule(category="mult", effect_type="mult"),
    "j_sly": JokerRule(
        category="chips", effect_type="chips", tags=frozenset({"pairs_payoff"})
    ),
    "j_wily": JokerRule(
        category="chips", effect_type="chips", tags=frozenset({"pairs_payoff"})
    ),
    "j_clever": JokerRule(
        category="chips", effect_type="chips", tags=frozenset({"pairs_payoff"})
    ),
    "j_devious": JokerRule(
        category="chips", effect_type="chips", tags=frozenset({"straight_payoff"})
    ),
    "j_crafty": JokerRule(
        category="chips", effect_type="chips", tags=frozenset({"flush_payoff"})
    ),
    "j_banner": JokerRule(category="chips", effect_type="chips"),
    "j_scary_face": JokerRule(category="chips", effect_type="chips"),
    "j_stencil": JokerRule(category="xmult", effect_type="xmult"),
    "j_loyalty_card": JokerRule(category="xmult", effect_type="xmult"),
    "j_steel_joker": JokerRule(category="xmult", effect_type="xmult"),
    "j_mime": JokerRule(category="xmult", effect_type="xmult"),
    "j_dusk": JokerRule(category="xmult", effect_type="xmult"),
    "j_hack": JokerRule(category="xmult", effect_type="xmult"),
    "j_chaos": JokerRule(
        category="econ",
        effect_type="reroll",
        flat_bonus=20,
        tags=frozenset({"reroll_engine"}),
    ),
    "j_flash": JokerRule(
        category="mult",
        effect_type="mult_scaling",
        flat_bonus=10,
        tags=frozenset({"reroll_engine"}),
    ),
    "j_credit_card": JokerRule(category="econ", effect_type="econ"),
    "j_delayed_grat": JokerRule(category="econ", effect_type="econ"),
    # Utility/support jokers: keep category non-scoring (default=0) and express value via tags/intent.
    "j_smeared": JokerRule(
        category="utility",
        effect_type="suit_support",
        base_score=0,
        intent_bonus=(("FLUSH", 60), ("STRAIGHT", -40)),
        tags=frozenset({"suit_focus", "smeared"}),
    ),
    "j_four_fingers": JokerRule(
        category="utility",
        effect_type="straight_support",
        base_score=0,
        tags=frozenset({"straight_support_joker"}),
    ),
    "j_shortcut": JokerRule(
        category="utility",
        effect_type="straight_support",
        base_score=0,
        tags=frozenset({"straight_support_joker"}),
    ),
    "j_runner": JokerRule(
        category="utility",
        effect_type="straight_payoff",
        base_score=0,
        tags=frozenset({"straight_payoff"}),
    ),
    "j_order": JokerRule(
        category="utility",
        effect_type="straight_payoff",
        base_score=0,
        tags=frozenset({"straight_payoff"}),
    ),
    "j_tribe": JokerRule(
        category="utility",
        effect_type="flush_payoff",
        base_score=0,
        tags=frozenset({"flush_payoff"}),
    ),
}


def joker_rule(key: str | None) -> JokerRule | None:
    """Return a rule for a known joker key."""
    if not key:
        return None
    normalized = _ALIASES.get(key.lower(), key.lower())
    return _RULES.get(normalized)
