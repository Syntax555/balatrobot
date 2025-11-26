"""Tests for src/lua/endpoints/skip.lua"""

import socket
from typing import Any

from tests.lua.conftest import api, assert_error_response, load_fixture


def verify_skip_response(response: dict[str, Any]) -> None:
    """Verify that skip response has expected fields."""
    # Verify state field
    assert "state" in response
    assert isinstance(response["state"], str)
    assert response["state"] == "BLIND_SELECT"

    # Verify blinds field exists
    assert "blinds" in response
    assert isinstance(response["blinds"], dict)


class TestSkipEndpoint:
    """Test basic skip endpoint functionality."""

    def test_skip_small_blind(self, client: socket.socket) -> None:
        """Test skipping Small blind in BLIND_SELECT state."""
        gamestate = load_fixture(
            client, "skip", "state-BLIND_SELECT--blinds.small.status-SELECT"
        )
        assert gamestate["state"] == "BLIND_SELECT"
        assert gamestate["blinds"]["small"]["status"] == "SELECT"
        response = api(client, "skip", {})
        verify_skip_response(response)
        assert response["blinds"]["small"]["status"] == "SKIPPED"
        assert response["blinds"]["big"]["status"] == "SELECT"

    def test_skip_big_blind(self, client: socket.socket) -> None:
        """Test skipping Big blind in BLIND_SELECT state."""
        gamestate = load_fixture(
            client, "skip", "state-BLIND_SELECT--blinds.big.status-SELECT"
        )
        assert gamestate["state"] == "BLIND_SELECT"
        assert gamestate["blinds"]["big"]["status"] == "SELECT"
        response = api(client, "skip", {})
        verify_skip_response(response)
        assert response["blinds"]["big"]["status"] == "SKIPPED"
        assert response["blinds"]["boss"]["status"] == "SELECT"

    def test_skip_big_boss(self, client: socket.socket) -> None:
        """Test skipping Boss in BLIND_SELECT state."""
        gamestate = load_fixture(
            client, "skip", "state-BLIND_SELECT--blinds.boss.status-SELECT"
        )
        assert gamestate["state"] == "BLIND_SELECT"
        assert gamestate["blinds"]["boss"]["status"] == "SELECT"
        assert_error_response(
            api(client, "skip", {}),
            "GAME_INVALID_STATE",
            "Cannot skip Boss blind",
        )


class TestSkipEndpointStateRequirements:
    """Test skip endpoint state requirements."""

    def test_skip_from_MENU(self, client: socket.socket):
        """Test that skip fails when not in BLIND_SELECT state."""
        response = api(client, "menu", {})
        assert response["state"] == "MENU"
        assert_error_response(
            api(client, "skip", {}),
            "STATE_INVALID_STATE",
            "Endpoint 'skip' requires one of these states:",
        )
