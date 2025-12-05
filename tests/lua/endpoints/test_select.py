"""Tests for src/lua/endpoints/select.lua"""

import socket
from typing import Any

from tests.lua.conftest import api, assert_error_response, load_fixture


def verify_select_response(response: dict[str, Any]) -> None:
    """Verify that select response has expected fields."""
    # Verify state field - should transition to SELECTING_HAND after selecting blind
    assert "state" in response["result"]
    assert isinstance(response["result"]["state"], str)
    assert response["result"]["state"] == "SELECTING_HAND"

    # Verify hand field exists
    assert "hand" in response["result"]
    assert isinstance(response["result"]["hand"], dict)

    # Verify we transitioned to SELECTING_HAND state
    assert response["result"]["state"] == "SELECTING_HAND"


class TestSelectEndpoint:
    """Test basic select endpoint functionality."""

    def test_select_small_blind(self, client: socket.socket) -> None:
        """Test selecting Small blind in BLIND_SELECT state."""
        gamestate = load_fixture(
            client, "select", "state-BLIND_SELECT--blinds.small.status-SELECT"
        )
        assert gamestate["state"] == "BLIND_SELECT"
        assert gamestate["blinds"]["small"]["status"] == "SELECT"
        response = api(client, "select", {})
        verify_select_response(response)

    def test_select_big_blind(self, client: socket.socket) -> None:
        """Test selecting Big blind in BLIND_SELECT state."""
        gamestate = load_fixture(
            client, "select", "state-BLIND_SELECT--blinds.big.status-SELECT"
        )
        assert gamestate["state"] == "BLIND_SELECT"
        assert gamestate["blinds"]["big"]["status"] == "SELECT"
        response = api(client, "select", {})
        verify_select_response(response)

    def test_select_boss_blind(self, client: socket.socket) -> None:
        """Test selecting Boss blind in BLIND_SELECT state."""
        gamestate = load_fixture(
            client, "select", "state-BLIND_SELECT--blinds.boss.status-SELECT"
        )
        assert gamestate["state"] == "BLIND_SELECT"
        assert gamestate["blinds"]["boss"]["status"] == "SELECT"
        response = api(client, "select", {})
        verify_select_response(response)


class TestSelectEndpointStateRequirements:
    """Test select endpoint state requirements."""

    def test_select_from_MENU(self, client: socket.socket):
        """Test that select fails when not in BLIND_SELECT state."""
        response = api(client, "menu", {})
        assert response["result"]["state"] == "MENU"
        assert_error_response(
            api(client, "select", {}),
            "INVALID_STATE",
            "Method 'select' requires one of these states: BLIND_SELECT",
        )
