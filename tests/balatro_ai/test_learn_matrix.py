from __future__ import annotations

from balatro_ai.learn import _matrix_decks, _matrix_stakes, _split_csv, build_parser


def test_split_csv_normalizes_and_splits() -> None:
    assert _split_csv("") == []
    assert _split_csv(" red , blue;checkered ") == ["RED", "BLUE", "CHECKERED"]


def test_matrix_defaults_to_single_combo() -> None:
    args = build_parser().parse_args(["--deck", "red", "--stake", "white"])
    assert _matrix_decks(args) == ["RED"]
    assert _matrix_stakes(args) == ["WHITE"]


def test_matrix_uses_csv_overrides() -> None:
    args = build_parser().parse_args(
        [
            "--deck",
            "RED",
            "--stake",
            "WHITE",
            "--decks",
            "blue,green",
            "--stakes",
            "red",
        ]
    )
    assert _matrix_decks(args) == ["BLUE", "GREEN"]
    assert _matrix_stakes(args) == ["RED"]
