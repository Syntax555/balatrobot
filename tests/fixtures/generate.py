#!/usr/bin/env python3
"""Generate test fixture files for endpoint testing.

This script automatically connects to a running Balatro instance and generates
.jkr fixture files for testing endpoints.

Usage:
    python generate.py

Requirements:
- Balatro must be running with the BalatroBot mod loaded
- Default connection: 127.0.0.1:12346
"""

import json
import socket
from dataclasses import dataclass
from pathlib import Path

from tqdm import tqdm

FIXTURES_DIR = Path(__file__).parent
HOST = "127.0.0.1"
PORT = 12346
BUFFER_SIZE = 65536


@dataclass
class FixtureSpec:
    """Specification for a single fixture."""

    paths: list[Path]  # Output paths (first is primary, rest are copies)
    setup: list[tuple[str, dict]]  # Sequence of API calls: [(name, arguments), ...]


def api(sock: socket.socket, name: str, arguments: dict) -> dict:
    """Send API call to Balatro and return response.

    Args:
        sock: Connected socket to Balatro server.
        name: API endpoint name.
        arguments: API call arguments.

    Returns:
        Response dictionary from server.
    """
    request = {"name": name, "arguments": arguments}
    message = json.dumps(request) + "\n"
    sock.sendall(message.encode())

    response = sock.recv(BUFFER_SIZE)
    decoded = response.decode()
    first_newline = decoded.find("\n")
    if first_newline != -1:
        first_message = decoded[:first_newline]
    else:
        first_message = decoded.strip()
    return json.loads(first_message)


def corrupt_file(path: Path) -> None:
    """Corrupt a file for error testing."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"CORRUPTED_SAVE_FILE_FOR_TESTING\x00\x01\x02")


def generate_fixture(
    sock: socket.socket,
    spec: FixtureSpec,
    pbar: tqdm,
) -> bool:
    """Generate a single fixture from its specification."""
    primary_path = spec.paths[0]
    relative_path = primary_path.relative_to(FIXTURES_DIR)

    try:
        # Execute API call sequence
        for endpoint, arguments in spec.setup:
            api(sock, endpoint, arguments)

        # Save fixture
        primary_path.parent.mkdir(parents=True, exist_ok=True)
        api(sock, "save", {"path": str(primary_path)})

        # Copy to additional paths
        for dest_path in spec.paths[1:]:
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            dest_path.write_bytes(primary_path.read_bytes())

        return True

    except Exception as e:
        pbar.write(f"  Error: {relative_path} failed: {e}")
        return False


def build_fixtures() -> list[FixtureSpec]:
    """Build fixture specifications."""
    return [
        FixtureSpec(
            paths=[
                FIXTURES_DIR / "save" / "state-BLIND_SELECT.jkr",
                FIXTURES_DIR / "load" / "state-BLIND_SELECT.jkr",
                FIXTURES_DIR / "menu" / "state-BLIND_SELECT.jkr",
                FIXTURES_DIR / "health" / "state-BLIND_SELECT.jkr",
                FIXTURES_DIR / "start" / "state-BLIND_SELECT.jkr",
                FIXTURES_DIR
                / "skip"
                / "state-BLIND_SELECT--blinds.small.status-SELECT.jkr",
                FIXTURES_DIR
                / "gamestate"
                / "state-BLIND_SELECT--round_num-0--deck-RED--stake-WHITE.jkr",
            ],
            setup=[
                ("menu", {}),
                ("start", {"deck": "RED", "stake": "WHITE"}),
            ],
        ),
        FixtureSpec(
            paths=[
                FIXTURES_DIR
                / "skip"
                / "state-BLIND_SELECT--blinds.big.status-SELECT.jkr",
            ],
            setup=[
                ("menu", {}),
                ("start", {"deck": "RED", "stake": "WHITE"}),
                ("skip", {}),
            ],
        ),
        FixtureSpec(
            paths=[
                FIXTURES_DIR
                / "skip"
                / "state-BLIND_SELECT--blinds.boss.status-SELECT.jkr",
            ],
            setup=[
                ("menu", {}),
                ("start", {"deck": "RED", "stake": "WHITE"}),
                ("skip", {}),
                ("skip", {}),
            ],
        ),
    ]


def should_generate(spec: FixtureSpec) -> bool:
    """Check if fixture should be generated (any path missing)."""
    return not all(path.exists() for path in spec.paths)


def main() -> int:
    """Main entry point."""
    print("BalatroBot Fixture Generator")
    print(f"Connecting to {HOST}:{PORT}\n")

    fixtures = build_fixtures()

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.connect((HOST, PORT))

            success = 0
            skipped = 0
            failed = 0

            with tqdm(
                total=len(fixtures), desc="Generating fixtures", unit="fixture"
            ) as pbar:
                for spec in fixtures:
                    if should_generate(spec):
                        if generate_fixture(sock, spec, pbar):
                            success += 1
                        else:
                            failed += 1
                    else:
                        relative_path = spec.paths[0].relative_to(FIXTURES_DIR)
                        pbar.write(f"  Skipped: {relative_path}")
                        skipped += 1
                    pbar.update(1)

            # Go back to menu state
            api(sock, "menu", {})

            # Generate corrupted fixture
            corrupted_path = FIXTURES_DIR / "load" / "corrupted.jkr"
            corrupt_file(corrupted_path)
            success += 1

            print(f"\nSummary: {success} generated, {skipped} skipped, {failed} failed")

            if failed > 0:
                return 1

            return 0

    except ConnectionRefusedError:
        print(f"Error: Could not connect to Balatro at {HOST}:{PORT}")
        print("Make sure Balatro is running with BalatroBot mod loaded")
        return 1
    except socket.timeout:
        print(f"Error: Connection timeout to Balatro at {HOST}:{PORT}")
        return 1
    except Exception as e:
        print(f"Error: {e}")
        return 1


if __name__ == "__main__":
    exit(main())
