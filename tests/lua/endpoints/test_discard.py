"""Tests for src/lua/endpoints/discard.lua"""

import socket


from tests.lua.conftest import api, assert_error_response, get_fixture_path


class TestDiscardEndpoint:
    """Test basic discard endpoint functionality."""

    def test_discard_zero_cards(self, client: socket.socket) -> None:
        """Test discard endpoint with empty cards array."""
        save = "state-SELECTING_HAND.jkr"
        api(client, "load", {"path": str(get_fixture_path("discard", save))})
        response = api(client, "discard", {"cards": []})
        assert_error_response(
            response,
            expected_error_code="SCHEMA_INVALID_VALUE",
            expected_message_contains="Must provide at least one card to discard",
        )

    def test_discard_too_many_cards(self, client: socket.socket) -> None:
        """Test discard endpoint with more cards than limit."""
        save = "state-SELECTING_HAND.jkr"
        api(client, "load", {"path": str(get_fixture_path("discard", save))})
        response = api(client, "discard", {"cards": [0, 1, 2, 3, 4, 5]})
        assert_error_response(
            response,
            expected_error_code="SCHEMA_INVALID_VALUE",
            expected_message_contains="You can only discard 5 cards",
        )

    def test_discard_out_of_range_cards(self, client: socket.socket) -> None:
        """Test discard endpoint with invalid card index."""
        save = "state-SELECTING_HAND.jkr"
        api(client, "load", {"path": str(get_fixture_path("discard", save))})
        response = api(client, "discard", {"cards": [999]})
        assert_error_response(
            response,
            expected_error_code="SCHEMA_INVALID_VALUE",
            expected_message_contains="Invalid card index: 999",
        )

    def test_discard_no_discards_left(self, client: socket.socket) -> None:
        """Test discard endpoint when no discards remain."""
        save = "state-SELECTING_HAND--round.discards_left-0.jkr"
        api(client, "load", {"path": str(get_fixture_path("discard", save))})
        response = api(client, "discard", {"cards": [0]})
        assert_error_response(
            response,
            expected_error_code="SCHEMA_INVALID_VALUE",
            expected_message_contains="No discards left",
        )

    def test_discard_valid_single_card(self, client: socket.socket) -> None:
        """Test discard endpoint with valid single card."""
        save = "state-SELECTING_HAND.jkr"
        api(client, "load", {"path": str(get_fixture_path("discard", save))})
        before = api(client, "gamestate", {})
        after = api(client, "discard", {"cards": [0]})
        assert after["state"] == "SELECTING_HAND"
        assert after["round"]["discards_left"] == before["round"]["discards_left"] - 1

    def test_discard_valid_multiple_cards(self, client: socket.socket) -> None:
        """Test discard endpoint with valid multiple cards."""
        save = "state-SELECTING_HAND.jkr"
        api(client, "load", {"path": str(get_fixture_path("discard", save))})
        before = api(client, "gamestate", {})
        after = api(client, "discard", {"cards": [1, 2, 3]})
        assert after["state"] == "SELECTING_HAND"
        assert after["round"]["discards_left"] == before["round"]["discards_left"] - 1


class TestDiscardEndpointValidation:
    """Test discard endpoint parameter validation."""

    def test_missing_cards_parameter(self, client: socket.socket):
        """Test that discard fails when cards parameter is missing."""
        save = "state-SELECTING_HAND.jkr"
        api(client, "load", {"path": str(get_fixture_path("discard", save))})
        response = api(client, "discard", {})
        assert_error_response(
            response,
            expected_error_code="SCHEMA_MISSING_REQUIRED",
            expected_message_contains="Missing required field 'cards'",
        )

    def test_invalid_cards_type(self, client: socket.socket):
        """Test that discard fails when cards parameter is not an array."""
        save = "state-SELECTING_HAND.jkr"
        api(client, "load", {"path": str(get_fixture_path("discard", save))})
        response = api(client, "discard", {"cards": "INVALID_CARDS"})
        assert_error_response(
            response,
            expected_error_code="SCHEMA_INVALID_TYPE",
            expected_message_contains="Field 'cards' must be an array",
        )


class TestDiscardEndpointStateRequirements:
    """Test discard endpoint state requirements."""

    def test_discard_from_BLIND_SELECT(self, client: socket.socket):
        """Test that discard fails when not in SELECTING_HAND state."""
        save = "state-BLIND_SELECT.jkr"
        api(client, "load", {"path": str(get_fixture_path("discard", save))})
        response = api(client, "discard", {"cards": [0]})
        assert_error_response(
            response,
            expected_error_code="STATE_INVALID_STATE",
            expected_message_contains="Endpoint 'discard' requires one of these states:",
        )
