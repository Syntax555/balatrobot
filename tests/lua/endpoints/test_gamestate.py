"""Tests for src/lua/endpoints/gamestate.lua"""

import socket
from typing import Any

from tests.lua.conftest import api, load_fixture


def verify_base_gamestate_response(response: dict[str, Any]) -> None:
    """Verify that gamestate response has all base fields."""
    # Verify state field
    assert "state" in response["result"]
    assert isinstance(response["result"]["state"], str)
    assert len(response["result"]["state"]) > 0

    # Verify round_num field
    assert "round_num" in response["result"]
    assert isinstance(response["result"]["round_num"], int)
    assert response["result"]["round_num"] >= 0

    # Verify ante_num field
    assert "ante_num" in response["result"]
    assert isinstance(response["result"]["ante_num"], int)
    assert response["result"]["ante_num"] >= 0

    # Verify money field
    assert "money" in response["result"]
    assert isinstance(response["result"]["money"], int)
    assert response["result"]["money"] >= 0


class TestGamestateEndpoint:
    """Test basic gamestate endpoint and gamestate response structure."""

    def test_gamestate_from_MENU(self, client: socket.socket) -> None:
        """Test that gamestate endpoint from MENU state is valid."""
        api(client, "menu", {})
        response = api(client, "gamestate", {})
        verify_base_gamestate_response(response)
        assert response["result"]["state"] == "MENU"

    def test_gamestate_from_BLIND_SELECT(self, client: socket.socket) -> None:
        """Test that gamestate from BLIND_SELECT state is valid."""
        fixture_name = "state-BLIND_SELECT--round_num-0--deck-RED--stake-WHITE"
        gamestate = load_fixture(client, "gamestate", fixture_name)
        assert gamestate["state"] == "BLIND_SELECT"
        assert gamestate["round_num"] == 0
        assert gamestate["deck"] == "RED"
        assert gamestate["stake"] == "WHITE"
        response = api(client, "gamestate", {})
        verify_base_gamestate_response(response)
        assert response["result"]["state"] == "BLIND_SELECT"
        assert response["result"]["round_num"] == 0
        assert response["result"]["deck"] == "RED"
        assert response["result"]["stake"] == "WHITE"
