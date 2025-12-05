"""Tests for src/lua/endpoints/rearrange.lua"""

import socket

from tests.lua.conftest import api, assert_error_response, load_fixture


class TestRearrangeEndpoint:
    """Test basic rearrange endpoint functionality."""

    def test_rearrange_hand(self, client: socket.socket) -> None:
        """Test rearranging hand in selecting hand state."""
        gamestate = load_fixture(
            client, "rearrange", "state-SELECTING_HAND--hand.count-8"
        )
        assert gamestate["state"] == "SELECTING_HAND"
        assert gamestate["hand"]["count"] == 8
        prev_ids = [card["id"] for card in gamestate["hand"]["cards"]]
        permutation = [1, 2, 0, 3, 4, 5, 7, 6]
        response = api(
            client,
            "rearrange",
            {"hand": permutation},
        )
        ids = [card["id"] for card in response["result"]["hand"]["cards"]]
        assert ids == [prev_ids[i] for i in permutation]

    def test_rearrange_jokers(self, client: socket.socket) -> None:
        """Test rearranging jokers."""
        gamestate = load_fixture(
            client, "rearrange", "state-SHOP--jokers.count-4--consumables.count-2"
        )
        assert gamestate["state"] == "SHOP"
        assert gamestate["jokers"]["count"] == 4
        prev_ids = [card["id"] for card in gamestate["jokers"]["cards"]]
        permutation = [2, 0, 1, 3]
        response = api(
            client,
            "rearrange",
            {"jokers": permutation},
        )
        ids = [card["id"] for card in response["result"]["jokers"]["cards"]]
        assert ids == [prev_ids[i] for i in permutation]

    def test_rearrange_consumables(self, client: socket.socket) -> None:
        """Test rearranging consumables."""
        gamestate = load_fixture(
            client, "rearrange", "state-SHOP--jokers.count-4--consumables.count-2"
        )
        assert gamestate["state"] == "SHOP"
        assert gamestate["consumables"]["count"] == 2
        prev_ids = [card["id"] for card in gamestate["consumables"]["cards"]]
        permutation = [1, 0]
        response = api(
            client,
            "rearrange",
            {"consumables": permutation},
        )
        ids = [card["id"] for card in response["result"]["consumables"]["cards"]]
        assert ids == [prev_ids[i] for i in permutation]


