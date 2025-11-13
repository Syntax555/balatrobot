#!/usr/bin/env python3
"""Generate test fixture files for save/load endpoint testing.

This script connects to a running Balatro instance and uses the save endpoint
to generate .jkr fixture files for testing. It also creates corrupted files
for testing error handling.

Fixtures are organized by endpoint:
- save/start.jkr - Used by save tests to get into run state
- load/start.jkr - Used by load tests to test loading
- load/corrupted.jkr - Used by load tests to test error handling

Usage:
    python generate.py
"""

import json
import socket
from pathlib import Path

FIXTURES_DIR = Path(__file__).parent
HOST = "127.0.0.1"
PORT = 12346
BUFFER_SIZE = 65536


def send_request(sock: socket.socket, name: str, arguments: dict) -> None:
    """Send a JSON request to the Balatro server."""
    request = {"name": name, "arguments": arguments}
    message = json.dumps(request) + "\n"
    sock.sendall(message.encode())


def receive_response(sock: socket.socket, timeout: float = 3.0) -> dict:
    """Receive and parse JSON response from server."""
    sock.settimeout(timeout)
    response = sock.recv(BUFFER_SIZE)
    decoded = response.decode()
    first_newline = decoded.find("\n")
    if first_newline != -1:
        first_message = decoded[:first_newline]
    else:
        first_message = decoded.strip()
    return json.loads(first_message)


def generate_start_fixtures() -> None:
    """Generate start.jkr fixtures for both save and load endpoints.

    Creates identical start.jkr files in both save/ and load/ directories
    from the current game state. This should be run when the game is in
    an initial state (e.g., early in a run).
    """
    save_fixture = FIXTURES_DIR / "save" / "start.jkr"
    load_fixture = FIXTURES_DIR / "load" / "start.jkr"

    print(f"Generating start.jkr fixtures...")

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(10)
        sock.connect((HOST, PORT))

        # Save to save/ directory
        send_request(sock, "save", {"path": str(save_fixture)})
        response = receive_response(sock)

        if "error" in response:
            print(
                f"  Error: {response['error']} ({response.get('error_code', 'UNKNOWN')})"
            )
            print("  Make sure you're in an active run before generating fixtures")
            return

        if response.get("success"):
            print(f"  Generated {save_fixture}")
            print(f"  File size: {save_fixture.stat().st_size} bytes")

            # Copy to load/ directory
            load_fixture.write_bytes(save_fixture.read_bytes())
            print(f"  Generated {load_fixture}")
            print(f"  File size: {load_fixture.stat().st_size} bytes")

            # Validate by loading it back
            send_request(sock, "load", {"path": str(load_fixture)})
            load_response = receive_response(sock)

            if load_response.get("success"):
                print(f"  Validated: fixtures load successfully")
            else:
                print(f"  Warning: fixtures generated but failed to load")
                print(f"  Error: {load_response.get('error', 'Unknown error')}")
        else:
            print(f"  Failed to generate fixtures")


def generate_corrupted() -> None:
    """Generate corrupted.jkr fixture for error testing.

    Creates an intentionally corrupted .jkr file in load/ directory to test
    EXEC_INVALID_SAVE_FORMAT error handling in the load endpoint.
    """
    fixture_path = FIXTURES_DIR / "load" / "corrupted.jkr"
    print(f"Generating {fixture_path}...")

    # Write invalid/truncated data that won't decompress correctly
    corrupted_data = b"CORRUPTED_SAVE_FILE_FOR_TESTING\x00\x01\x02"

    fixture_path.write_bytes(corrupted_data)
    print(f"  Generated {fixture_path}")
    print(f"  File size: {fixture_path.stat().st_size} bytes")
    print(f"  This file is intentionally corrupted for error testing")


def main() -> None:
    """Main entry point for fixture generation."""
    print("BalatroBot Fixture Generator")
    print(f"Connecting to {HOST}:{PORT}")
    print()

    try:
        generate_start_fixtures()
        print()
        generate_corrupted()
        print()

        print("Fixture generation complete!")
        print(f"Fixtures organized in: {FIXTURES_DIR}/")
        print("  - save/start.jkr")
        print("  - load/start.jkr")
        print("  - load/corrupted.jkr")

    except ConnectionRefusedError:
        print(f"Error: Could not connect to Balatro at {HOST}:{PORT}")
        print("Make sure Balatro is running with BalatroBot mod loaded")
        return 1
    except Exception as e:
        print(f"Unexpected error: {e}")
        return 1

    return 0


if __name__ == "__main__":
    exit(main())
