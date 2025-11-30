"""
Integration tests for BB_DISPATCHER request routing and validation.

Test classes are organized by validation tier:
- TestDispatcherProtocolValidation: TIER 1 - Protocol structure validation
- TestDispatcherSchemaValidation: TIER 2 - Schema/argument validation
- TestDispatcherStateValidation: TIER 3 - Game state validation
- TestDispatcherExecution: TIER 4 - Endpoint execution and error handling
- TestDispatcherEndpointRegistry: Endpoint registration and discovery
"""

import json
import socket

from tests.lua.conftest import BUFFER_SIZE


class TestDispatcherProtocolValidation:
    """Tests for TIER 1: Protocol Validation.

    Tests verify that dispatcher correctly validates:
    - Request has 'name' field (string)
    - Request has 'arguments' field (table)
    - Endpoint exists in registry
    """

    def test_missing_name_field(self, client: socket.socket) -> None:
        """Test that requests without 'name' field are rejected."""
        request = json.dumps({"arguments": {}}) + "\n"
        client.send(request.encode())

        response = client.recv(BUFFER_SIZE).decode().strip()
        data = json.loads(response)

        assert "error" in data
        assert "error_code" in data
        assert data["error_code"] == "BAD_REQUEST"
        assert "name" in data["error"].lower()

    def test_invalid_name_type(self, client: socket.socket) -> None:
        """Test that 'name' field must be a string."""
        request = json.dumps({"name": 123, "arguments": {}}) + "\n"
        client.send(request.encode())

        response = client.recv(BUFFER_SIZE).decode().strip()
        data = json.loads(response)

        assert "error" in data
        assert data["error_code"] == "BAD_REQUEST"

    def test_missing_arguments_field(self, client: socket.socket) -> None:
        """Test that requests without 'arguments' field are rejected."""
        request = json.dumps({"name": "health"}) + "\n"
        client.send(request.encode())

        response = client.recv(BUFFER_SIZE).decode().strip()
        data = json.loads(response)

        assert "error" in data
        assert data["error_code"] == "BAD_REQUEST"
        assert "arguments" in data["error"].lower()

    def test_unknown_endpoint(self, client: socket.socket) -> None:
        """Test that unknown endpoints are rejected."""
        request = json.dumps({"name": "nonexistent_endpoint", "arguments": {}}) + "\n"
        client.send(request.encode())

        response = client.recv(BUFFER_SIZE).decode().strip()
        data = json.loads(response)

        assert "error" in data
        assert data["error_code"] == "BAD_REQUEST"
        assert "nonexistent_endpoint" in data["error"]

    def test_valid_health_endpoint_request(self, client: socket.socket) -> None:
        """Test that valid requests to health endpoint succeed."""
        request = json.dumps({"name": "health", "arguments": {}}) + "\n"
        client.send(request.encode())

        response = client.recv(BUFFER_SIZE).decode().strip()
        data = json.loads(response)

        # Health endpoint should return success
        assert "status" in data
        assert data["status"] == "ok"


class TestDispatcherSchemaValidation:
    """Tests for TIER 2: Schema Validation.

    Tests verify that dispatcher correctly validates arguments against
    endpoint schemas using the Validator module.
    """

    def test_missing_required_field(self, client: socket.socket) -> None:
        """Test that missing required fields are rejected."""
        # test_endpoint requires 'required_string' and 'required_integer'
        request = (
            json.dumps(
                {
                    "name": "test_endpoint",
                    "arguments": {
                        "required_integer": 50,
                        "required_enum": "option_a",
                        # Missing 'required_string'
                    },
                }
            )
            + "\n"
        )
        client.send(request.encode())

        response = client.recv(BUFFER_SIZE).decode().strip()
        data = json.loads(response)

        assert "error" in data
        assert data["error_code"] == "BAD_REQUEST"
        assert "required_string" in data["error"].lower()

    def test_invalid_type_string_instead_of_integer(
        self, client: socket.socket
    ) -> None:
        """Test that type validation rejects wrong types."""
        request = (
            json.dumps(
                {
                    "name": "test_endpoint",
                    "arguments": {
                        "required_string": "valid_string",
                        "required_integer": "not_an_integer",  # Should be integer
                        "required_enum": "option_a",
                    },
                }
            )
            + "\n"
        )
        client.send(request.encode())

        response = client.recv(BUFFER_SIZE).decode().strip()
        data = json.loads(response)

        assert "error" in data
        assert data["error_code"] == "BAD_REQUEST"
        assert "required_integer" in data["error"].lower()

    def test_array_item_type_validation(self, client: socket.socket) -> None:
        """Test that array items are validated for correct type."""
        request = (
            json.dumps(
                {
                    "name": "test_endpoint",
                    "arguments": {
                        "required_string": "test",
                        "required_integer": 50,
                        "optional_array_integers": [
                            1,
                            2,
                            "not_integer",
                            4,
                        ],  # Should be integers
                    },
                }
            )
            + "\n"
        )
        client.send(request.encode())

        response = client.recv(BUFFER_SIZE).decode().strip()
        data = json.loads(response)

        assert "error" in data
        assert data["error_code"] == "BAD_REQUEST"

    def test_valid_request_with_all_fields(self, client: socket.socket) -> None:
        """Test that valid requests with multiple fields pass validation."""
        request = (
            json.dumps(
                {
                    "name": "test_endpoint",
                    "arguments": {
                        "required_string": "test",
                        "required_integer": 50,
                        "optional_string": "optional",
                        "optional_integer": 42,
                        "optional_array_integers": [1, 2, 3],
                    },
                }
            )
            + "\n"
        )
        client.send(request.encode())

        response = client.recv(BUFFER_SIZE).decode().strip()
        data = json.loads(response)

        # Should succeed and echo back
        assert "success" in data
        assert data["success"] is True
        assert "received_args" in data

    def test_valid_request_with_only_required_fields(
        self, client: socket.socket
    ) -> None:
        """Test that valid requests with only required fields pass validation."""
        request = (
            json.dumps(
                {
                    "name": "test_endpoint",
                    "arguments": {
                        "required_string": "test",
                        "required_integer": 1,
                        "required_enum": "option_c",
                    },
                }
            )
            + "\n"
        )
        client.send(request.encode())

        response = client.recv(BUFFER_SIZE).decode().strip()
        data = json.loads(response)

        assert "success" in data
        assert data["success"] is True


