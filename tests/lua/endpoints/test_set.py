"""Tests for src/lua/endpoints/set.lua"""

import socket

from tests.lua.conftest import api, assert_error_response, load_fixture


class TestSetEndpoint:
    """Test basic set endpoint functionality."""

    def test_set_game_not_in_run(self, client: socket.socket) -> None:
        """Test that set fails when game is not in run."""
        api(client, "menu", {})
        response = api(client, "set", {})
        assert_error_response(
            response,
            "INVALID_STATE",
            "Can only set during an active run",
        )

    def test_set_no_fields(self, client: socket.socket) -> None:
        """Test that set fails when no fields are provided."""
        gamestate = load_fixture(client, "set", "state-SELECTING_HAND")
        assert gamestate["state"] == "SELECTING_HAND"
        response = api(client, "set", {})
        assert_error_response(
            response,
            "BAD_REQUEST",
            "Must provide at least one field to set",
        )

    def test_set_negative_money(self, client: socket.socket) -> None:
        """Test that set fails when money is negative."""
        gamestate = load_fixture(client, "set", "state-SELECTING_HAND")
        assert gamestate["state"] == "SELECTING_HAND"
        response = api(client, "set", {"money": -100})
        assert_error_response(
            response,
            "BAD_REQUEST",
            "Money must be a positive integer",
        )

    def test_set_money(self, client: socket.socket) -> None:
        """Test that set succeeds when money is positive."""
        gamestate = load_fixture(client, "set", "state-SELECTING_HAND")
        assert gamestate["state"] == "SELECTING_HAND"
        response = api(client, "set", {"money": 100})
        assert response["money"] == 100

    def test_set_negative_chips(self, client: socket.socket) -> None:
        """Test that set fails when chips is negative."""
        gamestate = load_fixture(client, "set", "state-SELECTING_HAND")
        assert gamestate["state"] == "SELECTING_HAND"
        response = api(client, "set", {"chips": -100})
        assert_error_response(
            response,
            "BAD_REQUEST",
            "Chips must be a positive integer",
        )

    def test_set_chips(self, client: socket.socket) -> None:
        """Test that set succeeds when chips is positive."""
        gamestate = load_fixture(client, "set", "state-SELECTING_HAND")
        assert gamestate["state"] == "SELECTING_HAND"
        response = api(client, "set", {"chips": 100})
        assert response["round"]["chips"] == 100

    def test_set_negative_ante(self, client: socket.socket) -> None:
        """Test that set fails when ante is negative."""
        gamestate = load_fixture(client, "set", "state-SELECTING_HAND")
        assert gamestate["state"] == "SELECTING_HAND"
        response = api(client, "set", {"ante": -8})
        assert_error_response(
            response,
            "BAD_REQUEST",
            "Ante must be a positive integer",
        )

    def test_set_ante(self, client: socket.socket) -> None:
        """Test that set succeeds when ante is positive."""
        gamestate = load_fixture(client, "set", "state-SELECTING_HAND")
        assert gamestate["state"] == "SELECTING_HAND"
        response = api(client, "set", {"ante": 8})
        assert response["ante_num"] == 8

    def test_set_negative_round(self, client: socket.socket) -> None:
        """Test that set fails when round is negative."""
        gamestate = load_fixture(client, "set", "state-SELECTING_HAND")
        assert gamestate["state"] == "SELECTING_HAND"
        response = api(client, "set", {"round": -5})
        assert_error_response(
            response,
            "BAD_REQUEST",
            "Round must be a positive integer",
        )

    def test_set_round(self, client: socket.socket) -> None:
        """Test that set succeeds when round is positive."""
        gamestate = load_fixture(client, "set", "state-SELECTING_HAND")
        assert gamestate["state"] == "SELECTING_HAND"
        response = api(client, "set", {"round": 5})
        assert response["round_num"] == 5

    def test_set_negative_hands(self, client: socket.socket) -> None:
        """Test that set fails when hands is negative."""
        gamestate = load_fixture(client, "set", "state-SELECTING_HAND")
        assert gamestate["state"] == "SELECTING_HAND"
        response = api(client, "set", {"hands": -10})
        assert_error_response(
            response,
            "BAD_REQUEST",
            "Hands must be a positive integer",
        )

    def test_set_hands(self, client: socket.socket) -> None:
        """Test that set succeeds when hands is positive."""
        gamestate = load_fixture(client, "set", "state-SELECTING_HAND")
        assert gamestate["state"] == "SELECTING_HAND"
        response = api(client, "set", {"hands": 10})
        assert response["round"]["hands_left"] == 10

    def test_set_negative_discards(self, client: socket.socket) -> None:
        """Test that set fails when discards is negative."""
        gamestate = load_fixture(client, "set", "state-SELECTING_HAND")
        assert gamestate["state"] == "SELECTING_HAND"
        response = api(client, "set", {"discards": -10})
        assert_error_response(
            response,
            "BAD_REQUEST",
            "Discards must be a positive integer",
        )

    def test_set_discards(self, client: socket.socket) -> None:
        """Test that set succeeds when discards is positive."""
        gamestate = load_fixture(client, "set", "state-SELECTING_HAND")
        assert gamestate["state"] == "SELECTING_HAND"
        response = api(client, "set", {"discards": 10})
        assert response["round"]["discards_left"] == 10

    def test_set_shop_from_selecting_hand(self, client: socket.socket) -> None:
        """Test that set fails when shop is called from SELECTING_HAND state."""
        gamestate = load_fixture(client, "set", "state-SELECTING_HAND")
        assert gamestate["state"] == "SELECTING_HAND"
        response = api(client, "set", {"shop": True})
        assert_error_response(
            response,
            "NOT_ALLOWED",
            "Can re-stock shop only in SHOP state",
        )

    def test_set_shop_from_SHOP(self, client: socket.socket) -> None:
        """Test that set fails when shop is called from SHOP state."""
        gamestate = load_fixture(client, "set", "state-SHOP")
        assert gamestate["state"] == "SHOP"
        before = gamestate
        after = api(client, "set", {"shop": True})
        assert len(after["shop"]["cards"]) > 0
        assert len(before["shop"]["cards"]) > 0
        assert after["shop"] != before["shop"]
        assert after["packs"] != before["packs"]
        assert after["vouchers"] != before["vouchers"]  # here only the id is changed

    def test_set_shop_set_round_set_money(self, client: socket.socket) -> None:
        """Test that set fails when shop is called from SHOP state."""
        gamestate = load_fixture(client, "set", "state-SHOP")
        assert gamestate["state"] == "SHOP"
        before = gamestate
        after = api(client, "set", {"shop": True, "round": 5, "money": 100})
        assert after["shop"] != before["shop"]
        assert after["packs"] != before["packs"]
        assert after["vouchers"] != before["vouchers"]  # here only the id is changed
        assert after["round_num"] == 5
        assert after["money"] == 100


