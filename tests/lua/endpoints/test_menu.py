"""Tests for src/lua/endpoints/menu.lua"""

import socket
from typing import Any

from tests.lua.conftest import api, get_fixture_path


def verify_base_menu_response(response: dict[str, Any]) -> None:
    """Verify that menu response has all base fields."""
    # Verify state field
    assert "state" in response
    assert isinstance(response["state"], str)
    assert len(response["state"]) > 0


class TestMenuEndpoint:
    """Test basic menu endpoint and menu response structure.n"""

    def test_menu_from_MENU(self, client: socket.socket) -> None:
        """Test that menu endpoint returns state as MENU."""
        api(client, "menu", {})
        response = api(client, "menu", {})
        verify_base_menu_response(response)

    def test_menu_from_BLIND_SELECT(self, client: socket.socket) -> None:
        """Test that menu endpoint returns state as MENU."""
        save = "state-BLIND_SELECT--round_num-0--deck-RED--stake-WHITE.jkr"
        api(client, "load", {"path": str(get_fixture_path("menu", save))})
        response = api(client, "menu", {})
        verify_base_menu_response(response)
