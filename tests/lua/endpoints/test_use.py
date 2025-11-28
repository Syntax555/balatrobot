"""Tests for src/lua/endpoints/use.lua"""

import socket

from tests.lua.conftest import api, assert_error_response, load_fixture


class TestUseEndpoint:
    """Test basic use endpoint functionality."""

    def test_use_hermit_no_cards(self, client: socket.socket) -> None:
        """Test using The Hermit (no card selection) in SHOP state."""
        gamestate = load_fixture(
            client,
            "use",
            "state-SHOP--money-12--consumables.cards[0]-key-c_hermit",
        )
        assert gamestate["state"] == "SHOP"
        assert gamestate["money"] == 12
        assert gamestate["consumables"]["cards"][0]["key"] == "c_hermit"
        response = api(client, "use", {"consumable": 0})
        assert response["money"] == 12 * 2

    def test_use_hermit_in_selecting_hand(self, client: socket.socket) -> None:
        """Test using The Hermit in SELECTING_HAND state."""
        gamestate = load_fixture(
            client,
            "use",
            "state-SELECTING_HAND--money-12--consumables.cards[0]-key-c_hermit",
        )
        assert gamestate["state"] == "SELECTING_HAND"
        assert gamestate["money"] == 12
        assert gamestate["consumables"]["cards"][0]["key"] == "c_hermit"
        response = api(client, "use", {"consumable": 0})
        assert response["money"] == 12 * 2

    def test_use_temperance_no_cards(self, client: socket.socket) -> None:
        """Test using Temperance (no card selection)."""
        gamestate = load_fixture(
            client,
            "use",
            "state-SELECTING_HAND--consumables.cards[0]-key-c_temperance--jokers.count-0",
        )
        assert gamestate["state"] == "SELECTING_HAND"
        assert gamestate["jokers"]["count"] == 0  # no jokers => no money increase
        assert gamestate["consumables"]["cards"][0]["key"] == "c_temperance"
        response = api(client, "use", {"consumable": 0})
        assert response["money"] == gamestate["money"]

    def test_use_planet_no_cards(self, client: socket.socket) -> None:
        """Test using a Planet card (no card selection)."""
        gamestate = load_fixture(
            client,
            "use",
            "state-SELECTING_HAND--consumables.cards[0].key-c_pluto--consumables.cards[1].key-c_magician",
        )
        assert gamestate["state"] == "SELECTING_HAND"
        assert gamestate["hands"]["High Card"]["level"] == 1
        response = api(client, "use", {"consumable": 0})
        assert response["hands"]["High Card"]["level"] == 2

    def test_use_magician_with_one_card(self, client: socket.socket) -> None:
        """Test using The Magician with 1 card (min=1, max=2)."""
        gamestate = load_fixture(
            client,
            "use",
            "state-SELECTING_HAND--consumables.cards[0].key-c_pluto--consumables.cards[1].key-c_magician",
        )
        assert gamestate["state"] == "SELECTING_HAND"
        response = api(client, "use", {"consumable": 1, "cards": [0]})
        assert response["hand"]["cards"][0]["modifier"]["enhancement"] == "LUCKY"

    def test_use_magician_with_two_cards(self, client: socket.socket) -> None:
        """Test using The Magician with 2 cards."""
        gamestate = load_fixture(
            client,
            "use",
            "state-SELECTING_HAND--consumables.cards[0].key-c_pluto--consumables.cards[1].key-c_magician",
        )
        assert gamestate["state"] == "SELECTING_HAND"
        response = api(client, "use", {"consumable": 1, "cards": [7, 5]})
        assert response["hand"]["cards"][5]["modifier"]["enhancement"] == "LUCKY"
        assert response["hand"]["cards"][7]["modifier"]["enhancement"] == "LUCKY"

    def test_use_familiar_all_hand(self, client: socket.socket) -> None:
        """Test using Familiar (destroys cards, #G.hand.cards > 1)."""
        gamestate = load_fixture(
            client,
            "use",
            "state-SELECTING_HAND--consumables.cards[0]-key-c_familiar",
        )
        assert gamestate["state"] == "SELECTING_HAND"
        response = api(client, "use", {"consumable": 0})
        assert response["hand"]["count"] == gamestate["hand"]["count"] - 1 + 3
        assert response["hand"]["cards"][7]["set"] == "ENHANCED"
        assert response["hand"]["cards"][8]["set"] == "ENHANCED"
        assert response["hand"]["cards"][9]["set"] == "ENHANCED"


