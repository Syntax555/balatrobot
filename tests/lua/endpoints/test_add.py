"""Tests for src/lua/endpoints/add.lua"""

import socket

import pytest

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
            "BAD_REQUEST",
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
            "BAD_REQUEST",
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
            "BAD_REQUEST",
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
            "BAD_REQUEST",
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
            "INVALID_STATE",
            "Method 'add' requires one of these states: SELECTING_HAND, SHOP, ROUND_EVAL",
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
            "INVALID_STATE",
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
            "INVALID_STATE",
            "Vouchers can only be added in SHOP state",
        )


class TestAddEndpointSeal:
    """Test seal parameter for add endpoint."""

    @pytest.mark.parametrize("seal", ["RED", "BLUE", "GOLD", "PURPLE"])
    def test_add_playing_card_with_seal(self, client: socket.socket, seal: str) -> None:
        """Test adding a playing card with various seals."""
        gamestate = load_fixture(
            client,
            "add",
            "state-SELECTING_HAND--jokers.count-0--consumables.count-0--hand.count-8",
        )
        assert gamestate["state"] == "SELECTING_HAND"
        assert gamestate["hand"]["count"] == 8
        response = api(client, "add", {"key": "H_A", "seal": seal})
        assert response["hand"]["count"] == 9
        assert response["hand"]["cards"][8]["key"] == "H_A"
        assert response["hand"]["cards"][8]["modifier"]["seal"] == seal

    def test_add_playing_card_invalid_seal(self, client: socket.socket) -> None:
        """Test adding a playing card with invalid seal value."""
        gamestate = load_fixture(
            client,
            "add",
            "state-SELECTING_HAND--jokers.count-0--consumables.count-0--hand.count-8",
        )
        assert gamestate["state"] == "SELECTING_HAND"
        assert gamestate["hand"]["count"] == 8
        response = api(client, "add", {"key": "H_A", "seal": "WHITE"})
        assert_error_response(
            response,
            "BAD_REQUEST",
            "Invalid seal value. Expected: RED, BLUE, GOLD, or PURPLE",
        )

    @pytest.mark.parametrize("key", ["j_joker", "c_fool", "v_overstock_norm"])
    def test_add_non_playing_card_with_seal_fails(
        self, client: socket.socket, key: str
    ) -> None:
        """Test that adding non-playing cards with seal parameter fails."""
        gamestate = load_fixture(
            client,
            "add",
            "state-SHOP--jokers.count-0--consumables.count-0--vouchers.count-0",
        )
        assert gamestate["state"] == "SHOP"
        response = api(client, "add", {"key": key, "seal": "RED"})
        assert_error_response(
            response,
            "BAD_REQUEST",
            "Seal can only be applied to playing cards",
        )


