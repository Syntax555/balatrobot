from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    """Configuration for running the bot."""

    deck: str
    stake: str
    seed: str | None
    max_steps: int
    timeout: float
    log_level: str
    rollout_k: int = 30
    discard_m: int = 12
    reserve_early: int = 10
    reserve_mid: int = 20
    reserve_late: int = 25
    max_rerolls_per_shop: int = 1
    # Optional JSONL decision log written by the client (not the mod).
    decision_log_path: str | None = None
    # If True, include small state summaries in decision logs.
    decision_log_include_state: bool = True
    # Rollout controls (also configurable via env vars in rollout.py).
    rollout_parallel: str | None = None
    rollout_workers: int | None = None
    rollout_time_budget_s: float | None = None
    # If False, do not use save/load rollouts in SELECTING_HAND.
    hand_rollout: bool = True
    # If True, use snapshot (save/load) lookahead for SHOP actions.
    shop_rollout: bool = False
    # Max number of SHOP candidate sequences to evaluate.
    shop_rollout_candidates: int = 10
    # SHOP rollout evaluation time budget seconds.
    shop_rollout_time_budget_s: float | None = None
    # If True, use snapshot (save/load) evaluation for pack selection.
    pack_rollout: bool = False
    # Pack rollout evaluation time budget seconds.
    pack_rollout_time_budget_s: float | None = None
    # If True, run a quick determinism probe and disable rollouts if unsafe.
    determinism_check: bool = True
    # Intent evaluation Monte Carlo trials (higher = more stable, slower).
    intent_trials: int = 200
    # Shop policy thresholds/weights (tunable).
    buy_threshold_early: int = 30
    buy_threshold_mid: int = 35
    buy_threshold_late: int = 40
    reroll_threshold_early: int = 20
    reroll_threshold_mid: int = 25
    reroll_threshold_late: int = 30
    cost_weight_early: float = 1.8
    cost_weight_mid: float = 1.2
    cost_weight_late: float = 0.9
    # Joker category base scores (tunable).
    joker_score_xmult: int = 100
    joker_score_mult: int = 50
    joker_score_chips: int = 20
    joker_score_econ: int = 0
    joker_score_default: int = 0
    # If True, block forever at MENU (Option A) until the script is restarted.
    pause_at_menu: bool = True
    # If True, attempt to call RPC "start" from MENU using deck/stake/seed.
    auto_start: bool = False
