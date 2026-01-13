import json
import os
import time
from pathlib import Path

from balatro_ai import bot as bot_mod


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_resolve_params_auto_prefers_most_recent(tmp_path: Path) -> None:
    root = tmp_path / "logs" / "learn"

    single = root / "RED-WHITE-20250101-000000" / "best.json"
    matrix = root / "matrix-20250101-000000" / "RED-WHITE" / "best.json"

    _write_json(single, {"params": {"rollout_k": 11}})
    _write_json(matrix, {"params": {"rollout_k": 22}})

    now = time.time()
    os.utime(single, (now - 10, now - 10))
    os.utime(matrix, (now, now))

    resolved, source = bot_mod._resolve_params_json_path(
        ["--deck", "RED", "--stake", "WHITE", "--params-auto-root", str(root)]
    )
    assert source == "auto"
    assert resolved == str(matrix)


def test_resolve_params_explicit_overrides_auto(tmp_path: Path) -> None:
    root = tmp_path / "logs" / "learn"
    explicit = tmp_path / "explicit.json"
    _write_json(explicit, {"params": {"rollout_k": 99}})

    single = root / "RED-WHITE-20250101-000000" / "best.json"
    _write_json(single, {"params": {"rollout_k": 11}})

    resolved, source = bot_mod._resolve_params_json_path(
        [
            "--params-json",
            str(explicit),
            "--params-auto-root",
            str(root),
            "--deck",
            "RED",
            "--stake",
            "WHITE",
        ]
    )
    assert source == "explicit"
    assert resolved == str(explicit)


def test_resolve_params_no_params_auto_returns_none(tmp_path: Path) -> None:
    root = tmp_path / "logs" / "learn"
    resolved, source = bot_mod._resolve_params_json_path(
        [
            "--no-params-auto",
            "--params-auto-root",
            str(root),
            "--deck",
            "RED",
            "--stake",
            "WHITE",
        ]
    )
    assert source == "none"
    assert resolved is None


def test_resolve_params_auto_filters_by_deck_stake(tmp_path: Path) -> None:
    root = tmp_path / "logs" / "learn"
    _write_json(
        root / "RED-WHITE-20250101-000000" / "best.json", {"params": {"rollout_k": 11}}
    )

    resolved, source = bot_mod._resolve_params_json_path(
        ["--deck", "BLUE", "--stake", "WHITE", "--params-auto-root", str(root)]
    )
    assert source == "auto"
    assert resolved is None
