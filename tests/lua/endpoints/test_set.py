"""Tests for src/lua/endpoints/set.lua"""

import socket

from tests.lua.conftest import api, assert_error_response, get_fixture_path


class TestSetEndpoint:
    """Test basic set endpoint functionality."""

    def test_set_game_not_in_run(self, client: socket.socket) -> None:
        """Test that set fails when game is not in run."""
        api(client, "menu", {})
        response = api(client, "set", {})
        assert_error_response(
            response,
            expected_error_code="GAME_NOT_IN_RUN",
            expected_message_contains="Can only set during an active run",
        )

    def test_set_no_fields(self, client: socket.socket) -> None:
        """Test that set fails when no fields are provided."""
        save = "state-SELECTING_HAND.jkr"
        api(client, "load", {"path": str(get_fixture_path("set", save))})
        response = api(client, "set", {})
        assert_error_response(
            response,
            expected_error_code="SCHEMA_INVALID_VALUE",
            expected_message_contains="Must provide at least one field to set",
        )

    def test_set_negative_money(self, client: socket.socket) -> None:
        """Test that set fails when money is negative."""
        save = "state-SELECTING_HAND.jkr"
        api(client, "load", {"path": str(get_fixture_path("set", save))})
        response = api(client, "set", {"money": -100})
        assert_error_response(
            response,
            expected_error_code="SCHEMA_INVALID_VALUE",
            expected_message_contains="Money must be a positive integer",
        )

    def test_set_money(self, client: socket.socket) -> None:
        """Test that set succeeds when money is positive."""
        save = "state-SELECTING_HAND.jkr"
        api(client, "load", {"path": str(get_fixture_path("set", save))})
        response = api(client, "set", {"money": 100})
        assert response["money"] == 100

    def test_set_negative_chips(self, client: socket.socket) -> None:
        """Test that set fails when chips is negative."""
        save = "state-SELECTING_HAND.jkr"
        api(client, "load", {"path": str(get_fixture_path("set", save))})
        response = api(client, "set", {"chips": -100})
        assert_error_response(
            response,
            expected_error_code="SCHEMA_INVALID_VALUE",
            expected_message_contains="Chips must be a positive integer",
        )

    def test_set_chips(self, client: socket.socket) -> None:
        """Test that set succeeds when chips is positive."""
        save = "state-SELECTING_HAND.jkr"
        api(client, "load", {"path": str(get_fixture_path("set", save))})
        response = api(client, "set", {"chips": 100})
        assert response["round"]["chips"] == 100

    def test_set_negative_ante(self, client: socket.socket) -> None:
        """Test that set fails when ante is negative."""
        save = "state-SELECTING_HAND.jkr"
        api(client, "load", {"path": str(get_fixture_path("set", save))})
        response = api(client, "set", {"ante": -8})
        assert_error_response(
            response,
            expected_error_code="SCHEMA_INVALID_VALUE",
            expected_message_contains="Ante must be a positive integer",
        )

    def test_set_ante(self, client: socket.socket) -> None:
        """Test that set succeeds when ante is positive."""
        save = "state-SELECTING_HAND.jkr"
        api(client, "load", {"path": str(get_fixture_path("set", save))})
        response = api(client, "set", {"ante": 8})
        assert response["ante_num"] == 8

    def test_set_negative_round(self, client: socket.socket) -> None:
        """Test that set fails when round is negative."""
        save = "state-SELECTING_HAND.jkr"
        api(client, "load", {"path": str(get_fixture_path("set", save))})
        response = api(client, "set", {"round": -5})
        assert_error_response(
            response,
            expected_error_code="SCHEMA_INVALID_VALUE",
            expected_message_contains="Round must be a positive integer",
        )

    def test_set_round(self, client: socket.socket) -> None:
        """Test that set succeeds when round is positive."""
        save = "state-SELECTING_HAND.jkr"
        api(client, "load", {"path": str(get_fixture_path("set", save))})
        response = api(client, "set", {"round": 5})
        assert response["round_num"] == 5

    def test_set_negative_hands(self, client: socket.socket) -> None:
        """Test that set fails when hands is negative."""
        save = "state-SELECTING_HAND.jkr"
        api(client, "load", {"path": str(get_fixture_path("set", save))})
        response = api(client, "set", {"hands": -10})
        assert_error_response(
            response,
            expected_error_code="SCHEMA_INVALID_VALUE",
            expected_message_contains="Hands must be a positive integer",
        )

    def test_set_hands(self, client: socket.socket) -> None:
        """Test that set succeeds when hands is positive."""
        save = "state-SELECTING_HAND.jkr"
        api(client, "load", {"path": str(get_fixture_path("set", save))})
        response = api(client, "set", {"hands": 10})
        assert response["round"]["hands_left"] == 10

    def test_set_negative_discards(self, client: socket.socket) -> None:
        """Test that set fails when discards is negative."""
        save = "state-SELECTING_HAND.jkr"
        api(client, "load", {"path": str(get_fixture_path("set", save))})
        response = api(client, "set", {"discards": -10})
        assert_error_response(
            response,
            expected_error_code="SCHEMA_INVALID_VALUE",
            expected_message_contains="Discards must be a positive integer",
        )

    def test_set_discards(self, client: socket.socket) -> None:
        """Test that set succeeds when discards is positive."""
        save = "state-SELECTING_HAND.jkr"
        api(client, "load", {"path": str(get_fixture_path("set", save))})
        response = api(client, "set", {"discards": 10})
        assert response["round"]["discards_left"] == 10

    def test_set_shop_from_selecting_hand(self, client: socket.socket) -> None:
        """Test that set fails when shop is called from SELECTING_HAND state."""
        save = "state-SELECTING_HAND.jkr"
        api(client, "load", {"path": str(get_fixture_path("set", save))})
        response = api(client, "set", {"shop": True})
        assert_error_response(
            response,
            expected_error_code="GAME_INVALID_STATE",
            expected_message_contains="Can re-stock shop only in SHOP state",
        )

    def test_set_shop_from_SHOP(self, client: socket.socket) -> None:
        """Test that set fails when shop is called from SHOP state."""
        save = "state-SHOP.jkr"
        response = api(client, "load", {"path": str(get_fixture_path("set", save))})
        assert "error" not in response
        before = api(client, "gamestate", {})
        after = api(client, "set", {"shop": True})
        assert len(after["shop"]["cards"]) > 0
        assert len(before["shop"]["cards"]) > 0
        assert after["shop"] != before["shop"]
        assert after["vouchers"] != before["vouchers"]


