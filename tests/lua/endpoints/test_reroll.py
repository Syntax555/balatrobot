"""Tests for src/lua/endpoints/reroll.lua"""

import socket

from tests.lua.conftest import api, assert_error_response, get_fixture_path


class TestRerollEndpoint:
    """Test basic reroll endpoint functionality."""

    def test_reroll_from_shop(self, client: socket.socket) -> None:
        """Test rerolling shop from SHOP state."""
        save = "state-SHOP.jkr"
        api(client, "load", {"path": str(get_fixture_path("reroll", save))})
        after = api(client, "gamestate", {})
        before = api(client, "reroll", {})
        assert after["state"] == "SHOP"
        assert before["state"] == "SHOP"
        assert after["shop"] != before["shop"]

    def test_reroll_insufficient_funds(self, client: socket.socket) -> None:
        """Test reroll endpoint when player has insufficient funds."""
        save = "state-SHOP--money-0.jkr"
        api(client, "load", {"path": str(get_fixture_path("reroll", save))})
        response = api(client, "reroll", {})
        assert_error_response(
            response,
            expected_error_code="GAME_INVALID_STATE",
            expected_message_contains="Not enough dollars to reroll",
        )


class TestRerollEndpointStateRequirements:
    """Test reroll endpoint state requirements."""

    def test_reroll_from_BLIND_SELECT(self, client: socket.socket):
        """Test that reroll fails when not in SHOP state."""
        save = "state-BLIND_SELECT.jkr"
        api(client, "load", {"path": str(get_fixture_path("reroll", save))})
        response = api(client, "reroll", {})
        assert_error_response(
            response,
            expected_error_code="STATE_INVALID_STATE",
            expected_message_contains="Endpoint 'reroll' requires one of these states:",
        )
