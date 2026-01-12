from __future__ import annotations

import pytest

from balatro_ai.joker_rules import joker_rule


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("x2 mult", "xmult"),
        ("X1.5 mult", "xmult"),
        ("+mult every hand", "mult"),
        ("multiplier when played", "mult"),
        ("gain chips", "chips"),
        ("gain chip", "chips"),
        ("earn $2 interest", "econ"),
        ("shop discount", "econ"),
        ("nothing special", "default"),
    ],
)
def test_infer_joker_category_from_text_tokens(text: str, expected: str) -> None:
    rule = joker_rule("j_new_content", text)
    assert rule is not None
    assert rule.category == expected

