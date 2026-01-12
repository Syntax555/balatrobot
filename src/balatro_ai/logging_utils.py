from __future__ import annotations

import logging


class _DefaultFieldsFilter(logging.Filter):
    def __init__(self, defaults: dict[str, object]) -> None:
        super().__init__()
        self._defaults = defaults

    def filter(self, record: logging.LogRecord) -> bool:
        for key, value in self._defaults.items():
            if not hasattr(record, key):
                setattr(record, key, value)
        return True


def configure_logging(log_level: str) -> None:
    """Configure standard logging for the bot."""
    level = getattr(logging, log_level.upper(), logging.INFO)
    defaults = {
        "state": "UNKNOWN",
        "ante": -1,
        "round": -1,
        "money": -1,
        "action_kind": "NONE",
    }
    logging.basicConfig(
        level=level,
        format=(
            "%(asctime)s %(levelname)s %(name)s "
            "state=%(state)s ante=%(ante)s round=%(round)s "
            "money=%(money)s action=%(action_kind)s: %(message)s"
        ),
    )
    default_filter = _DefaultFieldsFilter(defaults)
    root = logging.getLogger()
    for handler in root.handlers:
        handler.addFilter(default_filter)
