from __future__ import annotations

import random
import time


class BackoffPacer:
    """Adaptive backoff helper for pacing requests."""

    def __init__(
        self,
        *,
        min_delay: float = 0.1,
        max_delay: float = 2.0,
        factor: float = 1.5,
        jitter: float = 0.0,
    ) -> None:
        self._min_delay = min_delay
        self._max_delay = max_delay
        self._factor = factor
        self._jitter = jitter
        self._delay = min_delay

    def reset(self) -> None:
        self._delay = self._min_delay

    def bump(self, *, factor: float | None = None) -> float:
        scale = factor if factor is not None else self._factor
        self._delay = min(self._max_delay, self._delay * scale)
        if self._delay < self._min_delay:
            self._delay = self._min_delay
        return self._delay

    def sleep(self) -> None:
        delay = self._delay
        if self._jitter:
            delay = max(0.0, delay + random.uniform(-self._jitter, self._jitter))
        time.sleep(delay)