class TestUseEndpointValidation:
    """Test use endpoint parameter validation."""

    def test_use_no_consumable_provided(self, client: socket.socket) -> None:
        """Test that use fails when consumable parameter is missing."""
        gamestate = load_fixture(
            client,
            "use",
            "state-SELECTING_HAND--consumables.cards[0].key-c_pluto--consumables.cards[1].key-c_magician",
        )
        assert gamestate["state"] == "SELECTING_HAND"
        assert_error_response(
            api(client, "use", {}),
            "SCHEMA_MISSING_REQUIRED",
            "Missing required field 'consumable'",
        )

    def test_use_invalid_consumable_type(self, client: socket.socket) -> None:
        """Test that use fails when consumable is not an integer."""
        gamestate = load_fixture(
            client,
            "use",
            "state-SELECTING_HAND--consumables.cards[0].key-c_pluto--consumables.cards[1].key-c_magician",
        )
        assert gamestate["state"] == "SELECTING_HAND"
        assert_error_response(
            api(client, "use", {"consumable": "NOT_AN_INTEGER"}),
            "SCHEMA_INVALID_TYPE",
            "Field 'consumable' must be an integer",
        )

    def test_use_invalid_consumable_index_negative(self, client: socket.socket) -> None:
        """Test that use fails when consumable index is negative."""
        gamestate = load_fixture(
            client,
            "use",
            "state-SELECTING_HAND--consumables.cards[0].key-c_pluto--consumables.cards[1].key-c_magician",
        )
        assert gamestate["state"] == "SELECTING_HAND"
        assert_error_response(
            api(client, "use", {"consumable": -1}),
            "SCHEMA_INVALID_VALUE",
            "Consumable index out of range: -1",
        )

    def test_use_invalid_consumable_index_too_high(self, client: socket.socket) -> None:
        """Test that use fails when consumable index >= count."""
        gamestate = load_fixture(
            client,
            "use",
            "state-SELECTING_HAND--consumables.cards[0].key-c_pluto--consumables.cards[1].key-c_magician",
        )
        assert gamestate["state"] == "SELECTING_HAND"
        assert_error_response(
            api(client, "use", {"consumable": 999}),
            "SCHEMA_INVALID_VALUE",
            "Consumable index out of range: 999",
        )

    def test_use_invalid_cards_type(self, client: socket.socket) -> None:
        """Test that use fails when cards is not an array."""
        gamestate = load_fixture(
            client,
            "use",
            "state-SELECTING_HAND--consumables.cards[0].key-c_pluto--consumables.cards[1].key-c_magician",
        )
        assert gamestate["state"] == "SELECTING_HAND"
        assert_error_response(
            api(client, "use", {"consumable": 1, "cards": "NOT_AN_ARRAY_OF_INTEGERS"}),
            "SCHEMA_INVALID_TYPE",
            "Field 'cards' must be an array",
        )

    def test_use_invalid_cards_item_type(self, client: socket.socket) -> None:
        """Test that use fails when cards array contains non-integer."""
        gamestate = load_fixture(
            client,
            "use",
            "state-SELECTING_HAND--consumables.cards[0].key-c_pluto--consumables.cards[1].key-c_magician",
        )
        assert gamestate["state"] == "SELECTING_HAND"
        assert_error_response(
            api(client, "use", {"consumable": 1, "cards": ["NOT_INT_1", "NOT_INT_2"]}),
            "SCHEMA_INVALID_ARRAY_ITEMS",
            "Field 'cards' array item at index 0 must be of type integer",
        )

    def test_use_invalid_card_index_negative(self, client: socket.socket) -> None:
        """Test that use fails when a card index is negative."""
        gamestate = load_fixture(
            client,
            "use",
            "state-SELECTING_HAND--consumables.cards[0].key-c_pluto--consumables.cards[1].key-c_magician",
        )
        assert gamestate["state"] == "SELECTING_HAND"
        assert_error_response(
            api(client, "use", {"consumable": 1, "cards": [-1]}),
            "SCHEMA_INVALID_VALUE",
            "Card index out of range: -1",
        )

    def test_use_invalid_card_index_too_high(self, client: socket.socket) -> None:
        """Test that use fails when a card index >= hand count."""
        gamestate = load_fixture(
            client,
            "use",
            "state-SELECTING_HAND--consumables.cards[0].key-c_pluto--consumables.cards[1].key-c_magician",
        )
        assert gamestate["state"] == "SELECTING_HAND"
        assert_error_response(
            api(client, "use", {"consumable": 1, "cards": [999]}),
            "SCHEMA_INVALID_VALUE",
            "Card index out of range: 999",
        )

    def test_use_magician_without_cards(self, client: socket.socket) -> None:
        """Test that using The Magician without cards parameter fails."""
        gamestate = load_fixture(
            client,
            "use",
            "state-SELECTING_HAND--consumables.cards[0].key-c_pluto--consumables.cards[1].key-c_magician",
        )
        assert gamestate["state"] == "SELECTING_HAND"
        assert gamestate["consumables"]["cards"][1]["key"] == "c_magician"
        assert_error_response(
            api(client, "use", {"consumable": 1}),
            "SCHEMA_MISSING_REQUIRED",
            "Consumable 'The Magician' requires card selection",
        )

    def test_use_magician_with_empty_cards(self, client: socket.socket) -> None:
        """Test that using The Magician with empty cards array fails."""
        gamestate = load_fixture(
            client,
            "use",
            "state-SELECTING_HAND--consumables.cards[0].key-c_pluto--consumables.cards[1].key-c_magician",
        )
        assert gamestate["state"] == "SELECTING_HAND"
        assert gamestate["consumables"]["cards"][1]["key"] == "c_magician"
        assert_error_response(
            api(client, "use", {"consumable": 1, "cards": []}),
            "SCHEMA_MISSING_REQUIRED",
            "Consumable 'The Magician' requires card selection",
        )

    def test_use_magician_too_many_cards(self, client: socket.socket) -> None:
        """Test that using The Magician with 3 cards fails (max=2)."""
        gamestate = load_fixture(
            client,
            "use",
            "state-SELECTING_HAND--consumables.cards[0].key-c_pluto--consumables.cards[1].key-c_magician",
        )
        assert gamestate["state"] == "SELECTING_HAND"
        assert gamestate["consumables"]["cards"][1]["key"] == "c_magician"
        assert_error_response(
            api(client, "use", {"consumable": 1, "cards": [0, 1, 2]}),
            "SCHEMA_INVALID_VALUE",
            "Consumable 'The Magician' requires at most 2 cards (provided: 3)",
        )

    def test_use_death_too_few_cards(self, client: socket.socket) -> None:
        """Test that using Death with 1 card fails (requires exactly 2)."""
        gamestate = load_fixture(
            client,
            "use",
            "state-SELECTING_HAND--consumables.cards[0].key-c_death",
        )
        assert gamestate["state"] == "SELECTING_HAND"
        assert gamestate["consumables"]["cards"][0]["key"] == "c_death"
        assert_error_response(
            api(client, "use", {"consumable": 0, "cards": [0]}),
            "SCHEMA_INVALID_VALUE",
            "Consumable 'Death' requires exactly 2 cards (provided: 1)",
        )

    def test_use_death_too_many_cards(self, client: socket.socket) -> None:
        """Test that using Death with 3 cards fails (requires exactly 2)."""
        gamestate = load_fixture(
            client,
            "use",
            "state-SELECTING_HAND--consumables.cards[0].key-c_death",
        )
        assert gamestate["state"] == "SELECTING_HAND"
        assert gamestate["consumables"]["cards"][0]["key"] == "c_death"
        assert_error_response(
            api(client, "use", {"consumable": 0, "cards": [0, 1, 2]}),
            "SCHEMA_INVALID_VALUE",
            "Consumable 'Death' requires exactly 2 cards (provided: 3)",
        )


