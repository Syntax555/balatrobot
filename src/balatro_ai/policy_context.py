from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from balatro_ai.config import Config


@dataclass
class PolicyContext:
    """Context for policy decisions."""

    config: Config
    run_memory: dict[str, Any]
    round_memory: dict[str, Any]

    @property
    def memory(self) -> dict[str, Any]:
        return self.run_memory


@dataclass(frozen=True)
class DecisionFrame:
    state: str
    last_state: str | None
    entering: bool

