from __future__ import annotations


def has_x_token(tokens: set[str], *, slice_after_first_char: int = 1) -> bool:
    if "x" in tokens:
        return True
    for token in tokens:
        if token.startswith("x") and token[slice_after_first_char:].isdigit():
            return True
    return False