class TestSetEndpointValidation:
    """Test set endpoint parameter validation."""

    def test_invalid_money_type(self, client: socket.socket):
        """Test that set fails when money parameter is not an integer."""
        gamestate = load_fixture(client, "set", "state-SELECTING_HAND")
        assert gamestate["state"] == "SELECTING_HAND"
        response = api(client, "set", {"money": "INVALID_STRING"})
        assert_error_response(
            response,
            "BAD_REQUEST",
            "Field 'money' must be an integer",
        )

    def test_invalid_chips_type(self, client: socket.socket):
        """Test that set fails when chips parameter is not an integer."""
        gamestate = load_fixture(client, "set", "state-SELECTING_HAND")
        assert gamestate["state"] == "SELECTING_HAND"
        response = api(client, "set", {"chips": "INVALID_STRING"})
        assert_error_response(
            response,
            "BAD_REQUEST",
            "Field 'chips' must be an integer",
        )

    def test_invalid_ante_type(self, client: socket.socket):
        """Test that set fails when ante parameter is not an integer."""
        gamestate = load_fixture(client, "set", "state-SELECTING_HAND")
        assert gamestate["state"] == "SELECTING_HAND"
        response = api(client, "set", {"ante": "INVALID_STRING"})
        assert_error_response(
            response,
            "BAD_REQUEST",
            "Field 'ante' must be an integer",
        )

    def test_invalid_round_type(self, client: socket.socket):
        """Test that set fails when round parameter is not an integer."""
        gamestate = load_fixture(client, "set", "state-SELECTING_HAND")
        assert gamestate["state"] == "SELECTING_HAND"
        response = api(client, "set", {"round": "INVALID_STRING"})
        assert_error_response(
            response,
            "BAD_REQUEST",
            "Field 'round' must be an integer",
        )

    def test_invalid_hands_type(self, client: socket.socket):
        """Test that set fails when hands parameter is not an integer."""
        gamestate = load_fixture(client, "set", "state-SELECTING_HAND")
        assert gamestate["state"] == "SELECTING_HAND"
        response = api(client, "set", {"hands": "INVALID_STRING"})
        assert_error_response(
            response,
            "BAD_REQUEST",
            "Field 'hands' must be an integer",
        )

    def test_invalid_discards_type(self, client: socket.socket):
        """Test that set fails when discards parameter is not an integer."""
        gamestate = load_fixture(client, "set", "state-SELECTING_HAND")
        assert gamestate["state"] == "SELECTING_HAND"
        response = api(client, "set", {"discards": "INVALID_STRING"})
        assert_error_response(
            response,
            "BAD_REQUEST",
            "Field 'discards' must be an integer",
        )

    def test_invalid_shop_type(self, client: socket.socket):
        """Test that set fails when shop parameter is not a boolean."""
        gamestate = load_fixture(client, "set", "state-SHOP")
        assert gamestate["state"] == "SHOP"
        response = api(client, "set", {"shop": "INVALID_STRING"})
        assert_error_response(
            response,
            "BAD_REQUEST",
            "Field 'shop' must be of type boolean",
        )
