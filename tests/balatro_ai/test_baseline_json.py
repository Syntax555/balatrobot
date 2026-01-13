from __future__ import annotations

import json
from pathlib import Path

from balatro_ai.asha_tune import _baseline_params as asha_baseline_params
from balatro_ai.autotune import _baseline_params as autotune_baseline_params


def test_autotune_baseline_accepts_best_json(tmp_path: Path) -> None:
    payload = {"best": {"params": {"reserve_early": 5, "reserve_mid": 12}}}
    path = tmp_path / "best.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    params = autotune_baseline_params(path)
    assert params is not None
    assert params.reserve_early == 5
    assert params.reserve_mid == 12


def test_asha_baseline_accepts_partial_params(tmp_path: Path) -> None:
    payload = {"best": {"params": {"reserve_early": 5, "joker_score_xmult": 123}}}
    path = tmp_path / "best.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    params = asha_baseline_params(path)
    assert params is not None
    assert params.reserve_early == 5
    assert params.joker_score_xmult == 123