class TestDispatcherStateValidation:
    """Tests for TIER 3: Game State Validation.

    Tests verify that dispatcher enforces endpoint state requirements.
    Note: These tests may pass or fail depending on current game state.
    """

    def test_state_validation_enforcement(self, client: socket.socket) -> None:
        """Test that endpoints with requires_state are validated."""
        # test_state_endpoint requires SPLASH or MENU state
        request = json.dumps({"name": "test_state_endpoint", "arguments": {}}) + "\n"
        client.send(request.encode())

        response = client.recv(BUFFER_SIZE).decode().strip()
        data = json.loads(response)

        # Response depends on current game state
        # Either succeeds if in correct state, or fails with STATE_INVALID_STATE
        if "error" in data:
            assert data["error_code"] == "INVALID_STATE"
            assert "requires" in data["error"].lower()
        else:
            assert "success" in data
            assert data["state_validated"] is True


class TestDispatcherExecution:
    """Tests for TIER 4: Endpoint Execution and Error Handling.

    Tests verify that dispatcher correctly executes endpoints and
    handles runtime errors with appropriate error codes.
    """

    def test_successful_endpoint_execution(self, client: socket.socket) -> None:
        """Test that endpoints execute successfully with valid input."""
        request = (
            json.dumps(
                {
                    "name": "test_endpoint",
                    "arguments": {
                        "required_string": "test",
                        "required_integer": 42,
                        "required_enum": "option_a",
                    },
                }
            )
            + "\n"
        )
        client.send(request.encode())

        response = client.recv(BUFFER_SIZE).decode().strip()
        data = json.loads(response)

        assert "success" in data
        assert data["success"] is True
        assert "received_args" in data
        assert data["received_args"]["required_integer"] == 42

    def test_execution_error_handling(self, client: socket.socket) -> None:
        """Test that runtime errors are caught and returned properly."""
        request = (
            json.dumps(
                {
                    "name": "test_error_endpoint",
                    "arguments": {
                        "error_type": "throw_error",
                    },
                }
            )
            + "\n"
        )
        client.send(request.encode())

        response = client.recv(BUFFER_SIZE).decode().strip()
        data = json.loads(response)

        assert "error" in data
        assert data["error_code"] == "INTERNAL_ERROR"
        assert "Intentional test error" in data["error"]

    def test_execution_error_no_categorization(self, client: socket.socket) -> None:
        """Test that all execution errors use EXEC_INTERNAL_ERROR."""
        request = (
            json.dumps(
                {
                    "name": "test_error_endpoint",
                    "arguments": {
                        "error_type": "throw_error",
                    },
                }
            )
            + "\n"
        )
        client.send(request.encode())

        response = client.recv(BUFFER_SIZE).decode().strip()
        data = json.loads(response)

        # Should always be EXEC_INTERNAL_ERROR (no categorization)
        assert data["error_code"] == "INTERNAL_ERROR"

    def test_execution_success_when_no_error(self, client: socket.socket) -> None:
        """Test that endpoints can execute successfully."""
        request = (
            json.dumps(
                {
                    "name": "test_error_endpoint",
                    "arguments": {
                        "error_type": "success",
                    },
                }
            )
            + "\n"
        )
        client.send(request.encode())

        response = client.recv(BUFFER_SIZE).decode().strip()
        data = json.loads(response)

        assert "success" in data
        assert data["success"] is True


class TestDispatcherEndpointRegistry:
    """Tests for endpoint registration and discovery."""

    def test_health_endpoint_is_registered(self, client: socket.socket) -> None:
        """Test that the health endpoint is properly registered."""
        request = json.dumps({"name": "health", "arguments": {}}) + "\n"
        client.send(request.encode())

        response = client.recv(BUFFER_SIZE).decode().strip()
        data = json.loads(response)

        assert "status" in data
        assert data["status"] == "ok"

    def test_multiple_sequential_requests_to_same_endpoint(
        self, client: socket.socket
    ) -> None:
        """Test that multiple requests to the same endpoint work."""
        for i in range(3):
            request = json.dumps({"name": "health", "arguments": {}}) + "\n"
            client.send(request.encode())

            response = client.recv(BUFFER_SIZE).decode().strip()
            data = json.loads(response)

            assert "status" in data
            assert data["status"] == "ok"

    def test_requests_to_different_endpoints(self, client: socket.socket) -> None:
        """Test that requests can be routed to different endpoints."""
        # Request to health endpoint
        request1 = json.dumps({"name": "health", "arguments": {}}) + "\n"
        client.send(request1.encode())
        response1 = client.recv(BUFFER_SIZE).decode().strip()
        data1 = json.loads(response1)
        assert "status" in data1

        # Request to test_endpoint
        request2 = (
            json.dumps(
                {
                    "name": "test_endpoint",
                    "arguments": {
                        "required_string": "test",
                        "required_integer": 25,
                        "required_enum": "option_a",
                    },
                }
            )
            + "\n"
        )
        client.send(request2.encode())
        response2 = client.recv(BUFFER_SIZE).decode().strip()
        data2 = json.loads(response2)
        assert "success" in data2
