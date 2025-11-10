# tests/lua/core/test_validator.py
# Comprehensive tests for src/lua/core/validator.lua
#
# Tests validation scenarios through the dispatcher using the test_validation endpoint:
# - Type validation (string, integer, array)
# - Required field validation
# - Array item type validation (integer arrays only)
# - Error codes and messages

import socket

from tests.lua.conftest import (
    assert_error_response,
    assert_success_response,
    receive_response,
    send_request,
)

# ============================================================================
# Test: Type Validation
# ============================================================================


class TestTypeValidation:
    """Test type validation for all supported types."""

    def test_valid_string_type(self, client: socket.socket) -> None:
        """Test that valid string type passes validation."""
        send_request(
            client,
            "test_validation",
            {
                "required_field": "test",
                "string_field": "hello",
            },
        )
        response = receive_response(client)
        assert_success_response(response)

    def test_invalid_string_type(self, client: socket.socket) -> None:
        """Test that invalid string type fails validation."""
        send_request(
            client,
            "test_validation",
            {
                "required_field": "test",
                "string_field": 123,  # Should be string
            },
        )
        response = receive_response(client)
        assert_error_response(
            response,
            expected_error_code="SCHEMA_INVALID_TYPE",
            expected_message_contains="string_field",
        )

    def test_valid_integer_type(self, client: socket.socket) -> None:
        """Test that valid integer type passes validation."""
        send_request(
            client,
            "test_validation",
            {
                "required_field": "test",
                "integer_field": 42,
            },
        )
        response = receive_response(client)
        assert_success_response(response)

    def test_invalid_integer_type_float(self, client: socket.socket) -> None:
        """Test that float fails integer validation."""
        send_request(
            client,
            "test_validation",
            {
                "required_field": "test",
                "integer_field": 42.5,  # Should be integer
            },
        )
        response = receive_response(client)
        assert_error_response(
            response,
            expected_error_code="SCHEMA_INVALID_TYPE",
            expected_message_contains="integer_field",
        )

    def test_invalid_integer_type_string(self, client: socket.socket) -> None:
        """Test that string fails integer validation."""
        send_request(
            client,
            "test_validation",
            {
                "required_field": "test",
                "integer_field": "42",
            },
        )
        response = receive_response(client)
        assert_error_response(
            response,
            expected_error_code="SCHEMA_INVALID_TYPE",
            expected_message_contains="integer_field",
        )

    def test_valid_array_type(self, client: socket.socket) -> None:
        """Test that valid array type passes validation."""
        send_request(
            client,
            "test_validation",
            {
                "required_field": "test",
                "array_field": [1, 2, 3],
            },
        )
        response = receive_response(client)
        assert_success_response(response)

    def test_invalid_array_type_not_sequential(self, client: socket.socket) -> None:
        """Test that non-sequential table fails array validation."""
        send_request(
            client,
            "test_validation",
            {
                "required_field": "test",
                "array_field": {"key": "value"},  # Not an array
            },
        )
        response = receive_response(client)
        assert_error_response(
            response,
            expected_error_code="SCHEMA_INVALID_TYPE",
            expected_message_contains="array_field",
        )

    def test_invalid_array_type_string(self, client: socket.socket) -> None:
        """Test that string fails array validation."""
        send_request(
            client,
            "test_validation",
            {
                "required_field": "test",
                "array_field": "not an array",
            },
        )
        response = receive_response(client)
        assert_error_response(
            response,
            expected_error_code="SCHEMA_INVALID_TYPE",
            expected_message_contains="array_field",
        )


# ============================================================================
# Test: Required Field Validation
# ============================================================================


