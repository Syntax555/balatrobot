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
    # If True, block forever at MENU (Option A) until the script is restarted.
    pause_at_menu: bool = True
    # If True, attempt to call RPC "start" from MENU using deck/stake/seed.
    auto_start: bool = False
