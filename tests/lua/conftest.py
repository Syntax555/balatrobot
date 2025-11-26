"""Lua API test-specific configuration and fixtures."""

import json
import socket
import tempfile
import uuid
from pathlib import Path
from typing import Any, Generator

import pytest

# ============================================================================
# Constants
# ============================================================================

HOST: str = "127.0.0.1"  # Default host for Balatro server
PORT: int = 12346  # Default port for Balatro server
BUFFER_SIZE: int = 65536  # 64KB buffer for TCP messages


@pytest.fixture(scope="session")
def host() -> str:
    """Return the default Balatro server host."""
    return HOST


@pytest.fixture
def client(host: str, port: int) -> Generator[socket.socket, None, None]:
    """Create a TCP socket client connected to Balatro game instance.

    Args:
        host: The hostname or IP address of the Balatro game server.
        port: The port number the Balatro game server is listening on.

    Yields:
        A connected TCP socket for communicating with the game.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(60)  # 60 second timeout for operations
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, BUFFER_SIZE)
        sock.connect((host, port))
        yield sock


@pytest.fixture(scope="session")
def port() -> int:
    """Return the default Balatro server port."""
    return PORT


# ============================================================================
# Helper Functions
# ============================================================================


def api(
    client: socket.socket,
    name: str,
    arguments: dict = {},
    timeout: int = 5,
) -> dict[str, Any]:
    """Send an API call to the Balatro game and get the response.

    Args:
        client: The TCP socket connected to the game.
        name: The name of the API function to call.
        arguments: Dictionary of arguments to pass to the API function (default: {}).

    Returns:
        The game state response as a dictionary.
    """
    payload = {"name": name, "arguments": arguments}
    client.send(json.dumps(payload).encode() + b"\n")
    client.settimeout(timeout)
    response = client.recv(BUFFER_SIZE)
    gamestate = json.loads(response.decode().strip())
    return gamestate


def send_request(sock: socket.socket, name: str, arguments: dict[str, Any]) -> None:
    """Send a JSON request to the server.

    Args:
        sock: The TCP socket connected to the game.
        name: The name of the endpoint to call.
        arguments: Dictionary of arguments to pass to the endpoint.
    """
    request = {"name": name, "arguments": arguments}
    message = json.dumps(request) + "\n"
    sock.sendall(message.encode())


def receive_response(sock: socket.socket, timeout: float = 3.0) -> dict[str, Any]:
    """Receive and parse JSON response from server.

    Args:
        sock: The TCP socket connected to the game.
        timeout: Socket timeout in seconds (default: 3.0).

    Returns:
        The parsed JSON response as a dictionary.
    """
    sock.settimeout(timeout)
    response = sock.recv(BUFFER_SIZE)
    decoded = response.decode()

    # Parse first complete message
    first_newline = decoded.find("\n")
    if first_newline != -1:
        first_message = decoded[:first_newline]
    else:
        first_message = decoded.strip()

    return json.loads(first_message)


def get_fixture_path(endpoint: str, fixture_name: str) -> Path:
    """Get path to a test fixture file.

    Args:
        endpoint: The endpoint directory (e.g., "save", "load").
        fixture_name: Name of the fixture file (e.g., "start.jkr").

    Returns:
        Path to the fixture file in tests/fixtures/<endpoint>/.
    """
    fixtures_dir = Path(__file__).parent.parent / "fixtures"
    return fixtures_dir / endpoint / f"{fixture_name}.jkr"


def create_temp_save_path() -> Path:
    """Create a temporary path for save files.

    Returns:
        Path to a temporary .jkr file in the system temp directory.
    """
    temp_dir = Path(tempfile.gettempdir())
    return temp_dir / f"balatrobot_test_{uuid.uuid4().hex[:8]}.jkr"


# ============================================================================
# Assertion Helpers
# ============================================================================


def assert_success_response(response: dict[str, Any]) -> None:
    """Validate success response structure.

    Args:
        response: The response dictionary to validate.

    Raises:
        AssertionError: If the response is not a valid success response.
    """
    assert "success" in response, "Success response must have 'success' field"
    assert response["success"] is True, "'success' field must be True"
    assert "error" not in response, "Success response should not have 'error' field"
    assert "error_code" not in response, (
        "Success response should not have 'error_code' field"
    )


def assert_error_response(
    response: dict[str, Any],
    expected_error_code: str | None = None,
    expected_message_contains: str | None = None,
) -> None:
    """Validate error response structure and content.

    Args:
        response: The response dictionary to validate.
        expected_error_code: The expected error code (optional).
        expected_message_contains: Substring expected in error message (optional).

    Raises:
        AssertionError: If the response is not a valid error response or doesn't match expectations.
    """
    assert "error" in response, "Error response must have 'error' field"
    assert "error_code" in response, "Error response must have 'error_code' field"

    assert isinstance(response["error"], str), "'error' must be a string"
    assert isinstance(response["error_code"], str), "'error_code' must be a string"

    if expected_error_code:
        assert response["error_code"] == expected_error_code, (
            f"Expected error_code '{expected_error_code}', got '{response['error_code']}'"
        )

    if expected_message_contains:
        assert expected_message_contains.lower() in response["error"].lower(), (
            f"Expected error message to contain '{expected_message_contains}', got '{response['error']}'"
        )


def assert_health_response(response: dict[str, Any]) -> None:
    """Validate health response structure.

    Args:
        response: The response dictionary to validate.

    Raises:
        AssertionError: If the response is not a valid health response.
    """
    assert "status" in response, "Health response must have 'status' field"
    assert response["status"] == "ok", "Health response 'status' must be 'ok'"


def load_fixture(
    client: socket.socket,
    endpoint: str,
    fixture_name: str,
    cache: bool = True,
) -> dict[str, Any]:
    """Load a fixture file and return the resulting gamestate.

    This helper function consolidates the common pattern of:
    1. Loading a fixture file (or generating it if missing)
    2. Asserting the load succeeded
    3. Getting the current gamestate

    If the fixture file doesn't exist or cache=False, it will be automatically
    generated using the setup steps defined in fixtures.json.

    Args:
        client: The TCP socket connected to the game.
        endpoint: The endpoint directory name (e.g., "buy", "discard").
        fixture_name: Name of the fixture file (e.g., "state-SHOP.jkr").
        cache: If True, use existing fixture file. If False, regenerate (default: True).

    Returns:
        The current gamestate after loading the fixture.

    Raises:
        AssertionError: If the load operation or generation fails.
        KeyError: If fixture definition not found in fixtures.json.

    Example:
        gamestate = load_fixture(client, "buy", "state-SHOP.jkr")
        response = api(client, "buy", {"card": 0})
        assert response["success"]
    """
    fixture_path = get_fixture_path(endpoint, fixture_name)

    # Generate fixture if it doesn't exist or cache=False
    if not fixture_path.exists() or not cache:
        fixtures_json_path = Path(__file__).parent.parent / "fixtures" / "fixtures.json"
        with open(fixtures_json_path) as f:
            fixtures_data = json.load(f)

        if endpoint not in fixtures_data:
            raise KeyError(f"Endpoint '{endpoint}' not found in fixtures.json")
        if fixture_name not in fixtures_data[endpoint]:
            raise KeyError(
                f"Fixture key '{fixture_name}' not found in fixtures.json['{endpoint}']"
            )

        setup_steps = fixtures_data[endpoint][fixture_name]

        # Execute each setup step
        for step in setup_steps:
            step_endpoint = step["endpoint"]
            step_arguments = step.get("arguments", {})
            response = api(client, step_endpoint, step_arguments)

            # Check for errors during generation
            if "error" in response:
                raise AssertionError(
                    f"Fixture generation failed at step {step_endpoint}: {response['error']}"
                )

        # Save the fixture
        fixture_path.parent.mkdir(parents=True, exist_ok=True)
        save_response = api(client, "save", {"path": str(fixture_path)})
        assert_success_response(save_response)

    # Load the fixture
    load_response = api(client, "load", {"path": str(fixture_path)})
    assert_success_response(load_response)
    return api(client, "gamestate", {})