class TestRequiredFields:
    """Test required field validation."""

    def test_required_field_present(self, client: socket.socket) -> None:
        """Test that request with required field passes."""
        send_request(
            client,
            "test_validation",
            {"required_field": "present"},
        )
        response = receive_response(client)
        assert_success_response(response)

    def test_required_field_missing(self, client: socket.socket) -> None:
        """Test that request without required field fails."""
        send_request(
            client,
            "test_validation",
            {},  # Missing required_field
        )
        response = receive_response(client)
        assert_error_response(
            response,
            expected_error_code="SCHEMA_MISSING_REQUIRED",
            expected_message_contains="required_field",
        )

    def test_optional_field_missing(self, client: socket.socket) -> None:
        """Test that missing optional fields are allowed."""
        send_request(
            client,
            "test_validation",
            {
                "required_field": "present",
                # All other fields are optional
            },
        )
        response = receive_response(client)
        assert_success_response(response)


# ============================================================================
# Test: Array Item Type Validation
# ============================================================================


class TestArrayItemTypes:
    """Test array item type validation."""

    def test_array_of_integers_valid(self, client: socket.socket) -> None:
        """Test that array of integers passes."""
        send_request(
            client,
            "test_validation",
            {
                "required_field": "test",
                "array_of_integers": [1, 2, 3],
            },
        )
        response = receive_response(client)
        assert_success_response(response)

    def test_array_of_integers_invalid_float(self, client: socket.socket) -> None:
        """Test that array with float items fails integer validation."""
        send_request(
            client,
            "test_validation",
            {
                "required_field": "test",
                "array_of_integers": [1, 2.5, 3],
            },
        )
        response = receive_response(client)
        assert_error_response(
            response,
            expected_error_code="SCHEMA_INVALID_ARRAY_ITEMS",
            expected_message_contains="array_of_integers",
        )

    def test_array_of_integers_invalid_string(self, client: socket.socket) -> None:
        """Test that array with string items fails integer validation."""
        send_request(
            client,
            "test_validation",
            {
                "required_field": "test",
                "array_of_integers": [1, "2", 3],
            },
        )
        response = receive_response(client)
        assert_error_response(
            response,
            expected_error_code="SCHEMA_INVALID_ARRAY_ITEMS",
            expected_message_contains="array_of_integers",
        )


# ============================================================================
# Test: Fail-Fast Behavior
# ============================================================================


class TestFailFastBehavior:
    """Test that validator fails fast on first error."""

    def test_multiple_errors_returns_first(self, client: socket.socket) -> None:
        """Test that only the first error is returned when multiple errors exist."""
        send_request(
            client,
            "test_validation",
            {
                # Missing required_field (one error)
                "string_field": 123,  # Type error (another error)
                "integer_field": "not an integer",  # Type error (another error)
            },
        )
        response = receive_response(client)
        # Should get ONE error (fail-fast), not all errors
        # The specific error depends on Lua table iteration order
        assert_error_response(response)
        # Verify it's one of the expected error codes
        assert response["error_code"] in [
            "SCHEMA_MISSING_REQUIRED",
            "SCHEMA_INVALID_TYPE",
        ]


# ============================================================================
# Test: Edge Cases
# ============================================================================


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_empty_arguments_with_only_required_field(
        self, client: socket.socket
    ) -> None:
        """Test that arguments with only required field passes."""
        send_request(
            client,
            "test_validation",
            {"required_field": "only this"},
        )
        response = receive_response(client)
        assert_success_response(response)

    def test_all_fields_provided(self, client: socket.socket) -> None:
        """Test request with multiple valid fields."""
        send_request(
            client,
            "test_validation",
            {
                "required_field": "test",
                "string_field": "hello",
                "integer_field": 42,
                "array_field": [1, 2, 3],
                "array_of_integers": [4, 5, 6],
            },
        )
        response = receive_response(client)
        assert_success_response(response)

    def test_empty_array_when_allowed(self, client: socket.socket) -> None:
        """Test that empty array passes when no min constraint."""
        send_request(
            client,
            "test_validation",
            {
                "required_field": "test",
                "array_field": [],
            },
        )
        response = receive_response(client)
        assert_success_response(response)

    def test_empty_string_when_allowed(self, client: socket.socket) -> None:
        """Test that empty string passes when no min constraint."""
        send_request(
            client,
            "test_validation",
            {
                "required_field": "",  # Empty but present
            },
        )
        response = receive_response(client)
        assert_success_response(response)
