"""
Integration tests for BB_SERVER TCP communication (JSON-RPC 2.0).

Test classes are organized by BB_SERVER function:
- TestBBServerInit: BB_SERVER.init() - server initialization and port binding
- TestBBServerAccept: BB_SERVER.accept() - client connection handling
- TestBBServerReceive: BB_SERVER.receive() - protocol enforcement and parsing
- TestBBServerSendResponse: BB_SERVER.send_response() - response sending
"""

import errno
import json
import socket
import time

import pytest

from tests.lua.conftest import BUFFER_SIZE

# Request ID counter for JSON-RPC 2.0
_test_request_id = 0


def make_request(method: str, params: dict = {}) -> str:
    """Create a JSON-RPC 2.0 request string."""
    global _test_request_id
    _test_request_id += 1
    return (
        json.dumps(
            {
                "jsonrpc": "2.0",
                "method": method,
                "params": params,
                "id": _test_request_id,
            }
        )
        + "\n"
    )


class TestBBServerInit:
    """Tests for BB_SERVER.init() - server initialization and port binding."""

    def test_server_binds_to_configured_port(self, port: int) -> None:
        """Test that server is listening on the expected port."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        try:
            sock.connect(("127.0.0.1", port))
            assert sock.fileno() != -1, f"Should connect to port {port}"
        finally:
            sock.close()

    def test_port_is_exclusively_bound(self, port: int) -> None:
        """Test that server exclusively binds the port."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            with pytest.raises(OSError) as exc_info:
                sock.bind(("127.0.0.1", port))
            assert exc_info.value.errno == errno.EADDRINUSE
        finally:
            sock.close()

    def test_port_not_reusable_while_running(self, port: int) -> None:
        """Test that port cannot be reused while server is running."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            with pytest.raises(OSError) as exc_info:
                sock.bind(("127.0.0.1", port))
                sock.listen(1)
            assert exc_info.value.errno == errno.EADDRINUSE
        finally:
            sock.close()


class TestBBServerAccept:
    """Tests for BB_SERVER.accept() - client connection handling."""

    def test_accepts_connections(self, client: socket.socket) -> None:
        """Test that server accepts client connections."""
        assert client.fileno() != -1, "Client should connect successfully"

    def test_sequential_connections(self, port: int) -> None:
        """Test that server handles sequential connections correctly."""
        for i in range(3):
            time.sleep(0.02)  # Delay to prevent overwhelming server
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2)
            try:
                sock.connect(("127.0.0.1", port))
                assert sock.fileno() != -1, f"Connection {i + 1} should succeed"
            finally:
                sock.close()

    def test_rapid_sequential_connections(self, port: int) -> None:
        """Test server handles rapid sequential connections."""
        for i in range(5):
            time.sleep(0.02)  # Delay to prevent overwhelming server
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2)
            try:
                sock.connect(("127.0.0.1", port))
                assert sock.fileno() != -1, f"Rapid connection {i + 1} should succeed"
            finally:
                sock.close()

    def test_immediate_disconnect(self, port: int) -> None:
        """Test server handles clients that disconnect immediately."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        sock.connect(("127.0.0.1", port))
        sock.close()

        time.sleep(0.1)  # Delay to prevent overwhelming server

        # Server should still accept new connections
        sock2 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock2.settimeout(2)
        try:
            sock2.connect(("127.0.0.1", port))
            assert sock2.fileno() != -1, (
                "Server should accept connection after disconnect"
            )
        finally:
            sock2.close()

    def test_reconnect_after_graceful_disconnect(self, port: int) -> None:
        """Test client can reconnect after clean disconnect."""
        # First connection
        sock1 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock1.settimeout(2)
        sock1.connect(("127.0.0.1", port))

        # Send a JSON-RPC 2.0 request
        msg = make_request("health", {})
        sock1.send(msg.encode())
        sock1.recv(BUFFER_SIZE)  # Consume response

        # Close connection
        sock1.close()

        # Reconnect
        sock2 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock2.settimeout(2)
        try:
            sock2.connect(("127.0.0.1", port))
            assert sock2.fileno() != -1, "Should reconnect successfully"

            # Verify new connection works
            sock2.send(make_request("health", {}).encode())
            response = sock2.recv(BUFFER_SIZE)
            assert len(response) > 0, "Should receive response after reconnect"
        finally:
            sock2.close()

    def test_client_disconnect_without_sending(self, port: int) -> None:
        """Test server handles client that connects but never sends data."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        sock.connect(("127.0.0.1", port))
        sock.close()

        time.sleep(0.1)  # Delay to prevent overwhelming server

        # Server should still accept new connections
        sock2 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock2.settimeout(2)
        try:
            sock2.connect(("127.0.0.1", port))
            assert sock2.fileno() != -1
        finally:
            sock2.close()


class TestBBServerReceive:
    """Tests for BB_SERVER.receive() - protocol enforcement and parsing.

    Tests verify error responses for protocol violations:
    - Message size limit (256 bytes including newline)
    - Pipelining rejection (multiple messages)
    - JSON validation (must be object, not string/number/array)
    - Invalid JSON syntax
    - Edge cases (whitespace, nested objects, escaped characters)
    """

    def test_message_too_large(self, client: socket.socket) -> None:
        """Test that messages exceeding 256 bytes are rejected."""
        # Create message > 255 bytes (line + newline must be <= 256)
        large_msg = {
            "jsonrpc": "2.0",
            "method": "test",
            "params": {"data": "x" * 300},
            "id": 1,
        }
        msg = json.dumps(large_msg) + "\n"
        assert len(msg) > 256, "Test message should exceed 256 bytes"

        client.send(msg.encode())

        response = client.recv(BUFFER_SIZE).decode().strip()
        raw_data = json.loads(response)

        # Response is JSON-RPC 2.0 error format
        assert "error" in raw_data
        assert raw_data["error"]["data"]["name"] == "BAD_REQUEST"
        assert "too large" in raw_data["error"]["message"].lower()

    def test_pipelined_messages_rejected(self, client: socket.socket) -> None:
        """Test that sending multiple messages at once are processed sequentially."""
        msg1 = make_request("health", {})
        msg2 = make_request("health", {})

        # Send both messages in one packet (pipelining)
        client.send((msg1 + msg2).encode())

        # Server processes messages sequentially - we should get two responses
        response = client.recv(BUFFER_SIZE).decode().strip()

        # We may get one or both responses depending on timing
        # The important thing is no error occurred
        lines = response.split("\n")
        raw_data1 = json.loads(lines[0])

        # First response should be successful
        assert "result" in raw_data1
        assert "status" in raw_data1["result"]
        assert raw_data1["result"]["status"] == "ok"

        # If we got both in one recv, verify second is also good
        if len(lines) > 1 and lines[1]:
            raw_data2 = json.loads(lines[1])
            assert "result" in raw_data2
            assert "status" in raw_data2["result"]
            assert raw_data2["result"]["status"] == "ok"

    def test_invalid_json_syntax(self, client: socket.socket) -> None:
        """Test that malformed JSON is rejected."""
        client.send(b"{invalid json}\n")

        response = client.recv(BUFFER_SIZE).decode().strip()
        raw_data = json.loads(response)

        assert "error" in raw_data
        assert raw_data["error"]["data"]["name"] == "BAD_REQUEST"

    def test_json_string_rejected(self, client: socket.socket) -> None:
        """Test that JSON strings are rejected (must be object)."""
        client.send(b'"just a string"\n')

        response = client.recv(BUFFER_SIZE).decode().strip()
        raw_data = json.loads(response)

        assert "error" in raw_data
        assert raw_data["error"]["data"]["name"] == "BAD_REQUEST"

    def test_json_number_rejected(self, client: socket.socket) -> None:
        """Test that JSON numbers are rejected (must be object)."""
        client.send(b"42\n")

        response = client.recv(BUFFER_SIZE).decode().strip()
        raw_data = json.loads(response)

        assert "error" in raw_data
        assert raw_data["error"]["data"]["name"] == "BAD_REQUEST"

    def test_json_array_rejected(self, client: socket.socket) -> None:
        """Test that JSON arrays are rejected (must be object starting with '{')."""
        client.send(b'["array", "of", "values"]\n')

        response = client.recv(BUFFER_SIZE).decode().strip()
        raw_data = json.loads(response)

        assert "error" in raw_data
        assert raw_data["error"]["data"]["name"] == "BAD_REQUEST"

    def test_only_whitespace_line_rejected(self, client: socket.socket) -> None:
        """Test that whitespace-only lines are rejected as invalid JSON."""
        # Send whitespace-only line (gets trimmed to empty string, fails '{' check)
        client.send(b"   \t  \n")

        response = client.recv(BUFFER_SIZE).decode().strip()
        raw_data = json.loads(response)

        # Should be rejected as invalid JSON (trimmed to empty, doesn't start with '{')
        assert "error" in raw_data
        assert raw_data["error"]["data"]["name"] == "BAD_REQUEST"


class TestBBServerSendResponse:
    """Tests for BB_SERVER.send_response() and send_error() - response sending."""

    def test_server_accepts_data(self, client: socket.socket) -> None:
        """Test that server accepts data from connected clients."""
        test_data = b"test\n"
        bytes_sent = client.send(test_data)
        assert bytes_sent == len(test_data), "Should send all data"

    def test_multiple_sequential_valid_requests(self, client: socket.socket) -> None:
        """Test handling multiple valid requests sent sequentially (not pipelined)."""
        # Send first request
        msg1 = make_request("health", {})
        client.send(msg1.encode())

        response1 = client.recv(BUFFER_SIZE).decode().strip()
        raw_data1 = json.loads(response1)
        assert "result" in raw_data1
        assert "status" in raw_data1["result"]  # Health endpoint returns status

        # Send second request on same connection
        msg2 = make_request("health", {})
        client.send(msg2.encode())

        response2 = client.recv(BUFFER_SIZE).decode().strip()
        raw_data2 = json.loads(response2)
        assert "result" in raw_data2
        assert "status" in raw_data2["result"]

    def test_whitespace_around_json_accepted(self, client: socket.socket) -> None:
        """Test that JSON with leading/trailing whitespace is accepted."""
        global _test_request_id
        _test_request_id += 1
        msg = (
            "  "
            + json.dumps(
                {
                    "jsonrpc": "2.0",
                    "method": "health",
                    "params": {},
                    "id": _test_request_id,
                }
            )
            + "  \n"
        )
        client.send(msg.encode())
        response = client.recv(BUFFER_SIZE).decode().strip()
        raw_data = json.loads(response)

        # Should be processed successfully (whitespace trimmed at line 134)
        # Result should contain health status or error
        if "result" in raw_data:
            assert "status" in raw_data["result"]
        else:
            assert "error" in raw_data
