from __future__ import annotations

import logging


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
    old_factory = logging.getLogRecordFactory()

    def record_factory(*args: object, **kwargs: object) -> logging.LogRecord:
        record = old_factory(*args, **kwargs)
        for key, value in defaults.items():
            if not hasattr(record, key):
                setattr(record, key, value)
        return record

    logging.setLogRecordFactory(record_factory)
    logging.basicConfig(
        level=level,
        format=(
            "%(asctime)s %(levelname)s %(name)s "
            "state=%(state)s ante=%(ante)s round=%(round)s "
            "money=%(money)s action=%(action_kind)s: %(message)s"
        ),
    )