class TestSetEndpointValidation:
    """Test set endpoint parameter validation."""

    def test_invalid_money_type(self, client: socket.socket):
        """Test that set fails when money parameter is not an integer."""
        save = "state-SELECTING_HAND.jkr"
        api(client, "load", {"path": str(get_fixture_path("set", save))})
        response = api(client, "set", {"money": "INVALID_STRING"})
        assert_error_response(
            response,
            expected_error_code="SCHEMA_INVALID_TYPE",
            expected_message_contains="Field 'money' must be an integer",
        )

    def test_invalid_chips_type(self, client: socket.socket):
        """Test that set fails when chips parameter is not an integer."""
        save = "state-SELECTING_HAND.jkr"
        api(client, "load", {"path": str(get_fixture_path("set", save))})
        response = api(client, "set", {"chips": "INVALID_STRING"})
        assert_error_response(
            response,
            expected_error_code="SCHEMA_INVALID_TYPE",
            expected_message_contains="Field 'chips' must be an integer",
        )

    def test_invalid_ante_type(self, client: socket.socket):
        """Test that set fails when ante parameter is not an integer."""
        save = "state-SELECTING_HAND.jkr"
        api(client, "load", {"path": str(get_fixture_path("set", save))})
        response = api(client, "set", {"ante": "INVALID_STRING"})
        assert_error_response(
            response,
            expected_error_code="SCHEMA_INVALID_TYPE",
            expected_message_contains="Field 'ante' must be an integer",
        )

    def test_invalid_round_type(self, client: socket.socket):
        """Test that set fails when round parameter is not an integer."""
        save = "state-SELECTING_HAND.jkr"
        api(client, "load", {"path": str(get_fixture_path("set", save))})
        response = api(client, "set", {"round": "INVALID_STRING"})
        assert_error_response(
            response,
            expected_error_code="SCHEMA_INVALID_TYPE",
            expected_message_contains="Field 'round' must be an integer",
        )

    def test_invalid_hands_type(self, client: socket.socket):
        """Test that set fails when hands parameter is not an integer."""
        save = "state-SELECTING_HAND.jkr"
        api(client, "load", {"path": str(get_fixture_path("set", save))})
        response = api(client, "set", {"hands": "INVALID_STRING"})
        assert_error_response(
            response,
            expected_error_code="SCHEMA_INVALID_TYPE",
            expected_message_contains="Field 'hands' must be an integer",
        )

    def test_invalid_discards_type(self, client: socket.socket):
        """Test that set fails when discards parameter is not an integer."""
        save = "state-SELECTING_HAND.jkr"
        api(client, "load", {"path": str(get_fixture_path("set", save))})
        response = api(client, "set", {"discards": "INVALID_STRING"})
        assert_error_response(
            response,
            expected_error_code="SCHEMA_INVALID_TYPE",
            expected_message_contains="Field 'discards' must be an integer",
        )

    def test_invalid_shop_type(self, client: socket.socket):
        """Test that set fails when shop parameter is not a boolean."""
        save = "state-SHOP.jkr"
        api(client, "load", {"path": str(get_fixture_path("set", save))})
        response = api(client, "set", {"shop": "INVALID_STRING"})
        assert_error_response(
            response,
            expected_error_code="SCHEMA_INVALID_TYPE",
            expected_message_contains="Field 'shop' must be of type boolean",
        )
