"""Lua API test-specific configuration and fixtures."""

import json
import socket
from typing import Any, Generator

import pytest

BUFFER_SIZE: int = 65536  # 64KB buffer for TCP messages


@pytest.fixture
def client(
    host: str = "127.0.0.1",
    port: int = 12346,
    timeout: float = 60,
    buffer_size: int = BUFFER_SIZE,
) -> Generator[socket.socket, None, None]:
    """Create a TCP socket client connected to Balatro game instance.

    Args:
        host: The hostname or IP address of the Balatro game server (default: "127.0.0.1").
        port: The port number the Balatro game server is listening on (default: 12346).
        timeout: Socket timeout in seconds for connection and operations (default: 60).
        buffer_size: Size of the socket receive buffer (default: 65536, i.e. 64KB).

    Yields:
        A connected TCP socket for communicating with the game.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, buffer_size)
        sock.connect((host, port))
        yield sock


def api(
    client: socket.socket,
    name: str,
    arguments: dict = {},
) -> dict[str, Any]:
    """Send an API call to the Balatro game and get the response.

    Args:
        sock: The TCP socket connected to the game.
        name: The name of the API function to call.
        arguments: Dictionary of arguments to pass to the API function (default: {}).

    Returns:
        The game state response as a dictionary.
    """
    payload = {"name": name, "arguments": arguments}
    client.send(json.dumps(payload).encode() + b"\n")
    response = client.recv(BUFFER_SIZE)
    gamestate = json.loads(response.decode().strip())
    return gamestate


# import platform
# from pathlib import Path
# import shutil
# def assert_error_response(
#     response,
#     expected_error_text,
#     expected_context_keys=None,
#     expected_error_code=None,
# ):
#     """
#     Helper function to assert the format and content of an error response.
#
#     Args:
#         response (dict): The response dictionary to validate. Must contain at least
#             the keys "error", "state", and "error_code".
#         expected_error_text (str): The expected error message text to check within
#             the "error" field of the response.
#         expected_context_keys (list, optional): A list of keys expected to be present
#             in the "context" field of the response, if the "context" field exists.
#         expected_error_code (str, optional): The expected error code to check within
#             the "error_code" field of the response.
#
#     Raises:
#         AssertionError: If the response does not match the expected format or content.
#     """
#     assert isinstance(response, dict)
#     assert "error" in response
#     assert "state" in response
#     assert "error_code" in response
#     assert expected_error_text in response["error"]
#     if expected_error_code:
#         assert response["error_code"] == expected_error_code
#     if expected_context_keys:
#         assert "context" in response
#         for key in expected_context_keys:
#             assert key in response["context"]
#
#
# def prepare_checkpoint(sock: socket.socket, checkpoint_path: Path) -> dict[str, Any]:
#     """Prepare a checkpoint file for loading and load it into the game.
#
#     This function copies a checkpoint file to Love2D's save directory and loads it
#     directly without requiring a game restart.
#
#     Args:
#         sock: Socket connection to the game.
#         checkpoint_path: Path to the checkpoint .jkr file to load.
#
#     Returns:
#         Game state after loading the checkpoint.
#
#     Raises:
#         FileNotFoundError: If checkpoint file doesn't exist.
#         RuntimeError: If loading the checkpoint fails.
#     """
#     if not checkpoint_path.exists():
#         raise FileNotFoundError(f"Checkpoint file not found: {checkpoint_path}")
#
#     # First, get the save directory from the game
#     game_state = send_and_receive_api_message(sock, "get_save_info", {})
#
#     # Determine the Love2D save directory
#     # On Linux with Steam, convert Windows paths
#
#     save_dir_str = game_state["save_directory"]
#     if platform.system() == "Linux" and save_dir_str.startswith("C:"):
#         # Replace C: with Linux Steam Proton prefix
#         linux_prefix = (
#             Path.home() / ".steam/steam/steamapps/compatdata/2379780/pfx/drive_c"
#         )
#         save_dir_str = str(linux_prefix) + "/" + save_dir_str[3:]
#
#     save_dir = Path(save_dir_str)
#
#     # Copy checkpoint to a test profile in Love2D save directory
#     test_profile = "test_checkpoint"
#     test_dir = save_dir / test_profile
#     test_dir.mkdir(parents=True, exist_ok=True)
#
#     dest_path = test_dir / "save.jkr"
#     shutil.copy2(checkpoint_path, dest_path)
#
#     # Load the save using the new load_save API function
#     love2d_path = f"{test_profile}/save.jkr"
#     game_state = send_and_receive_api_message(
#         sock, "load_save", {"save_path": love2d_path}
#     )
#
#     # Check for errors
#     if "error" in game_state:
#         raise RuntimeError(f"Failed to load checkpoint: {game_state['error']}")
#
#     return game_state
