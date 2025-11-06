"""Tests for BalatroBot protocol handling.

This module tests the core TCP communication layer between the Python bot and
the Lua game mod, ensuring proper message protocol, and error response
validation.

Protocol Payload Tests:
- test_empty_payload: Verify error response for empty messages (E001)
- test_missing_name: Test error when API call name is missing (E002)
- test_unknown_name: Test error for unknown API call names (E004)
- test_missing_arguments: Test error when arguments field is missing (E003)
- test_malformed_arguments: Test error for malformed JSON arguments (E001)
- test_invalid_arguments: Test error for invalid argument types (E005)
"""

import json
import socket

from .conftest import BUFFER_SIZE, api


def test_empty_payload(client: socket.socket):
    """Test sending an empty payload."""
    client.send(b"\n")
    response = client.recv(BUFFER_SIZE)
    gamestate = json.loads(response.decode().strip())
    assert gamestate["error_code"] == "E001"  # Invalid JSON


def test_missing_name(client: socket.socket):
    """Test message without name field returns error response."""
    payload = {"arguments": {}}
    client.send(json.dumps(payload).encode() + b"\n")
    response = client.recv(BUFFER_SIZE)
    gamestate = json.loads(response.decode().strip())
    assert gamestate["error_code"] == "E002"  # MISSING NAME


def test_unknown_name(client: socket.socket):
    """Test message with unknown name field returns error response."""
    gamestate = api(client, "unknown")
    assert gamestate["error_code"] == "E004"  # UNKNOWN NAME


def test_missing_arguments(client: socket.socket):
    """Test message without name field returns error response."""
    payload = {"name": "get_game_state"}
    client.send(json.dumps(payload).encode() + b"\n")
    response = client.recv(BUFFER_SIZE)
    gamestate = json.loads(response.decode().strip())
    assert gamestate["error_code"] == "E003"  # MISSING ARGUMENTS


def test_malformed_arguments(client: socket.socket):
    """Test message with malformed arguments returns error response."""
    payload = '{"name": "start_run", "arguments": {this is not valid JSON} }'
    client.send(payload.encode() + b"\n")
    response = client.recv(BUFFER_SIZE)
    gamestate = json.loads(response.decode().strip())
    assert gamestate["error_code"] == "E001"  # Invalid JSON


def test_invalid_arguments(client: socket.socket):
    """Test that invalid JSON messages return error responses."""
    gamestate = api(client, "start_run", arguments="this is not a dict")  # type: ignore
    assert gamestate["error_code"] == "E005"  # Invalid Arguments