class TestAddEndpointEdition:
    """Test edition parameter for add endpoint."""

    @pytest.mark.parametrize("edition", ["HOLO", "FOIL", "POLYCHROME", "NEGATIVE"])
    def test_add_joker_with_edition(self, client: socket.socket, edition: str) -> None:
        """Test adding a joker with various editions."""
        gamestate = load_fixture(
            client,
            "add",
            "state-SHOP--jokers.count-0--consumables.count-0--vouchers.count-0",
        )
        assert gamestate["state"] == "SHOP"
        assert gamestate["jokers"]["count"] == 0
        response = api(client, "add", {"key": "j_joker", "edition": edition})
        assert response["jokers"]["count"] == 1
        assert response["jokers"]["cards"][0]["key"] == "j_joker"
        assert response["jokers"]["cards"][0]["modifier"]["edition"] == edition

    @pytest.mark.parametrize("edition", ["HOLO", "FOIL", "POLYCHROME", "NEGATIVE"])
    def test_add_playing_card_with_edition(
        self, client: socket.socket, edition: str
    ) -> None:
        """Test adding a playing card with various editions."""
        gamestate = load_fixture(
            client,
            "add",
            "state-SELECTING_HAND--jokers.count-0--consumables.count-0--hand.count-8",
        )
        assert gamestate["state"] == "SELECTING_HAND"
        assert gamestate["hand"]["count"] == 8
        response = api(client, "add", {"key": "H_A", "edition": edition})
        assert response["hand"]["count"] == 9
        assert response["hand"]["cards"][8]["key"] == "H_A"
        assert response["hand"]["cards"][8]["modifier"]["edition"] == edition

    def test_add_consumable_with_negative_edition(self, client: socket.socket) -> None:
        """Test adding a consumable with NEGATIVE edition (only valid edition for consumables)."""
        gamestate = load_fixture(
            client,
            "add",
            "state-SHOP--jokers.count-0--consumables.count-0--vouchers.count-0",
        )
        assert gamestate["state"] == "SHOP"
        assert gamestate["consumables"]["count"] == 0
        response = api(client, "add", {"key": "c_fool", "edition": "NEGATIVE"})
        assert response["consumables"]["count"] == 1
        assert response["consumables"]["cards"][0]["key"] == "c_fool"
        assert response["consumables"]["cards"][0]["modifier"]["edition"] == "NEGATIVE"

    @pytest.mark.parametrize("edition", ["HOLO", "FOIL", "POLYCHROME"])
    def test_add_consumable_with_non_negative_edition_fails(
        self, client: socket.socket, edition: str
    ) -> None:
        """Test that adding a consumable with HOLO | FOIL | POLYCHROME edition fails."""
        gamestate = load_fixture(
            client,
            "add",
            "state-SHOP--jokers.count-0--consumables.count-0--vouchers.count-0",
        )
        assert gamestate["state"] == "SHOP"
        assert gamestate["consumables"]["count"] == 0
        response = api(client, "add", {"key": "c_fool", "edition": edition})
        assert_error_response(
            response,
            "BAD_REQUEST",
            "Consumables can only have NEGATIVE edition",
        )

    def test_add_voucher_with_edition_fails(self, client: socket.socket) -> None:
        """Test that adding a voucher with any edition fails."""
        gamestate = load_fixture(
            client,
            "add",
            "state-SHOP--jokers.count-0--consumables.count-0--vouchers.count-0",
        )
        assert gamestate["state"] == "SHOP"
        assert gamestate["vouchers"]["count"] == 0
        response = api(client, "add", {"key": "v_overstock_norm", "edition": "FOIL"})
        assert_error_response(
            response, "BAD_REQUEST", "Edition cannot be applied to vouchers"
        )

    def test_add_playing_card_invalid_edition(self, client: socket.socket) -> None:
        """Test adding a playing card with invalid edition value."""
        gamestate = load_fixture(
            client,
            "add",
            "state-SELECTING_HAND--jokers.count-0--consumables.count-0--hand.count-8",
        )
        assert gamestate["state"] == "SELECTING_HAND"
        assert gamestate["hand"]["count"] == 8
        response = api(client, "add", {"key": "H_A", "edition": "WHITE"})
        assert_error_response(
            response,
            "BAD_REQUEST",
            "Invalid edition value. Expected: HOLO, FOIL, POLYCHROME, or NEGATIVE",
        )


class TestAddEndpointEnhancement:
    """Test enhancement parameter for add endpoint."""

    @pytest.mark.parametrize(
        "enhancement",
        ["BONUS", "MULT", "WILD", "GLASS", "STEEL", "STONE", "GOLD", "LUCKY"],
    )
    def test_add_playing_card_with_enhancement(
        self, client: socket.socket, enhancement: str
    ) -> None:
        """Test adding a playing card with various enhancements."""
        gamestate = load_fixture(
            client,
            "add",
            "state-SELECTING_HAND--jokers.count-0--consumables.count-0--hand.count-8",
        )
        assert gamestate["state"] == "SELECTING_HAND"
        assert gamestate["hand"]["count"] == 8
        response = api(client, "add", {"key": "H_A", "enhancement": enhancement})
        assert response["hand"]["count"] == 9
        assert response["hand"]["cards"][8]["key"] == "H_A"
        assert response["hand"]["cards"][8]["modifier"]["enhancement"] == enhancement

    def test_add_playing_card_invalid_enhancement(self, client: socket.socket) -> None:
        """Test adding a playing card with invalid enhancement value."""
        gamestate = load_fixture(
            client,
            "add",
            "state-SELECTING_HAND--jokers.count-0--consumables.count-0--hand.count-8",
        )
        assert gamestate["state"] == "SELECTING_HAND"
        assert gamestate["hand"]["count"] == 8
        response = api(client, "add", {"key": "H_A", "enhancement": "WHITE"})
        assert_error_response(
            response,
            "BAD_REQUEST",
            "Invalid enhancement value. Expected: BONUS, MULT, WILD, GLASS, STEEL, STONE, GOLD, or LUCKY",
        )

    @pytest.mark.parametrize("key", ["j_joker", "c_fool", "v_overstock_norm"])
    def test_add_non_playing_card_with_enhancement_fails(
        self, client: socket.socket, key: str
    ) -> None:
        """Test that adding non-playing cards with enhancement parameter fails."""
        gamestate = load_fixture(
            client,
            "add",
            "state-SHOP--jokers.count-0--consumables.count-0--vouchers.count-0",
        )
        assert gamestate["state"] == "SHOP"
        assert gamestate["consumables"]["count"] == 0
        response = api(client, "add", {"key": key, "enhancement": "BONUS"})
        assert_error_response(
            response,
            "BAD_REQUEST",
            "Enhancement can only be applied to playing cards",
        )


