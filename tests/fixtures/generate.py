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
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from tqdm import tqdm

FIXTURES_DIR = Path(__file__).parent
HOST = "127.0.0.1"
PORT = 12346
BUFFER_SIZE = 65536


@dataclass
class FixtureSpec:
    """Specification for a single fixture."""

    name: str  # Display name
    paths: list[Path]  # Output paths (first is primary, rest are copies)
    setup: Callable[[socket.socket], bool] | None = None  # Game state setup
    validate: bool = True  # Whether to validate by loading
    post_process: Callable[[Path], None] | None = (
        None  # Post-processing (e.g., corruption)
    )
    depends_on: list[str] = field(default_factory=list)  # Dependencies


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


def start_new_game(
    sock: socket.socket,
    deck: str = "RED",
    stake: str = "WHITE",
    seed: str | None = None,
) -> bool:
    """Start a new game with specified deck and stake."""
    # Ensure menu state
    send_request(sock, "menu", {})
    res = receive_response(sock)
    if "error" in res or res.get("state") != "MENU":
        return False

    # Start game
    arguments = {"deck": deck, "stake": stake}
    if seed:
        arguments["seed"] = seed
    send_request(sock, "start", arguments)
    res = receive_response(sock)

    if "error" in res:
        return False

    state = res.get("state")
    if state == "BLIND_SELECT":
        return res.get("deck") == deck and res.get("stake") == stake
    return False


def corrupt_file(path: Path) -> None:
    """Corrupt a file for error testing."""
    path.write_bytes(b"CORRUPTED_SAVE_FILE_FOR_TESTING\x00\x01\x02")


def generate_fixture(
    sock: socket.socket | None,
    spec: FixtureSpec,
    pbar: tqdm,
) -> bool:
    """Generate a single fixture from its specification."""
    primary_path = spec.paths[0]

    try:
        # Setup game state
        if spec.setup:
            if not sock:
                pbar.write(f"  Error: {spec.name} requires socket connection")
                return False
            if not spec.setup(sock):
                pbar.write(f"  Error: {spec.name} setup failed")
                return False

        # Save fixture
        primary_path.parent.mkdir(parents=True, exist_ok=True)
        assert sock, "Socket connection required for save"

        if spec.setup:  # Game-based fixture
            send_request(sock, "save", {"path": str(primary_path)})
            res = receive_response(sock)
            if not res.get("success"):
                error = res.get("error", "Unknown error")
                pbar.write(f"  Error: {spec.name} save failed: {error}")
                return False
        else:  # Non-game fixture (created by post_process)
            primary_path.touch()

        # Copy to additional paths
        for dest_path in spec.paths[1:]:
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            dest_path.write_bytes(primary_path.read_bytes())

        # Post-processing
        if spec.post_process:
            for path in spec.paths:
                spec.post_process(path)

        # Validation
        if spec.validate and spec.setup and sock:
            send_request(sock, "load", {"path": str(primary_path)})
            load_response = receive_response(sock)
            if not load_response.get("success"):
                pbar.write(f"  Warning: {spec.name} validation failed")

        return True

    except Exception as e:
        pbar.write(f"  Error: {spec.name} failed: {e}")
        return False


def build_fixtures() -> list[FixtureSpec]:
    """Build fixture specifications."""
    return [
        FixtureSpec(
            name="Initial state (BLIND_SELECT)",
            paths=[
                FIXTURES_DIR / "save" / "state-BLIND_SELECT.jkr",
                FIXTURES_DIR / "load" / "state-BLIND_SELECT.jkr",
                FIXTURES_DIR / "menu" / "state-BLIND_SELECT.jkr",
                FIXTURES_DIR / "health" / "state-BLIND_SELECT.jkr",
                FIXTURES_DIR / "start" / "state-BLIND_SELECT.jkr",
                FIXTURES_DIR
                / "gamestate"
                / "state-BLIND_SELECT--round_num-0--deck-RED--stake-WHITE.jkr",
            ],
            setup=lambda sock: start_new_game(sock, deck="RED", stake="WHITE"),
        ),
        FixtureSpec(
            name="load/corrupted.jkr",
            paths=[FIXTURES_DIR / "load" / "corrupted.jkr"],
            setup=None,
            validate=False,
            post_process=corrupt_file,
        ),
    ]


def should_generate(spec: FixtureSpec, regenerated: set[str]) -> bool:
    """Check if fixture should be generated (dependencies or missing files)."""
    # Check dependencies - if any dependency was regenerated, regenerate this too
    if any(dep in regenerated for dep in spec.depends_on):
        return True

    # Check if any path is missing
    return not all(path.exists() for path in spec.paths)


def main() -> int:
    """Main entry point."""
    print("BalatroBot Fixture Generator")
    print(f"Connecting to {HOST}:{PORT}\n")

    fixtures = build_fixtures()

    # Check existing fixtures
    existing = [spec for spec in fixtures if all(path.exists() for path in spec.paths)]

    if existing:
        print(f"Found {len(existing)} existing fixture(s)")
        response = input("Delete all existing fixtures and regenerate? [y/N]: ")
        if response.lower() == "y":
            for spec in existing:
                for path in spec.paths:
                    if path.exists():
                        path.unlink()
            print("Deleted existing fixtures\n")
        else:
            print("Will skip existing fixtures\n")

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.connect((HOST, PORT))

            regenerated: set[str] = set()
            success = 0
            skipped = 0
            failed = 0

            with tqdm(
                total=len(fixtures), desc="Generating fixtures", unit="fixture"
            ) as pbar:
                for spec in fixtures:
                    if should_generate(spec, regenerated):
                        if generate_fixture(sock, spec, pbar):
                            regenerated.add(spec.name)
                            success += 1
                        else:
                            failed += 1
                    else:
                        pbar.write(f"  Skipped: {spec.name} (already exists)")
                        skipped += 1
                    pbar.update(1)

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
