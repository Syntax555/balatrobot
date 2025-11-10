# tests/lua/endpoints/test_health.py
# Tests for src/lua/endpoints/health.lua
#
# Tests the health check endpoint:
# - Basic health check functionality
# - Response structure and fields

import socket

import pytest

from tests.lua.conftest import assert_health_response, receive_response, send_request

# ============================================================================
# Test: Health Endpoint Basics
# ============================================================================


class TestHealthEndpointBasics:
    """Test basic health endpoint functionality."""

    def test_health_check_succeeds(self, client: socket.socket) -> None:
        """Test that health check returns status ok."""
        send_request(client, "health", {})
        response = receive_response(client)
        assert_health_response(response)

    def test_health_check_with_empty_arguments(self, client: socket.socket) -> None:
        """Test that health check works with empty arguments."""
        send_request(client, "health", {})
        response = receive_response(client)
        assert_health_response(response)

    def test_health_check_ignores_extra_arguments(self, client: socket.socket) -> None:
        """Test that health check ignores extra arguments."""
        send_request(
            client,
            "health",
            {
                "extra_field": "ignored",
                "another_field": 123,
            },
        )
        response = receive_response(client)
        assert_health_response(response)


# ============================================================================
# Test: Health Response Structure
# ============================================================================


class TestHealthResponseStructure:
    """Test health endpoint response structure."""

    def test_response_has_status_field(self, client: socket.socket) -> None:
        """Test that response contains status field."""
        send_request(client, "health", {})
        response = receive_response(client)
        assert "status" in response

    def test_status_field_is_ok(self, client: socket.socket) -> None:
        """Test that status field is 'ok'."""
        send_request(client, "health", {})
        response = receive_response(client)
        assert response["status"] == "ok"

    def test_response_only_has_status_field(self, client: socket.socket) -> None:
        """Test that response only contains the status field."""
        send_request(client, "health", {})
        response = receive_response(client)
        assert list(response.keys()) == ["status"]


# ============================================================================
# Test: Multiple Health Checks
# ============================================================================


class TestMultipleHealthChecks:
    """Test multiple sequential health checks."""

    @pytest.mark.parametrize("iteration", range(10))
    def test_multiple_health_checks_succeed(
        self, client: socket.socket, iteration: int
    ) -> None:
        """Test that multiple health checks all succeed."""
        send_request(client, "health", {})
        response = receive_response(client)
        assert_health_response(response)

    def test_health_check_responses_consistent(self, client: socket.socket) -> None:
        """Test that health check responses are consistent."""
        send_request(client, "health", {})
        response1 = receive_response(client)

        send_request(client, "health", {})
        response2 = receive_response(client)

        # Responses should be identical
        assert response1 == response2
        assert response1["status"] == "ok"
        assert response2["status"] == "ok"


# ============================================================================
# Test: Health Check Edge Cases
# ============================================================================


class TestHealthCheckEdgeCases:
    """Test edge cases for health endpoint."""

    def test_health_check_fast_response(self, client: socket.socket) -> None:
        """Test that health check responds quickly (synchronous)."""
        from time import time

        start = time()
        send_request(client, "health", {})
        response = receive_response(client, timeout=1.0)
        elapsed = time() - start

        # Should respond in less than 1 second (it's synchronous)
        assert elapsed < 1.0
        assert_health_response(response)

    @pytest.mark.parametrize("iteration", range(5))
    def test_health_check_no_side_effects(
        self,
        client: socket.socket,
        iteration: int,
    ) -> None:
        """Test that health check has no side effects."""
        send_request(client, "health", {})
        response = receive_response(client)
        assert_health_response(response)


# ============================================================================
# Test: Health Check Integration
# ============================================================================


class TestHealthCheckIntegration:
    """Test health check integration with other endpoints."""

    def test_health_check_after_validation_endpoint(
        self, client: socket.socket
    ) -> None:
        """Test health check after using validation endpoint."""
        # Use validation endpoint
        send_request(client, "test_validation", {"required_field": "test"})
        validation_response = receive_response(client)
        assert validation_response["success"] is True

        # Then health check
        send_request(client, "health", {})
        health_response = receive_response(client)
        assert_health_response(health_response)

    @pytest.mark.parametrize("iteration", range(5))
    def test_alternating_health_and_validation(
        self, client: socket.socket, iteration: int
    ) -> None:
        """Test alternating between health and validation requests."""
        # Health check
        send_request(client, "health", {})
        health_response = receive_response(client)
        assert_health_response(health_response)

        # Validation endpoint
        send_request(client, "test_validation", {"required_field": "test"})
        validation_response = receive_response(client)
        assert validation_response["success"] is True
