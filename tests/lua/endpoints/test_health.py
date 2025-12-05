# tests/lua/endpoints/test_health.py
# Tests for src/lua/endpoints/health.lua
#
# Tests the health check endpoint:
# - Basic health check functionality
# - Response structure and fields

import socket
from typing import Any

from tests.lua.conftest import api, load_fixture


def assert_health_response(response: dict[str, Any]) -> None:
    assert "result" in response
    assert "status" in response["result"]
    assert response["result"]["status"] == "ok"


class TestHealthEndpoint:
    """Test basic health endpoint functionality."""

    def test_health_from_MENU(self, client: socket.socket) -> None:
        """Test that health check returns status ok."""
        response = api(client, "menu", {})
        assert response["result"]["state"] == "MENU"
        assert_health_response(api(client, "health", {}))

    def test_health_from_BLIND_SELECT(self, client: socket.socket) -> None:
        """Test that health check returns status ok."""
        save = "state-BLIND_SELECT"
        gamestate = load_fixture(client, "health", save)
        assert gamestate["state"] == "BLIND_SELECT"
        assert_health_response(api(client, "health", {}))
