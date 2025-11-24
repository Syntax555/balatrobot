"""Tests for src/lua/endpoints/play.lua"""

import socket

from tests.lua.conftest import api, assert_error_response, get_fixture_path


class TestPlayEndpoint:
    """Test basic play endpoint functionality."""

    def test_play_zero_cards(self, client: socket.socket) -> None:
        """Test play endpoint from BLIND_SELECT state."""
        save = "state-SELECTING_HAND.jkr"
        api(client, "load", {"path": str(get_fixture_path("play", save))})
        response = api(client, "play", {"cards": []})
        assert_error_response(
            response,
            expected_error_code="SCHEMA_INVALID_VALUE",
            expected_message_contains="Must provide at least one card to play",
        )

    def test_play_six_cards(self, client: socket.socket) -> None:
        """Test play endpoint from BLIND_SELECT state."""
        save = "state-SELECTING_HAND.jkr"
        api(client, "load", {"path": str(get_fixture_path("play", save))})
        response = api(client, "play", {"cards": [0, 1, 2, 3, 4, 5]})
        assert_error_response(
            response,
            expected_error_code="SCHEMA_INVALID_VALUE",
            expected_message_contains="You can only play 5 cards",
        )

    def test_play_out_of_range_cards(self, client: socket.socket) -> None:
        """Test play endpoint from BLIND_SELECT state."""
        save = "state-SELECTING_HAND.jkr"
        api(client, "load", {"path": str(get_fixture_path("play", save))})
        response = api(client, "play", {"cards": [999]})
        assert_error_response(
            response,
            expected_error_code="SCHEMA_INVALID_VALUE",
            expected_message_contains="Invalid card index: 999",
        )

    def test_play_valid_cards_and_round_active(self, client: socket.socket) -> None:
        """Test play endpoint from BLIND_SELECT state."""
        save = "state-SELECTING_HAND.jkr"
        api(client, "load", {"path": str(get_fixture_path("play", save))})
        response = api(client, "play", {"cards": [0, 3, 4, 5, 6]})
        assert response["state"] == "SELECTING_HAND"
        assert response["hands"]["Flush"]["played_this_round"] == 1
        assert response["round"]["chips"] == 260

    def test_play_valid_cards_and_round_won(self, client: socket.socket) -> None:
        """Test play endpoint from BLIND_SELECT state."""
        save = "state-SELECTING_HAND--round.chips-200.jkr"
        api(client, "load", {"path": str(get_fixture_path("play", save))})
        response = api(client, "play", {"cards": [0, 3, 4, 5, 6]})
        assert response["state"] == "ROUND_EVAL"

    def test_play_valid_cards_and_game_won(self, client: socket.socket) -> None:
        """Test play endpoint from BLIND_SELECT state."""
        save = "state-SELECTING_HAND--ante_num-8--blinds.boss.status-CURRENT--round.chips-1000000.jkr"
        api(client, "load", {"path": str(get_fixture_path("play", save))})
        response = api(client, "play", {"cards": [0, 3, 4, 5, 6]})
        assert response["won"] is True

    def test_play_valid_cards_and_game_over(self, client: socket.socket) -> None:
        """Test play endpoint from BLIND_SELECT state."""
        save = "state-SELECTING_HAND--round.hands_left-1.jkr"
        api(client, "load", {"path": str(get_fixture_path("play", save))})
        # SMODS.calculate_context() in end_round() can take longer for game_over
        response = api(client, "play", {"cards": [0]}, timeout=5)
        assert response["state"] == "GAME_OVER"


class TestPlayEndpointValidation:
    """Test play endpoint parameter validation."""

    def test_missing_cards_parameter(self, client: socket.socket):
        """Test that play fails when cards parameter is missing."""
        save = "state-SELECTING_HAND.jkr"
        api(client, "load", {"path": str(get_fixture_path("play", save))})
        response = api(client, "play", {})
        assert_error_response(
            response,
            expected_error_code="SCHEMA_MISSING_REQUIRED",
            expected_message_contains="Missing required field 'cards'",
        )

    def test_invalid_cards_type(self, client: socket.socket):
        """Test that play fails when cards parameter is not an array."""
        save = "state-SELECTING_HAND.jkr"
        api(client, "load", {"path": str(get_fixture_path("play", save))})
        response = api(client, "play", {"cards": "INVALID_CARDS"})
        assert_error_response(
            response,
            expected_error_code="SCHEMA_INVALID_TYPE",
            expected_message_contains="Field 'cards' must be an array",
        )


class TestPlayEndpointStateRequirements:
    """Test play endpoint state requirements."""

    def test_play_from_BLIND_SELECT(self, client: socket.socket):
        """Test that play fails when not in SELECTING_HAND state."""
        save = "state-BLIND_SELECT.jkr"
        api(client, "load", {"path": str(get_fixture_path("play", save))})
        response = api(client, "play", {"cards": [0]})
        assert_error_response(
            response,
            expected_error_code="STATE_INVALID_STATE",
            expected_message_contains="Endpoint 'play' requires one of these states:",
        )
