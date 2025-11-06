"""Tests for BalatroBot TCP API connection.

This module tests the core TCP communication layer between the Python bot
and the Lua game mod, ensuring proper connection handling.

Connection Tests:
- test_basic_connection: Verify TCP connection and basic game state retrieval
- test_rapid_messages: Test multiple rapid API calls without connection drops
- test_connection_wrong_port: Ensure connection refusal on wrong port
"""

import json
import socket

import pytest

from .conftest import BUFFER_SIZE, api


def test_basic_connection(client: socket.socket):
    """Test basic TCP connection and response."""
    gamestate = api(client, "get_game_state")
    assert isinstance(gamestate, dict)


def test_rapid_messages(client: socket.socket):
    """Test rapid succession of get_game_state messages."""
    NUM_MESSAGES = 5
    gamestates = [api(client, "get_game_state") for _ in range(NUM_MESSAGES)]
    assert all(isinstance(gamestate, dict) for gamestate in gamestates)
    assert len(gamestates) == NUM_MESSAGES


def test_connection_wrong_port():
    """Test behavior when wrong port is specified."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client:
        client.settimeout(0.2)
        client.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, BUFFER_SIZE)
        with pytest.raises(ConnectionRefusedError):
            client.connect(("127.0.0.1", 12345))
