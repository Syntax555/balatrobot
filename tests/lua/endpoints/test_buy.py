"""Tests for src/lua/endpoints/buy.lua"""

import socket

import pytest

from tests.lua.conftest import api, assert_error_response, get_fixture_path


class TestBuyEndpoint:
    """Test basic buy endpoint functionality."""

    @pytest.mark.flaky(reruns=2)
    def test_buy_no_args(self, client: socket.socket) -> None:
        """Test buy endpoint with no arguments."""
        save = "state-SHOP--shop.cards[0].set-JOKER.jkr"
        api(client, "load", {"path": str(get_fixture_path("buy", save))})
        response = api(client, "buy", {})
        assert_error_response(
            response,
            expected_error_code="SCHEMA_INVALID_VALUE",
            expected_message_contains="Invalid arguments. You must provide one of: card, voucher, pack",
        )

    @pytest.mark.flaky(reruns=2)
    def test_buy_multi_args(self, client: socket.socket) -> None:
        """Test buy endpoint with multiple arguments."""
        save = "state-SHOP--shop.cards[0].set-JOKER.jkr"
        api(client, "load", {"path": str(get_fixture_path("buy", save))})
        response = api(client, "buy", {"card": 0, "voucher": 0})
        assert_error_response(
            response,
            expected_error_code="SCHEMA_INVALID_VALUE",
            expected_message_contains="Invalid arguments. Cannot provide more than one of: card, voucher, or pack",
        )

    def test_buy_no_card_in_shop_area(self, client: socket.socket) -> None:
        """Test buy endpoint with no card in shop area."""
        save = "state-SHOP--shop.count-0.jkr"
        api(client, "load", {"path": str(get_fixture_path("buy", save))})
        response = api(client, "buy", {"card": 0})
        assert_error_response(
            response,
            expected_error_code="SCHEMA_INVALID_VALUE",
            expected_message_contains="No jokers/consumables/cards in the shop. Reroll to restock the shop",
        )

    def test_buy_invalid_index(self, client: socket.socket) -> None:
        """Test buy endpoint with invalid card index."""
        save = "state-SHOP--shop.cards[0].set-JOKER.jkr"
        api(client, "load", {"path": str(get_fixture_path("buy", save))})
        response = api(client, "buy", {"card": 999})
        assert_error_response(
            response,
            expected_error_code="SCHEMA_INVALID_VALUE",
            expected_message_contains="Card index out of range. Index: 999, Available cards: 2",
        )

    def test_buy_insufficient_funds(self, client: socket.socket) -> None:
        """Test buy endpoint when player has insufficient funds."""
        save = "state-SHOP--money-0.jkr"
        api(client, "load", {"path": str(get_fixture_path("buy", save))})
        response = api(client, "buy", {"card": 0})
        assert_error_response(
            response,
            expected_error_code="SCHEMA_INVALID_VALUE",
            expected_message_contains="Card is not affordable. Cost: 5, Current money: 0",
        )

    def test_buy_joker_slots_full(self, client: socket.socket) -> None:
        """Test buy endpoint when player has the maximum number of consumables."""
        save = "state-SHOP--jokers.count-5--shop.cards[0].set-JOKER.jkr"
        api(client, "load", {"path": str(get_fixture_path("buy", save))})
        response = api(client, "buy", {"card": 0})
        assert_error_response(
            response,
            expected_error_code="SCHEMA_INVALID_VALUE",
            expected_message_contains="Cannot purchase joker card, joker slots are full. Current: 5, Limit: 5",
        )

    def test_buy_consumable_slots_full(self, client: socket.socket) -> None:
        """Test buy endpoint when player has the maximum number of consumables."""
        save = "state-SHOP--consumables.count-2--shop.cards[1].set-PLANET.jkr"
        api(client, "load", {"path": str(get_fixture_path("buy", save))})
        response = api(client, "buy", {"card": 1})
        assert_error_response(
            response,
            expected_error_code="SCHEMA_INVALID_VALUE",
            expected_message_contains="Cannot purchase consumable card, consumable slots are full. Current: 2, Limit: 2",
        )

    def test_buy_vouchers_slot_empty(self, client: socket.socket) -> None:
        """Test buy endpoint when player has the maximum number of vouchers."""
        save = "state-SHOP--voucher.count-0.jkr"
        api(client, "load", {"path": str(get_fixture_path("buy", save))})
        response = api(client, "buy", {"voucher": 0})
        assert_error_response(
            response,
            expected_error_code="SCHEMA_INVALID_VALUE",
            expected_message_contains="No vouchers to redeem. Defeat boss blind to restock",
        )

    @pytest.mark.skip(
        reason="Fixture not available yet. We need to be able to skip a pack."
    )
    def test_buy_packs_slot_empty(self, client: socket.socket) -> None:
        """Test buy endpoint when player has the maximum number of vouchers."""
        save = "state-SHOP--packs.count-0.jkr"
        api(client, "load", {"path": str(get_fixture_path("buy", save))})
        response = api(client, "buy", {"voucher": 0})
        assert_error_response(
            response,
            expected_error_code="SCHEMA_INVALID_VALUE",
            expected_message_contains="No vouchers to redeem. Defeat boss blind to restock",
        )

    def test_buy_joker_success(self, client: socket.socket) -> None:
        """Test buying a joker card from shop."""
        save = "state-SHOP--shop.cards[0].set-JOKER.jkr"
        api(client, "load", {"path": str(get_fixture_path("buy", save))})
        response = api(client, "buy", {"card": 0})
        assert response["jokers"]["cards"][0]["set"] == "JOKER"

    def test_buy_consumable_success(self, client: socket.socket) -> None:
        """Test buying a consumable card (Planet/Tarot/Spectral) from shop."""
        save = "state-SHOP--shop.cards[1].set-PLANET.jkr"
        api(client, "load", {"path": str(get_fixture_path("buy", save))})
        response = api(client, "buy", {"card": 1})
        assert response["consumables"]["cards"][0]["set"] == "PLANET"

    def test_buy_voucher_success(self, client: socket.socket) -> None:
        """Test buying a voucher from shop."""
        save = "state-SHOP--voucher.cards[0].set-VOUCHER.jkr"
        api(client, "load", {"path": str(get_fixture_path("buy", save))})
        response = api(client, "buy", {"voucher": 0})
        assert response["used_vouchers"] is not None
        assert len(response["used_vouchers"]) > 0

    def test_buy_packs_success(self, client: socket.socket) -> None:
        """Test buying a pack from shop."""
        save = "state-SHOP--packs.cards[0].label-Buffoon+Pack--packs.cards[1].label-Standard+Pack.jkr"
        api(client, "load", {"path": str(get_fixture_path("buy", save))})
        response = api(client, "buy", {"pack": 0})
        assert response["pack"] is not None
        assert len(response["pack"]["cards"]) > 0