class TestUseEndpointStateRequirements:
    """Test use endpoint state requirements."""

    def test_use_from_BLIND_SELECT(self, client: socket.socket) -> None:
        """Test that use fails from BLIND_SELECT state."""
        gamestate = load_fixture(
            client,
            "use",
            "state-BLIND_SELECT",
        )
        assert gamestate["state"] == "BLIND_SELECT"
        assert_error_response(
            api(client, "use", {"consumable": 0, "cards": [0]}),
            "STATE_INVALID_STATE",
            "Endpoint 'use' requires one of these states: 1, 5",
        )

    def test_use_from_ROUND_EVAL(self, client: socket.socket) -> None:
        """Test that use fails from ROUND_EVAL state."""
        gamestate = load_fixture(
            client,
            "use",
            "state-ROUND_EVAL",
        )
        assert gamestate["state"] == "ROUND_EVAL"
        assert_error_response(
            api(client, "use", {"consumable": 0, "cards": [0]}),
            "STATE_INVALID_STATE",
            "Endpoint 'use' requires one of these states: 1, 5",
        )

    def test_use_magician_from_SHOP(self, client: socket.socket) -> None:
        """Test that using The Magician fails from SHOP (needs SELECTING_HAND)."""
        gamestate = load_fixture(
            client,
            "use",
            "state-SHOP--consumables.cards[0].key-c_magician",
        )
        assert gamestate["state"] == "SHOP"
        assert gamestate["consumables"]["cards"][0]["key"] == "c_magician"
        assert_error_response(
            api(client, "use", {"consumable": 0, "cards": [0]}),
            "STATE_INVALID_STATE",
            "Consumable 'The Magician' requires card selection and can only be used in SELECTING_HAND state",
        )

    def test_use_familiar_from_SHOP(self, client: socket.socket) -> None:
        """Test that using The Magician fails from SHOP (needs SELECTING_HAND)."""
        gamestate = load_fixture(
            client,
            "use",
            "state-SHOP--consumables.cards[0]-key-c_familiar",
        )
        assert gamestate["state"] == "SHOP"
        assert gamestate["consumables"]["cards"][0]["key"] == "c_familiar"
        assert_error_response(
            api(client, "use", {"consumable": 0}),
            "GAME_INVALID_STATE",
            "Consumable 'Familiar' cannot be used at this time",
        )
