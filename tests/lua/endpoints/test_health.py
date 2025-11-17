# tests/lua/endpoints/test_health.py
# Tests for src/lua/endpoints/health.lua
#
# Tests the health check endpoint:
# - Basic health check functionality
# - Response structure and fields

import socket
from typing import Any

from tests.lua.conftest import api, get_fixture_path


def assert_health_response(response: dict[str, Any]) -> None:
    assert "status" in response
    assert response["status"] == "ok"


class TestHealthEndpoint:
    """Test basic health endpoint functionality."""

    def test_health_from_MENU(self, client: socket.socket) -> None:
        """Test that health check returns status ok."""
        response = api(client, "menu", {})
        assert response["state"] == "MENU"
        response = api(client, "health", {})
        assert_health_response(response)

    def test_health_from_BLIND_SELECT(self, client: socket.socket) -> None:
        """Test that health check returns status ok."""
        save = "state-BLIND_SELECT.jkr"
        api(client, "load", {"path": str(get_fixture_path("health", save))})
        response = api(client, "health", {})
        assert_health_response(response)
