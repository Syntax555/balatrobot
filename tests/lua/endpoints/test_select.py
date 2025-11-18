"""Tests for src/lua/endpoints/select.lua"""

import socket
from typing import Any

from tests.lua.conftest import api, assert_error_response, get_fixture_path


def verify_select_response(response: dict[str, Any]) -> None:
    """Verify that select response has expected fields."""
    # Verify state field - should transition to SELECTING_HAND after selecting blind
    assert "state" in response
    assert isinstance(response["state"], str)
    assert response["state"] == "SELECTING_HAND"

    # Verify hand field exists
    assert "hand" in response
    assert isinstance(response["hand"], dict)


class TestSelectEndpoint:
    """Test basic select endpoint functionality."""

    def test_select_small_blind(self, client: socket.socket) -> None:
        """Test selecting Small blind in BLIND_SELECT state."""
        save = "state-BLIND_SELECT--blinds.small.status-SELECT.jkr"
        api(client, "load", {"path": str(get_fixture_path("select", save))})
        response = api(client, "select", {})
        verify_select_response(response)
        # Verify we transitioned to SELECTING_HAND state
        assert response["state"] == "SELECTING_HAND"

    def test_select_big_blind(self, client: socket.socket) -> None:
        """Test selecting Big blind in BLIND_SELECT state."""
        save = "state-BLIND_SELECT--blinds.big.status-SELECT.jkr"
        api(client, "load", {"path": str(get_fixture_path("select", save))})
        response = api(client, "select", {})
        verify_select_response(response)
        # Verify we transitioned to SELECTING_HAND state
        assert response["state"] == "SELECTING_HAND"

    def test_select_boss_blind(self, client: socket.socket) -> None:
        """Test selecting Boss blind in BLIND_SELECT state."""
        save = "state-BLIND_SELECT--blinds.boss.status-SELECT.jkr"
        api(client, "load", {"path": str(get_fixture_path("select", save))})
        response = api(client, "select", {})
        verify_select_response(response)
        # Verify we transitioned to SELECTING_HAND state
        assert response["state"] == "SELECTING_HAND"


class TestSelectEndpointStateRequirements:
    """Test select endpoint state requirements."""

    def test_select_from_MENU(self, client: socket.socket):
        """Test that select fails when not in BLIND_SELECT state."""
        response = api(client, "menu", {})
        assert response["state"] == "MENU"
        response = api(client, "select", {})
        assert_error_response(
            response,
            expected_error_code="STATE_INVALID_STATE",
            expected_message_contains="Endpoint 'select' requires one of these states:",
        )
