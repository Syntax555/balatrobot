from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from balatro_ai.cards import card_text, card_tokens
from balatro_ai.token_utils import has_x_token


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

_ECON_TOKENS = {"money", "interest", "discount", "sell", "reroll", "shop"}
_CHIPS_TOKENS = {"chips", "chip"}
_MULT_TOKENS = {"mult", "multiplier"}
_XMULT_TOKENS = {"xmult"}

DEFAULT_JOKER_RULE = JokerRule(
    category="default",
    effect_type="",
    base_score=None,
    tags=frozenset(),
)


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
        tags=frozenset({"straight_support_joker", "flush_payoff"}),
        intent_bonus=(("FLUSH", 35), ("STRAIGHT", 25)),
    ),
    "j_shortcut": JokerRule(
        category="utility",
        effect_type="straight_support",
        base_score=0,
        tags=frozenset({"straight_support_joker"}),
        intent_bonus=(("STRAIGHT", 20),),
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
    "j_burglar": JokerRule(
        category="utility",
        effect_type="hand_support",
        base_score=0,
        flat_bonus=15,
        intent_bonus=(("FLUSH", 10), ("STRAIGHT", 10), ("PAIRS", 10)),
        tags=frozenset(),
    ),
    "j_blackboard": JokerRule(
        category="xmult",
        effect_type="xmult_conditional",
        base_score=None,
        intent_bonus=(("FLUSH", 30), ("STRAIGHT", -10)),
        tags=frozenset({"suit_focus"}),
    ),
    "j_superposition": JokerRule(
        category="utility",
        effect_type="tarot_engine",
        base_score=0,
        flat_bonus=10,
        intent_bonus=(("STRAIGHT", 40),),
        tags=frozenset({"straight_payoff"}),
    ),
    "j_seance": JokerRule(
        category="utility",
        effect_type="spectral_engine",
        base_score=0,
        flat_bonus=12,
        intent_bonus=(("FLUSH", 35), ("STRAIGHT", 35)),
        tags=frozenset({"flush_payoff", "straight_payoff"}),
    ),
    "j_constellation": JokerRule(
        category="xmult",
        effect_type="xmult_scaling",
        base_score=None,
        flat_bonus=10,
    ),
    "j_card_sharp": JokerRule(
        category="xmult",
        effect_type="xmult_conditional",
        base_score=None,
        flat_bonus=8,
    ),
    "j_madness": JokerRule(
        category="xmult",
        effect_type="xmult_scaling",
        base_score=None,
        flat_bonus=5,
    ),
    "j_obelisk": JokerRule(
        category="xmult",
        effect_type="xmult_scaling",
        base_score=None,
        flat_bonus=6,
    ),
    "j_hologram": JokerRule(
        category="xmult",
        effect_type="xmult_scaling",
        base_score=None,
        flat_bonus=8,
    ),
    "j_vampire": JokerRule(
        category="xmult",
        effect_type="xmult_scaling",
        base_score=None,
        flat_bonus=6,
    ),
    "j_baron": JokerRule(
        category="xmult",
        effect_type="xmult_rank",
        base_score=None,
        intent_bonus=(("HIGH_CARD", 20), ("PAIRS", 10)),
    ),
    "j_brainstorm": JokerRule(
        category="utility",
        effect_type="copy_leftmost",
        base_score=0,
        flat_bonus=45,
        intent_bonus=(
            ("FLUSH", 20),
            ("STRAIGHT", 20),
            ("PAIRS", 20),
            ("HIGH_CARD", 20),
        ),
    ),
    "j_invisible": JokerRule(
        category="econ",
        effect_type="duplicate",
        base_score=0,
        flat_bonus=30,
    ),
    "j_drivers_license": JokerRule(
        category="xmult",
        effect_type="xmult_conditional",
        base_score=None,
        flat_bonus=10,
    ),
    "j_astronomer": JokerRule(
        category="econ",
        effect_type="free_planets",
        base_score=0,
        flat_bonus=35,
        intent_bonus=(("FLUSH", 10), ("STRAIGHT", 10), ("PAIRS", 10)),
    ),
    "j_cartomancer": JokerRule(
        category="econ",
        effect_type="tarot_engine",
        base_score=0,
        flat_bonus=25,
    ),
}


def _infer_joker_rule(*, key: str, text: str | None) -> JokerRule:
    raw = (text or "").lower()
    tokens = card_tokens(raw) | card_tokens(key)

    if tokens & _XMULT_TOKENS or has_x_token(tokens):
        category = "xmult"
    elif tokens & _MULT_TOKENS:
        category = "mult"
    elif tokens & _CHIPS_TOKENS:
        category = "chips"
    elif "$" in raw or tokens & _ECON_TOKENS:
        category = "econ"
    else:
        category = "default"

    if category == "default":
        return DEFAULT_JOKER_RULE
    return JokerRule(
        category=category, effect_type="", base_score=None, tags=frozenset()
    )


def joker_rule(key: str | None, text: str | None = None) -> JokerRule | None:
    """Return a rule for a joker key; infer categories for unknown keys."""
    if not key:
        return None
    normalized = _ALIASES.get(key.lower(), key.lower())
    rule = _RULES.get(normalized)
    if rule is not None:
        return rule
    if normalized.startswith("j_"):
        return _infer_joker_rule(key=normalized, text=text)
    return None


def joker_rule_for_card(card: Mapping[str, Any]) -> JokerRule | None:
    key_value = card.get("key")
    key = key_value if isinstance(key_value, str) else None
    if not key:
        return None
    return joker_rule(key, card_text(card))
