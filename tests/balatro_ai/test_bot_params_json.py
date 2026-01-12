from __future__ import annotations

import json

from balatro_ai.bot import _load_params_json, build_parser


def test_params_json_sets_cli_defaults(tmp_path) -> None:
    payload = {
        "best": {
            "params": {
                "reserve_early": 7,
                "reserve_mid": 17,
                "reserve_late": 27,
                "hand_rollout": False,
                "intent_trials": 150,
            }
        }
    }
    path = tmp_path / "best.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    params = _load_params_json(path)
    args = build_parser(defaults=params).parse_args(["--params-json", str(path)])
    assert args.reserve_early == 7
    assert args.reserve_mid == 17
    assert args.reserve_late == 27
    assert args.hand_rollout is False
    assert args.intent_trials == 150


def test_cli_flags_override_params_json_defaults(tmp_path) -> None:
    payload = {"best": {"params": {"reserve_early": 7}}}
    path = tmp_path / "best.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    params = _load_params_json(path)
    args = build_parser(defaults=params).parse_args(
        ["--params-json", str(path), "--reserve-early", "10"]
    )
    assert args.reserve_early == 10
