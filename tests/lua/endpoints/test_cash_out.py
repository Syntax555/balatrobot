"""Tests for src/lua/endpoints/cash_out.lua"""

import socket
from typing import Any

from tests.lua.conftest import api, assert_error_response, get_fixture_path


def verify_cash_out_response(response: dict[str, Any]) -> None:
    """Verify that cash_out response has expected fields."""
    # Verify state field - should transition to SHOP after cashing out
    assert "state" in response
    assert isinstance(response["state"], str)
    assert response["state"] == "SHOP"

    # Verify shop field exists
    assert "shop" in response
    assert isinstance(response["shop"], dict)


class TestCashOutEndpoint:
    """Test basic cash_out endpoint functionality."""

    def test_cash_out_from_round_eval(self, client: socket.socket) -> None:
        """Test cashing out from ROUND_EVAL state."""
        save = "state-ROUND_EVAL.jkr"
        api(client, "load", {"path": str(get_fixture_path("cash_out", save))})
        response = api(client, "cash_out", {})
        verify_cash_out_response(response)
        assert response["state"] == "SHOP"


class TestCashOutEndpointStateRequirements:
    """Test cash_out endpoint state requirements."""

    def test_cash_out_from_MENU(self, client: socket.socket):
        """Test that cash_out fails when not in ROUND_EVAL state."""
        response = api(client, "menu", {})
        response = api(client, "cash_out", {})
        assert_error_response(
            response,
            expected_error_code="STATE_INVALID_STATE",
            expected_message_contains="Endpoint 'cash_out' requires one of these states:",
        )
