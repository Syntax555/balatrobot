from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BotConfig:
    """Configuration for running the bot."""

    base_url: str
    deck: str
    stake: str
    seed: str | None
    max_steps: int
    timeout: float
