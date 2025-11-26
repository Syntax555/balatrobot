"""Tests for src/lua/endpoints/cash_out.lua"""

import socket
from typing import Any

from tests.lua.conftest import api, assert_error_response, load_fixture


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

    def test_cash_out_from_ROUND_EVAL(self, client: socket.socket) -> None:
        """Test cashing out from ROUND_EVAL state."""
        gamestate = load_fixture(client, "cash_out", "state-ROUND_EVAL")
        assert gamestate["state"] == "ROUND_EVAL"
        response = api(client, "cash_out", {})
        verify_cash_out_response(response)
        assert response["state"] == "SHOP"


class TestCashOutEndpointStateRequirements:
    """Test cash_out endpoint state requirements."""

    def test_cash_out_from_BLIND_SELECT(self, client: socket.socket):
        """Test that cash_out fails when not in ROUND_EVAL state."""
        gamestate = load_fixture(client, "cash_out", "state-BLIND_SELECT")
        assert gamestate["state"] == "BLIND_SELECT"
        assert_error_response(
            api(client, "cash_out", {}),
            "STATE_INVALID_STATE",
            "Endpoint 'cash_out' requires one of these states:",
        )