class TestBuyEndpointValidation:
    """Test buy endpoint parameter validation."""

    def test_invalid_card_type_string(self, client: socket.socket) -> None:
        """Test that buy fails when card parameter is a string instead of integer."""
        save = "state-SHOP--shop.cards[0].set-JOKER.jkr"
        api(client, "load", {"path": str(get_fixture_path("buy", save))})
        response = api(client, "buy", {"card": "INVALID_STRING"})
        assert_error_response(
            response,
            expected_error_code="SCHEMA_INVALID_TYPE",
            expected_message_contains="Field 'card' must be an integer",
        )

    def test_invalid_voucher_type_string(self, client: socket.socket) -> None:
        """Test that buy fails when voucher parameter is a string instead of integer."""
        save = "state-SHOP--shop.cards[0].set-JOKER.jkr"
        api(client, "load", {"path": str(get_fixture_path("buy", save))})
        response = api(client, "buy", {"voucher": "INVALID_STRING"})
        assert_error_response(
            response,
            expected_error_code="SCHEMA_INVALID_TYPE",
            expected_message_contains="Field 'voucher' must be an integer",
        )

    def test_invalid_pack_type_string(self, client: socket.socket) -> None:
        """Test that buy fails when pack parameter is a string instead of integer."""
        save = "state-SHOP--shop.cards[0].set-JOKER.jkr"
        api(client, "load", {"path": str(get_fixture_path("buy", save))})
        response = api(client, "buy", {"pack": "INVALID_STRING"})
        assert_error_response(
            response,
            expected_error_code="SCHEMA_INVALID_TYPE",
            expected_message_contains="Field 'pack' must be an integer",
        )


class TestBuyEndpointStateRequirements:
    """Test buy endpoint state requirements."""

    def test_buy_from_BLIND_SELECT(self, client: socket.socket) -> None:
        """Test that buy fails when not in SHOP state."""
        save = "state-BLIND_SELECT.jkr"
        api(client, "load", {"path": str(get_fixture_path("buy", save))})
        response = api(client, "buy", {"card": 0})
        assert_error_response(
            response,
            expected_error_code="STATE_INVALID_STATE",
            expected_message_contains="Endpoint 'buy' requires one of these states:",
        )