class TestAddEndpointStickers:
    """Test sticker parameters (eternal, perishable) for add endpoint."""

    def test_add_joker_with_eternal(self, client: socket.socket) -> None:
        """Test adding an eternal joker."""
        gamestate = load_fixture(
            client,
            "add",
            "state-SHOP--jokers.count-0--consumables.count-0--vouchers.count-0",
        )
        assert gamestate["state"] == "SHOP"
        assert gamestate["jokers"]["count"] == 0
        response = api(client, "add", {"key": "j_joker", "eternal": True})
        assert response["jokers"]["count"] == 1
        assert response["jokers"]["cards"][0]["key"] == "j_joker"
        assert response["jokers"]["cards"][0]["modifier"]["eternal"] is True

    @pytest.mark.parametrize("key", ["c_fool", "v_overstock_norm"])
    def test_add_non_joker_with_eternal_fails(
        self, client: socket.socket, key: str
    ) -> None:
        """Test that adding non-joker cards with eternal parameter fails."""
        gamestate = load_fixture(
            client,
            "add",
            "state-SHOP--jokers.count-0--consumables.count-0--vouchers.count-0",
        )
        assert gamestate["state"] == "SHOP"
        assert gamestate["consumables"]["count"] == 0
        assert_error_response(
            api(client, "add", {"key": key, "eternal": True}),
            "BAD_REQUEST",
            "Eternal can only be applied to jokers",
        )

    def test_add_playing_card_with_eternal_fails(self, client: socket.socket) -> None:
        """Test that adding a playing card with eternal parameter fails."""
        gamestate = load_fixture(
            client,
            "add",
            "state-SELECTING_HAND--jokers.count-0--consumables.count-0--hand.count-8",
        )
        assert gamestate["state"] == "SELECTING_HAND"
        assert gamestate["hand"]["count"] == 8
        assert_error_response(
            api(client, "add", {"key": "H_A", "eternal": True}),
            "BAD_REQUEST",
            "Eternal can only be applied to jokers",
        )

    @pytest.mark.parametrize("rounds", [1, 5, 10])
    def test_add_joker_with_perishable(
        self, client: socket.socket, rounds: int
    ) -> None:
        """Test adding a perishable joker with valid round values."""
        gamestate = load_fixture(
            client,
            "add",
            "state-SHOP--jokers.count-0--consumables.count-0--vouchers.count-0",
        )
        assert gamestate["state"] == "SHOP"
        assert gamestate["jokers"]["count"] == 0
        response = api(client, "add", {"key": "j_joker", "perishable": rounds})
        assert response["jokers"]["count"] == 1
        assert response["jokers"]["cards"][0]["key"] == "j_joker"
        assert response["jokers"]["cards"][0]["modifier"]["perishable"] == rounds

    def test_add_joker_with_eternal_and_perishable(self, client: socket.socket) -> None:
        """Test adding a joker with both eternal and perishable stickers."""
        gamestate = load_fixture(
            client,
            "add",
            "state-SHOP--jokers.count-0--consumables.count-0--vouchers.count-0",
        )
        assert gamestate["state"] == "SHOP"
        assert gamestate["jokers"]["count"] == 0
        response = api(
            client, "add", {"key": "j_joker", "eternal": True, "perishable": 5}
        )
        assert response["jokers"]["count"] == 1
        assert response["jokers"]["cards"][0]["key"] == "j_joker"
        assert response["jokers"]["cards"][0]["modifier"]["eternal"] is True
        assert response["jokers"]["cards"][0]["modifier"]["perishable"] == 5

    @pytest.mark.parametrize("invalid_value", [0, -1])
    def test_add_joker_with_perishable_invalid_integer_fails(
        self, client: socket.socket, invalid_value: int
    ) -> None:
        """Test that invalid perishable values (zero, negative, float) are rejected."""
        gamestate = load_fixture(
            client,
            "add",
            "state-SHOP--jokers.count-0--consumables.count-0--vouchers.count-0",
        )
        assert gamestate["state"] == "SHOP"
        assert gamestate["jokers"]["count"] == 0
        response = api(client, "add", {"key": "j_joker", "perishable": invalid_value})
        assert_error_response(
            response,
            "BAD_REQUEST",
            "Perishable must be a positive integer (>= 1)",
        )

    @pytest.mark.parametrize("invalid_value", [1.5, "NOT_INT_1"])
    def test_add_joker_with_perishable_invalid_type_fails(
        self, client: socket.socket, invalid_value: float | str
    ) -> None:
        """Test that perishable with string value is rejected."""
        gamestate = load_fixture(
            client,
            "add",
            "state-SHOP--jokers.count-0--consumables.count-0--vouchers.count-0",
        )
        assert gamestate["state"] == "SHOP"
        assert gamestate["jokers"]["count"] == 0
        response = api(client, "add", {"key": "j_joker", "perishable": invalid_value})
        assert_error_response(
            response,
            "BAD_REQUEST",
            "Field 'perishable' must be an integer",
        )

    @pytest.mark.parametrize("key", ["c_fool", "v_overstock_norm"])
    def test_add_non_joker_with_perishable_fails(
        self, client: socket.socket, key: str
    ) -> None:
        """Test that adding non-joker cards with perishable parameter fails."""
        gamestate = load_fixture(
            client,
            "add",
            "state-SHOP--jokers.count-0--consumables.count-0--vouchers.count-0",
        )
        assert gamestate["state"] == "SHOP"
        response = api(client, "add", {"key": key, "perishable": 5})
        assert_error_response(
            response,
            "BAD_REQUEST",
            "Perishable can only be applied to jokers",
        )

    def test_add_playing_card_with_perishable_fails(
        self, client: socket.socket
    ) -> None:
        """Test that adding a playing card with perishable parameter fails."""
        gamestate = load_fixture(
            client,
            "add",
            "state-SELECTING_HAND--jokers.count-0--consumables.count-0--hand.count-8",
        )
        assert gamestate["state"] == "SELECTING_HAND"
        assert gamestate["hand"]["count"] == 8
        response = api(client, "add", {"key": "H_A", "perishable": 5})
        assert_error_response(
            response,
            "BAD_REQUEST",
            "Perishable can only be applied to jokers",
        )

    def test_add_joker_with_rental(self, client: socket.socket) -> None:
        """Test adding a rental joker."""
        gamestate = load_fixture(
            client,
            "add",
            "state-SHOP--jokers.count-0--consumables.count-0--vouchers.count-0",
        )
        assert gamestate["state"] == "SHOP"
        assert gamestate["jokers"]["count"] == 0
        response = api(client, "add", {"key": "j_joker", "rental": True})
        assert response["jokers"]["count"] == 1
        assert response["jokers"]["cards"][0]["key"] == "j_joker"
        assert response["jokers"]["cards"][0]["modifier"]["rental"] is True

    @pytest.mark.parametrize("key", ["c_fool", "v_overstock_norm"])
    def test_add_non_joker_with_rental_fails(
        self, client: socket.socket, key: str
    ) -> None:
        """Test that rental can only be applied to jokers."""
        gamestate = load_fixture(
            client,
            "add",
            "state-SHOP--jokers.count-0--consumables.count-0--vouchers.count-0",
        )
        assert gamestate["state"] == "SHOP"
        assert gamestate["jokers"]["count"] == 0
        assert_error_response(
            api(client, "add", {"key": key, "rental": True}),
            "BAD_REQUEST",
            "Rental can only be applied to jokers",
        )

    def test_add_joker_with_rental_and_eternal(self, client: socket.socket) -> None:
        """Test adding a joker with both rental and eternal stickers."""
        gamestate = load_fixture(
            client,
            "add",
            "state-SHOP--jokers.count-0--consumables.count-0--vouchers.count-0",
        )
        assert gamestate["state"] == "SHOP"
        assert gamestate["jokers"]["count"] == 0
        response = api(
            client, "add", {"key": "j_joker", "rental": True, "eternal": True}
        )
        assert response["jokers"]["count"] == 1
        assert response["jokers"]["cards"][0]["key"] == "j_joker"
        assert response["jokers"]["cards"][0]["modifier"]["rental"] is True
        assert response["jokers"]["cards"][0]["modifier"]["eternal"] is True

    def test_add_playing_card_with_rental_fails(self, client: socket.socket) -> None:
        """Test that rental cannot be applied to playing cards."""
        gamestate = load_fixture(
            client,
            "add",
            "state-SELECTING_HAND--jokers.count-0--consumables.count-0--hand.count-8",
        )
        assert gamestate["state"] == "SELECTING_HAND"
        assert gamestate["hand"]["count"] == 8
        assert_error_response(
            api(client, "add", {"key": "H_A", "rental": True}),
            "BAD_REQUEST",
            "Rental can only be applied to jokers",
        )
