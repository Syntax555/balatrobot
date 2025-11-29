"""Tests for src/lua/endpoints/next_round.lua"""

import socket
from typing import Any

from tests.lua.conftest import api, assert_error_response, load_fixture


def verify_next_round_response(response: dict[str, Any]) -> None:
    """Verify that next_round response has expected fields."""
    # Verify state field - should transition to BLIND_SELECT
    assert "state" in response
    assert isinstance(response["state"], str)
    assert response["state"] == "BLIND_SELECT"

    # Verify blinds field exists (we're at blind selection)
    assert "blinds" in response
    assert isinstance(response["blinds"], dict)


class TestNextRoundEndpoint:
    """Test basic next_round endpoint functionality."""

    def test_next_round_from_shop(self, client: socket.socket) -> None:
        """Test advancing to next round from SHOP state."""
        gamestate = load_fixture(client, "next_round", "state-SHOP")
        assert gamestate["state"] == "SHOP"
        response = api(client, "next_round", {})
        verify_next_round_response(response)


class TestNextRoundEndpointStateRequirements:
    """Test next_round endpoint state requirements."""

    def test_next_round_from_MENU(self, client: socket.socket):
        """Test that next_round fails when not in SHOP state."""
        gamestate = load_fixture(client, "next_round", "state-BLIND_SELECT")
        assert gamestate["state"] == "BLIND_SELECT"
        response = api(client, "next_round", {})
        assert_error_response(
            response,
            expected_error_code="STATE_INVALID_STATE",
            expected_message_contains="Endpoint 'next_round' requires one of these states: SHOP",
        )
