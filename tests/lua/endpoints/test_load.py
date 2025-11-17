"""Tests for src/lua/endpoints/load.lua"""

import socket
from pathlib import Path

from tests.lua.conftest import (
    api,
    assert_error_response,
    assert_success_response,
    get_fixture_path,
)


class TestLoadEndpoint:
    """Test basic load endpoint functionality."""

    def test_load_from_fixture(self, client: socket.socket) -> None:
        """Test that load succeeds with a valid fixture file."""
        fixture_path = get_fixture_path("load", "state-BLIND_SELECT.jkr")

        response = api(client, "load", {"path": str(fixture_path)})

        assert_success_response(response)
        assert response["path"] == str(fixture_path)

    def test_load_save_roundtrip(self, client: socket.socket, tmp_path: Path) -> None:
        """Test that a loaded fixture can be saved and loaded again."""
        # Load fixture
        fixture_path = get_fixture_path("load", "state-BLIND_SELECT.jkr")
        load_response = api(client, "load", {"path": str(fixture_path)})
        assert_success_response(load_response)

        # Save to temp path
        temp_file = tmp_path / "save.jkr"
        save_response = api(client, "save", {"path": str(temp_file)})
        assert_success_response(save_response)
        assert temp_file.exists()

        # Load the saved file back
        load_again_response = api(client, "load", {"path": str(temp_file)})
        assert_success_response(load_again_response)


class TestLoadValidation:
    """Test load endpoint parameter validation."""

    def test_missing_path_parameter(self, client: socket.socket) -> None:
        """Test that load fails when path parameter is missing."""
        response = api(client, "load", {})

        assert_error_response(
            response,
            expected_error_code="SCHEMA_MISSING_REQUIRED",
            expected_message_contains="Missing required field 'path'",
        )

    def test_invalid_path_type(self, client: socket.socket) -> None:
        """Test that load fails when path is not a string."""
        response = api(client, "load", {"path": 123})

        assert_error_response(
            response,
            expected_error_code="SCHEMA_INVALID_TYPE",
            expected_message_contains="Field 'path' must be of type string",
        )
