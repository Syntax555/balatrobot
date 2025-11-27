"""Tests for src/lua/endpoints/add.lua"""

import socket

from tests.lua.conftest import api, assert_error_response, load_fixture


class TestAddEndpoint:
    """Test basic add endpoint functionality."""

    def test_add_joker(self, client: socket.socket) -> None:
        """Test adding a joker with valid key."""
        gamestate = load_fixture(
            client,
            "add",
            "state-SELECTING_HAND--jokers.count-0--consumables.count-0--hand.count-8",
        )
        assert gamestate["state"] == "SELECTING_HAND"
        assert gamestate["jokers"]["count"] == 0
        response = api(client, "add", {"key": "j_joker"})
        assert response["jokers"]["count"] == 1
        assert response["jokers"]["cards"][0]["key"] == "j_joker"

    def test_add_consumable_tarot(self, client: socket.socket) -> None:
        """Test adding a tarot consumable with valid key."""
        gamestate = load_fixture(
            client,
            "add",
            "state-SELECTING_HAND--jokers.count-0--consumables.count-0--hand.count-8",
        )
        assert gamestate["state"] == "SELECTING_HAND"
        assert gamestate["consumables"]["count"] == 0
        response = api(client, "add", {"key": "c_fool"})
        assert response["consumables"]["count"] == 1
        assert response["consumables"]["cards"][0]["key"] == "c_fool"

    def test_add_consumable_planet(self, client: socket.socket) -> None:
        """Test adding a planet consumable with valid key."""
        gamestate = load_fixture(
            client,
            "add",
            "state-SELECTING_HAND--jokers.count-0--consumables.count-0--hand.count-8",
        )
        assert gamestate["state"] == "SELECTING_HAND"
        assert gamestate["consumables"]["count"] == 0
        response = api(client, "add", {"key": "c_mercury"})
        assert response["consumables"]["count"] == 1
        assert response["consumables"]["cards"][0]["key"] == "c_mercury"

    def test_add_consumable_spectral(self, client: socket.socket) -> None:
        """Test adding a spectral consumable with valid key."""
        gamestate = load_fixture(
            client,
            "add",
            "state-SELECTING_HAND--jokers.count-0--consumables.count-0--hand.count-8",
        )
        assert gamestate["state"] == "SELECTING_HAND"
        assert gamestate["consumables"]["count"] == 0
        response = api(client, "add", {"key": "c_familiar"})
        assert response["consumables"]["count"] == 1
        assert response["consumables"]["cards"][0]["key"] == "c_familiar"

    def test_add_voucher(self, client: socket.socket) -> None:
        """Test adding a voucher with valid key in SHOP state."""
        gamestate = load_fixture(
            client,
            "add",
            "state-SHOP--jokers.count-0--consumables.count-0--vouchers.count-0",
        )
        assert gamestate["state"] == "SHOP"
        assert gamestate["vouchers"]["count"] == 0
        response = api(client, "add", {"key": "v_overstock_norm"})
        assert response["vouchers"]["count"] == 1
        assert response["vouchers"]["cards"][0]["key"] == "v_overstock_norm"

    def test_add_playing_card(self, client: socket.socket) -> None:
        """Test adding a playing card with valid key."""
        gamestate = load_fixture(
            client,
            "add",
            "state-SELECTING_HAND--jokers.count-0--consumables.count-0--hand.count-8",
        )
        assert gamestate["state"] == "SELECTING_HAND"
        assert gamestate["hand"]["count"] == 8
        response = api(client, "add", {"key": "H_A"})
        assert response["hand"]["count"] == 9
        assert response["hand"]["cards"][8]["key"] == "H_A"

    def test_add_no_key_provided(self, client: socket.socket) -> None:
        """Test add endpoint with no key parameter."""
        gamestate = load_fixture(
            client,
            "add",
            "state-SELECTING_HAND--jokers.count-0--consumables.count-0--hand.count-8",
        )
        assert gamestate["state"] == "SELECTING_HAND"
        assert_error_response(
            api(client, "add", {}),
            "SCHEMA_MISSING_REQUIRED",
            "Missing required field 'key'",
        )


class TestAddEndpointValidation:
    """Test add endpoint parameter validation."""

    def test_invalid_key_type_number(self, client: socket.socket) -> None:
        """Test that add fails when key parameter is a number."""
        gamestate = load_fixture(
            client,
            "add",
            "state-SELECTING_HAND--jokers.count-0--consumables.count-0--hand.count-8",
        )
        assert gamestate["state"] == "SELECTING_HAND"
        assert_error_response(
            api(client, "add", {"key": 123}),
            "SCHEMA_INVALID_TYPE",
            "Field 'key' must be of type string",
        )

    def test_invalid_key_unknown_format(self, client: socket.socket) -> None:
        """Test that add fails when key has unknown prefix format."""
        gamestate = load_fixture(
            client,
            "add",
            "state-SELECTING_HAND--jokers.count-0--consumables.count-0--hand.count-8",
        )
        assert gamestate["state"] == "SELECTING_HAND"
        assert_error_response(
            api(client, "add", {"key": "x_unknown"}),
            "SCHEMA_INVALID_VALUE",
            "Invalid card key format. Expected: joker (j_*), consumable (c_*), voucher (v_*), or playing card (SUIT_RANK)",
        )

    def test_invalid_key_known_format(self, client: socket.socket) -> None:
        """Test that add fails when key has known format."""
        gamestate = load_fixture(
            client,
            "add",
            "state-SELECTING_HAND--jokers.count-0--consumables.count-0--hand.count-8",
        )
        assert gamestate["state"] == "SELECTING_HAND"
        assert_error_response(
            api(client, "add", {"key": "j_NON_EXTING_JOKER"}),
            "SCHEMA_INVALID_VALUE",
            "Failed to add card: j_NON_EXTING_JOKER",
        )


class TestAddEndpointStateRequirements:
    """Test add endpoint state requirements."""

    def test_add_from_BLIND_SELECT(self, client: socket.socket) -> None:
        """Test that add fails from BLIND_SELECT state."""
        gamestate = load_fixture(client, "add", "state-BLIND_SELECT")
        assert gamestate["state"] == "BLIND_SELECT"
        assert_error_response(
            api(client, "add", {"key": "j_joker"}),
            "STATE_INVALID_STATE",
            "Endpoint 'add' requires one of these states: 1, 5, 8",
        )

    def test_add_playing_card_from_SHOP(self, client: socket.socket) -> None:
        """Test that add playing card fails from SHOP state."""
        gamestate = load_fixture(
            client,
            "add",
            "state-SHOP--jokers.count-0--consumables.count-0--vouchers.count-0",
        )
        assert gamestate["state"] == "SHOP"
        assert_error_response(
            api(client, "add", {"key": "H_A"}),
            "STATE_INVALID_STATE",
            "Playing cards can only be added in SELECTING_HAND state",
        )

    def test_add_voucher_card_from_SELECTING_HAND(self, client: socket.socket) -> None:
        """Test that add voucher card fails from SELECTING_HAND state."""
        gamestate = load_fixture(
            client,
            "add",
            "state-SELECTING_HAND--jokers.count-0--consumables.count-0--hand.count-8",
        )
        assert gamestate["state"] == "SELECTING_HAND"
        assert_error_response(
            api(client, "add", {"key": "v_overstock"}),
            "STATE_INVALID_STATE",
            "Vouchers can only be added in SHOP state",
        )
