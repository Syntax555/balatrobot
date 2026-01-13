from __future__ import annotations

import os
import time
from pathlib import Path

from balatro_ai.learn import _apply_auto_defaults, _find_latest_best_json, build_parser


def test_auto_defaults_apply_profile_when_flags_missing() -> None:
    argv = ["--deck", "RED", "--stake", "WHITE"]
    args = build_parser().parse_args(argv)
    _apply_auto_defaults(args, argv)
    assert args.profile == "balanced"
    assert args.train_count == 60
    assert args.eval_count == 20
    assert args.objective == "trimmed_mean_score"
    assert args.trim_bottom_pct == 0.1


def test_auto_defaults_do_not_override_explicit_flags() -> None:
    argv = [
        "--deck",
        "RED",
        "--stake",
        "WHITE",
        "--train-count",
        "10",
        "--objective",
        "wins_then_ante",
    ]
    args = build_parser().parse_args(argv)
    _apply_auto_defaults(args, argv)
    assert args.train_count == 10
    assert args.objective == "wins_then_ante"


def test_find_latest_best_json_prefers_newest_mtime(tmp_path: Path) -> None:
    out_root = tmp_path / "learn"
    out_root.mkdir()
    a = out_root / "RED-WHITE-20260101-000000" / "best.json"
    b = out_root / "matrix-20260102-000000" / "RED-WHITE" / "best.json"
    a.parent.mkdir(parents=True)
    b.parent.mkdir(parents=True)
    a.write_text("{}", encoding="utf-8")
    b.write_text("{}", encoding="utf-8")
    now = time.time()
    os.utime(a, (now - 100, now - 100))
    os.utime(b, (now, now))

    found = _find_latest_best_json(out_root, deck="RED", stake="WHITE")
    assert found == b
