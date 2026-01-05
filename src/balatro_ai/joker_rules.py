from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class JokerRule:
    """Structured hints for known joker keys."""

    category: str


_RULES: dict[str, JokerRule] = {
    "j_joker": JokerRule(category="mult"),
    "j_greedy_joker": JokerRule(category="mult"),
    "j_lusty_joker": JokerRule(category="mult"),
    "j_wrathful_joker": JokerRule(category="mult"),
    "j_gluttenous_joker": JokerRule(category="mult"),
    "j_gluttonous_joker": JokerRule(category="mult"),
    "j_jolly": JokerRule(category="mult"),
    "j_zany": JokerRule(category="mult"),
    "j_mad": JokerRule(category="mult"),
    "j_crazy": JokerRule(category="mult"),
    "j_droll": JokerRule(category="mult"),
    "j_half": JokerRule(category="mult"),
    "j_misprint": JokerRule(category="mult"),
    "j_abstract": JokerRule(category="mult"),
    "j_raised_fist": JokerRule(category="mult"),
    "j_fibonacci": JokerRule(category="mult"),
    "j_sly": JokerRule(category="chips"),
    "j_wily": JokerRule(category="chips"),
    "j_clever": JokerRule(category="chips"),
    "j_devious": JokerRule(category="chips"),
    "j_crafty": JokerRule(category="chips"),
    "j_banner": JokerRule(category="chips"),
    "j_scary_face": JokerRule(category="chips"),
    "j_stencil": JokerRule(category="xmult"),
    "j_loyalty_card": JokerRule(category="xmult"),
    "j_steel_joker": JokerRule(category="xmult"),
    "j_mime": JokerRule(category="xmult"),
    "j_dusk": JokerRule(category="xmult"),
    "j_hack": JokerRule(category="xmult"),
    "j_chaos": JokerRule(category="econ"),
    "j_credit_card": JokerRule(category="econ"),
    "j_delayed_grat": JokerRule(category="econ"),
}


def joker_rule(key: str | None) -> JokerRule | None:
    """Return a rule for a known joker key."""
    if not key:
        return None
    return _RULES.get(key)
