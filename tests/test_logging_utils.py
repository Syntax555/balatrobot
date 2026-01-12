import logging

from balatro_ai.logging_utils import configure_logging


def test_configure_logging_allows_overriding_fields_with_extra():
    configure_logging("INFO")
    logger = logging.getLogger("balatro_ai.test")
    logger.info(
        "hello",
        extra={
            "state": "MENU",
            "ante": 1,
            "round": 2,
            "money": 3,
            "action_kind": "test",
        },
    )

