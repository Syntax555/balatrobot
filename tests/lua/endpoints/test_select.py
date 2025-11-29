"""Tests for src/lua/endpoints/select.lua"""

import socket
from typing import Any

from tests.lua.conftest import api, assert_error_response, load_fixture


def verify_select_response(response: dict[str, Any]) -> None:
    """Verify that select response has expected fields."""
    # Verify state field - should transition to SELECTING_HAND after selecting blind
    assert "state" in response
    assert isinstance(response["state"], str)
    assert response["state"] == "SELECTING_HAND"

    # Verify hand field exists
    assert "hand" in response
    assert isinstance(response["hand"], dict)

    # Verify we transitioned to SELECTING_HAND state
    assert response["state"] == "SELECTING_HAND"


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
        assert response["state"] == "MENU"
        assert_error_response(
            api(client, "select", {}),
            "STATE_INVALID_STATE",
            "Endpoint 'select' requires one of these states: BLIND_SELECT",
        )
