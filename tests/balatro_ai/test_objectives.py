from __future__ import annotations

from balatro_ai.autotune import _objective as autotune_objective


def _run(*, won: bool, ante: int) -> dict:
    return {
        "won": won,
        "ante": ante,
        "round": 1,
        "money": 0,
        "steps": 0,
    }


def test_trimmed_mean_ignores_bottom_tail() -> None:
    runs = [
        _run(won=False, ante=1),  # "unwinnable" / very bad seed
        _run(won=True, ante=5),
        _run(won=True, ante=5),
        _run(won=True, ante=5),
        _run(won=True, ante=5),
        _run(won=True, ante=5),
        _run(won=True, ante=5),
        _run(won=True, ante=5),
        _run(won=True, ante=5),
        _run(won=True, ante=5),
    ]
    mean_score = autotune_objective(runs, objective="mean_score", trim_bottom_pct=0.0)
    trimmed = autotune_objective(
        runs, objective="trimmed_mean_score", trim_bottom_pct=0.1
    )
    assert trimmed > mean_score