class TestRearrangeEndpointValidation:
    """Test rearrange endpoint parameter validation."""

    def test_no_parameters_provided(self, client: socket.socket) -> None:
        """Test error when no rearrange type specified."""
        gamestate = load_fixture(
            client, "rearrange", "state-SELECTING_HAND--hand.count-8"
        )
        assert gamestate["state"] == "SELECTING_HAND"
        response = api(client, "rearrange", {})
        assert_error_response(
            response,
            "BAD_REQUEST",
            "Must provide exactly one of: hand, jokers, or consumables",
        )

    def test_multiple_parameters_provided(self, client: socket.socket) -> None:
        """Test error when multiple rearrange types specified."""
        gamestate = load_fixture(
            client, "rearrange", "state-SELECTING_HAND--hand.count-8"
        )
        assert gamestate["state"] == "SELECTING_HAND"
        response = api(
            client, "rearrange", {"hand": [], "jokers": [], "consumables": []}
        )
        assert_error_response(
            response,
            "BAD_REQUEST",
            "Can only rearrange one type at a time",
        )

    def test_wrong_array_length_hand(self, client: socket.socket) -> None:
        """Test error when hand array wrong length."""
        gamestate = load_fixture(
            client, "rearrange", "state-SELECTING_HAND--hand.count-8"
        )
        assert gamestate["state"] == "SELECTING_HAND"
        assert gamestate["hand"]["count"] == 8
        response = api(
            client,
            "rearrange",
            {"hand": [0, 1, 2, 3]},
        )
        assert_error_response(
            response,
            "BAD_REQUEST",
            "Must provide exactly 8 indices for hand",
        )

    def test_wrong_array_length_jokers(self, client: socket.socket) -> None:
        """Test error when jokers array wrong length."""
        gamestate = load_fixture(
            client, "rearrange", "state-SHOP--jokers.count-4--consumables.count-2"
        )
        assert gamestate["state"] == "SHOP"
        assert gamestate["jokers"]["count"] == 4
        response = api(
            client,
            "rearrange",
            {"jokers": [0, 1, 2]},
        )
        assert_error_response(
            response,
            "BAD_REQUEST",
            "Must provide exactly 4 indices for jokers",
        )

    def test_wrong_array_length_consumables(self, client: socket.socket) -> None:
        """Test error when consumables array wrong length."""
        gamestate = load_fixture(
            client, "rearrange", "state-SHOP--jokers.count-4--consumables.count-2"
        )
        assert gamestate["state"] == "SHOP"
        assert gamestate["consumables"]["count"] == 2
        response = api(
            client,
            "rearrange",
            {"consumables": [0, 1, 2]},
        )
        assert_error_response(
            response,
            "BAD_REQUEST",
            "Must provide exactly 2 indices for consumables",
        )

    def test_invalid_card_index(self, client: socket.socket) -> None:
        """Test error when card index out of range."""
        gamestate = load_fixture(
            client, "rearrange", "state-SELECTING_HAND--hand.count-8"
        )
        assert gamestate["state"] == "SELECTING_HAND"
        assert gamestate["hand"]["count"] == 8
        response = api(
            client,
            "rearrange",
            {"hand": [-1, 1, 2, 3, 4, 5, 6, 7]},
        )
        assert_error_response(
            response,
            "BAD_REQUEST",
            "Index out of range for hand: -1",
        )

    def test_duplicate_indices(self, client: socket.socket) -> None:
        """Test error when indices contain duplicates."""
        gamestate = load_fixture(
            client, "rearrange", "state-SELECTING_HAND--hand.count-8"
        )
        assert gamestate["state"] == "SELECTING_HAND"
        assert gamestate["hand"]["count"] == 8
        response = api(
            client,
            "rearrange",
            {"hand": [1, 1, 2, 3, 4, 5, 6, 7]},
        )
        assert_error_response(
            response,
            "BAD_REQUEST",
            "Duplicate index in hand: 1",
        )


class TestRearrangeEndpointStateRequirements:
    """Test rearrange endpoint state requirements."""

    def test_rearrange_hand_from_wrong_state(self, client: socket.socket) -> None:
        """Test that rearranging hand fails from wrong state."""
        gamestate = load_fixture(client, "rearrange", "state-BLIND_SELECT")
        assert gamestate["state"] == "BLIND_SELECT"
        assert_error_response(
            api(client, "rearrange", {"hand": [0, 1, 2, 3, 4, 5, 6, 7]}),
            "INVALID_STATE",
            "Method 'rearrange' requires one of these states: SELECTING_HAND, SHOP",
        )

    def test_rearrange_jokers_from_wrong_state(self, client: socket.socket) -> None:
        """Test that rearranging jokers fails from wrong state."""
        gamestate = load_fixture(client, "rearrange", "state-BLIND_SELECT")
        assert gamestate["state"] == "BLIND_SELECT"
        assert_error_response(
            api(client, "rearrange", {"jokers": [0, 1, 2, 3, 4]}),
            "INVALID_STATE",
            "Method 'rearrange' requires one of these states: SELECTING_HAND, SHOP",
        )

    def test_rearrange_consumables_from_wrong_state(
        self, client: socket.socket
    ) -> None:
        """Test that rearranging consumables fails from wrong state."""
        gamestate = load_fixture(client, "rearrange", "state-BLIND_SELECT")
        assert gamestate["state"] == "BLIND_SELECT"
        assert_error_response(
            api(client, "rearrange", {"jokers": [0, 1]}),
            "INVALID_STATE",
            "Method 'rearrange' requires one of these states: SELECTING_HAND, SHOP",
        )

    def test_rearrange_hand_from_shop(self, client: socket.socket) -> None:
        """Test that rearranging hand fails from SHOP."""
        gamestate = load_fixture(
            client, "rearrange", "state-SHOP--jokers.count-4--consumables.count-2"
        )
        assert gamestate["state"] == "SHOP"
        assert_error_response(
            api(client, "rearrange", {"hand": [0, 1, 2, 3, 4, 5, 6, 7]}),
            "INVALID_STATE",
            "Can only rearrange hand during hand selection",
        )
