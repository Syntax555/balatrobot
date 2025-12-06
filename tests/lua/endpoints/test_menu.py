"""Tests for src/lua/endpoints/menu.lua"""

import socket

from tests.lua.conftest import api, assert_gamestate_response, load_fixture


class TestMenuEndpoint:
    """Test basic menu endpoint and menu response structure."""

    def test_menu_from_MENU(self, client: socket.socket) -> None:
        """Test that menu endpoint returns state as MENU."""
        api(client, "menu", {})
        response = api(client, "menu", {})
        assert_gamestate_response(response, state="MENU")

    def test_menu_from_BLIND_SELECT(self, client: socket.socket) -> None:
        """Test that menu endpoint returns state as MENU."""
        gamestate = load_fixture(client, "menu", "state-BLIND_SELECT")
        assert gamestate["state"] == "BLIND_SELECT"
        response = api(client, "menu", {})
        assert_gamestate_response(response, state="MENU")
