"""Tests for src/lua/endpoints/discard.lua"""

import socket

from tests.lua.conftest import api, assert_error_response, load_fixture


class TestDiscardEndpoint:
    """Test basic discard endpoint functionality."""

    def test_discard_zero_cards(self, client: socket.socket) -> None:
        """Test discard endpoint with empty cards array."""
        gamestate = load_fixture(client, "discard", "state-SELECTING_HAND")
        assert gamestate["state"] == "SELECTING_HAND"
        assert_error_response(
            api(client, "discard", {"cards": []}),
            "SCHEMA_INVALID_VALUE",
            "Must provide at least one card to discard",
        )

    def test_discard_too_many_cards(self, client: socket.socket) -> None:
        """Test discard endpoint with more cards than limit."""
        gamestate = load_fixture(client, "discard", "state-SELECTING_HAND")
        assert gamestate["state"] == "SELECTING_HAND"
        assert_error_response(
            api(client, "discard", {"cards": [0, 1, 2, 3, 4, 5]}),
            "SCHEMA_INVALID_VALUE",
            "You can only discard 5 cards",
        )

    def test_discard_out_of_range_cards(self, client: socket.socket) -> None:
        """Test discard endpoint with invalid card index."""
        gamestate = load_fixture(client, "discard", "state-SELECTING_HAND")
        assert gamestate["state"] == "SELECTING_HAND"
        assert_error_response(
            api(client, "discard", {"cards": [999]}),
            "SCHEMA_INVALID_VALUE",
            "Invalid card index: 999",
        )

    def test_discard_no_discards_left(self, client: socket.socket) -> None:
        """Test discard endpoint when no discards remain."""
        gamestate = load_fixture(
            client, "discard", "state-SELECTING_HAND--round.discards_left-0"
        )
        assert gamestate["state"] == "SELECTING_HAND"
        assert gamestate["round"]["discards_left"] == 0
        assert_error_response(
            api(client, "discard", {"cards": [0]}),
            "SCHEMA_INVALID_VALUE",
            "No discards left",
        )

    def test_discard_valid_single_card(self, client: socket.socket) -> None:
        """Test discard endpoint with valid single card."""
        gamestate = load_fixture(client, "discard", "state-SELECTING_HAND")
        assert gamestate["state"] == "SELECTING_HAND"
        response = api(client, "discard", {"cards": [0]})
        assert response["state"] == "SELECTING_HAND"
        assert (
            response["round"]["discards_left"]
            == gamestate["round"]["discards_left"] - 1
        )

    def test_discard_valid_multiple_cards(self, client: socket.socket) -> None:
        """Test discard endpoint with valid multiple cards."""
        gamestate = load_fixture(client, "discard", "state-SELECTING_HAND")
        assert gamestate["state"] == "SELECTING_HAND"
        response = api(client, "discard", {"cards": [1, 2, 3]})
        assert response["state"] == "SELECTING_HAND"
        assert (
            response["round"]["discards_left"]
            == gamestate["round"]["discards_left"] - 1
        )


class TestDiscardEndpointValidation:
    """Test discard endpoint parameter validation."""

    def test_missing_cards_parameter(self, client: socket.socket):
        """Test that discard fails when cards parameter is missing."""
        gamestate = load_fixture(client, "discard", "state-SELECTING_HAND")
        assert gamestate["state"] == "SELECTING_HAND"
        assert_error_response(
            api(client, "discard", {}),
            "SCHEMA_MISSING_REQUIRED",
            "Missing required field 'cards'",
        )

    def test_invalid_cards_type(self, client: socket.socket):
        """Test that discard fails when cards parameter is not an array."""
        gamestate = load_fixture(client, "discard", "state-SELECTING_HAND")
        assert gamestate["state"] == "SELECTING_HAND"
        assert_error_response(
            api(client, "discard", {"cards": "INVALID_CARDS"}),
            "SCHEMA_INVALID_TYPE",
            "Field 'cards' must be an array",
        )


class TestDiscardEndpointStateRequirements:
    """Test discard endpoint state requirements."""

    def test_discard_from_BLIND_SELECT(self, client: socket.socket):
        """Test that discard fails when not in SELECTING_HAND state."""
        gamestate = load_fixture(client, "discard", "state-BLIND_SELECT")
        assert gamestate["state"] == "BLIND_SELECT"
        assert_error_response(
            api(client, "discard", {"cards": [0]}),
            "STATE_INVALID_STATE",
            "Endpoint 'discard' requires one of these states: SELECTING_HAND",
        )
