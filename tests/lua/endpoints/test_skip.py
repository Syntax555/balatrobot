"""Tests for src/lua/endpoints/skip.lua"""

import socket
from typing import Any

from tests.lua.conftest import api, assert_error_response, get_fixture_path


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
        save = "state-BLIND_SELECT--blinds.small.status-SELECT.jkr"
        api(client, "load", {"path": str(get_fixture_path("skip", save))})
        response = api(client, "skip", {})
        verify_skip_response(response)
        assert response["blinds"]["small"]["status"] == "SKIPPED"
        assert response["blinds"]["big"]["status"] == "SELECT"

    def test_skip_big_blind(self, client: socket.socket) -> None:
        """Test skipping Big blind in BLIND_SELECT state."""
        save = "state-BLIND_SELECT--blinds.big.status-SELECT.jkr"
        api(client, "load", {"path": str(get_fixture_path("skip", save))})
        response = api(client, "skip", {})
        verify_skip_response(response)
        assert response["blinds"]["big"]["status"] == "SKIPPED"
        assert response["blinds"]["boss"]["status"] == "SELECT"

    def test_skip_big_boss(self, client: socket.socket) -> None:
        """Test skipping Boss in BLIND_SELECT state."""
        save = "state-BLIND_SELECT--blinds.boss.status-SELECT.jkr"
        api(client, "load", {"path": str(get_fixture_path("skip", save))})
        response = api(client, "skip", {})
        assert_error_response(
            response,
            expected_error_code="GAME_INVALID_STATE",
            expected_message_contains="Cannot skip Boss blind",
        )


class TestSkipEndpointStateRequirements:
    """Test skip endpoint state requirements."""

    def test_skip_from_MENU(self, client: socket.socket):
        """Test that skip fails when not in BLIND_SELECT state."""
        response = api(client, "menu", {})
        assert response["state"] == "MENU"
        response = api(client, "skip", {})
        assert_error_response(
            response,
            expected_error_code="STATE_INVALID_STATE",
            expected_message_contains="Endpoint 'skip' requires one of these states:",
        )
