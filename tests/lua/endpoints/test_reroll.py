"""Tests for src/lua/endpoints/reroll.lua"""

import socket

from tests.lua.conftest import api, assert_error_response, load_fixture


class TestRerollEndpoint:
    """Test basic reroll endpoint functionality."""

    def test_reroll_from_shop(self, client: socket.socket) -> None:
        """Test rerolling shop from SHOP state."""
        gamestate = load_fixture(client, "reroll", "state-SHOP")
        assert gamestate["state"] == "SHOP"
        response = api(client, "reroll", {})
        after = response["result"]
        assert gamestate["state"] == "SHOP"
        assert after["state"] == "SHOP"
        assert gamestate["shop"] != after["shop"]

    def test_reroll_insufficient_funds(self, client: socket.socket) -> None:
        """Test reroll endpoint when player has insufficient funds."""
        gamestate = load_fixture(client, "reroll", "state-SHOP--money-0")
        assert gamestate["state"] == "SHOP"
        assert gamestate["money"] == 0
        assert_error_response(
            api(client, "reroll", {}),
            "NOT_ALLOWED",
            "Not enough dollars to reroll",
        )


class TestRerollEndpointStateRequirements:
    """Test reroll endpoint state requirements."""

    def test_reroll_from_BLIND_SELECT(self, client: socket.socket):
        """Test that reroll fails when not in SHOP state."""
        gamestate = load_fixture(client, "reroll", "state-BLIND_SELECT")
        assert gamestate["state"] == "BLIND_SELECT"
        assert_error_response(
            api(client, "reroll", {}),
            "INVALID_STATE",
            "Method 'reroll' requires one of these states: SHOP",
        )
