from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Action:
    """Represents a single RPC action to execute."""

    kind: str
    params: dict[str, Any]
