"""Tests for src/lua/endpoints/save.lua"""

import socket
from pathlib import Path

from tests.lua.conftest import (
    api,
    assert_error_response,
    assert_success_response,
    load_fixture,
)


class TestSaveEndpoint:
    """Test basic save endpoint functionality."""

    def test_save_from_BLIND_SELECT(
        self, client: socket.socket, tmp_path: Path
    ) -> None:
        """Test that save succeeds from BLIND_SELECT state."""
        gamestate = load_fixture(client, "save", "state-BLIND_SELECT")
        assert gamestate["state"] == "BLIND_SELECT"
        temp_file = tmp_path / "save"
        response = api(client, "save", {"path": str(temp_file)})
        assert_success_response(response)
        assert response["path"] == str(temp_file)
        assert temp_file.exists()
        assert temp_file.stat().st_size > 0

    def test_save_creates_valid_file(
        self, client: socket.socket, tmp_path: Path
    ) -> None:
        """Test that saved file can be loaded back successfully."""
        gamestate = load_fixture(client, "save", "state-BLIND_SELECT")
        assert gamestate["state"] == "BLIND_SELECT"
        temp_file = tmp_path / "save"
        save_response = api(client, "save", {"path": str(temp_file)})
        assert_success_response(save_response)
        load_response = api(client, "load", {"path": str(temp_file)})
        assert_success_response(load_response)


class TestSaveValidation:
    """Test save endpoint parameter validation."""

    def test_missing_path_parameter(self, client: socket.socket) -> None:
        """Test that save fails when path parameter is missing."""
        response = api(client, "save", {})
        assert_error_response(
            response,
            expected_error_code="SCHEMA_MISSING_REQUIRED",
            expected_message_contains="Missing required field 'path'",
        )

    def test_invalid_path_type(self, client: socket.socket) -> None:
        """Test that save fails when path is not a string."""
        response = api(client, "save", {"path": 123})
        assert_error_response(
            response,
            expected_error_code="SCHEMA_INVALID_TYPE",
            expected_message_contains="Field 'path' must be of type string",
        )


class TestSaveStateRequirements:
    """Test save endpoint state requirements."""

    def test_save_from_MENU(self, client: socket.socket, tmp_path: Path) -> None:
        """Test that save fails when not in an active run."""
        api(client, "menu", {})
        temp_file = tmp_path / "save"
        response = api(client, "save", {"path": str(temp_file)})
        assert_error_response(
            response,
            expected_error_code="STATE_INVALID_STATE",
            expected_message_contains="requires one of these states",
        )
        assert not temp_file.exists()
