#!/usr/bin/env python3

import argparse
import json
import socket
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from tqdm import tqdm

FIXTURES_DIR = Path(__file__).parent
HOST = "127.0.0.1"
PORT = 12346
BUFFER_SIZE = 65536


@dataclass
class FixtureSpec:
    paths: list[Path]
    setup: list[tuple[str, dict]]


def api(sock: socket.socket, name: str, arguments: dict) -> dict:
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
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"CORRUPTED_SAVE_FILE_FOR_TESTING\x00\x01\x02")


def load_fixtures_json() -> dict:
    with open(FIXTURES_DIR / "fixtures.json") as f:
        return json.load(f)


def steps_to_setup(steps: list[dict]) -> list[tuple[str, dict]]:
    return [(step["endpoint"], step["arguments"]) for step in steps]


def steps_to_key(steps: list[dict]) -> str:
    return json.dumps(steps, sort_keys=True, separators=(",", ":"))


def aggregate_fixtures(json_data: dict) -> list[FixtureSpec]:
    setup_to_paths: dict[str, list[Path]] = defaultdict(list)
    setup_to_steps: dict[str, list[dict]] = {}

    for group_name, fixtures in json_data.items():
        if group_name == "$schema":
            continue

        for fixture_name, steps in fixtures.items():
            path = FIXTURES_DIR / group_name / f"{fixture_name}.jkr"
            key = steps_to_key(steps)
            setup_to_paths[key].append(path)
            if key not in setup_to_steps:
                setup_to_steps[key] = steps

    fixtures = []
    for key, paths in setup_to_paths.items():
        steps = setup_to_steps[key]
        setup = steps_to_setup(steps)
        fixtures.append(FixtureSpec(paths=paths, setup=setup))

    return fixtures


def generate_fixture(sock: socket.socket, spec: FixtureSpec, pbar: tqdm) -> bool:
    primary_path = spec.paths[0]
    relative_path = primary_path.relative_to(FIXTURES_DIR)

    try:
        for endpoint, arguments in spec.setup:
            response = api(sock, endpoint, arguments)
            if "error" in response:
                pbar.write(f"  Error: {relative_path} - {response['error']}")
                return False

        primary_path.parent.mkdir(parents=True, exist_ok=True)
        response = api(sock, "save", {"path": str(primary_path)})
        if "error" in response:
            pbar.write(f"  Error: {relative_path} - {response['error']}")
            return False

        for dest_path in spec.paths[1:]:
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            dest_path.write_bytes(primary_path.read_bytes())

        return True

    except Exception as e:
        pbar.write(f"  Error: {relative_path} failed: {e}")
        return False


def should_generate(spec: FixtureSpec, overwrite: bool = False) -> bool:
    if overwrite:
        return True
    return not all(path.exists() for path in spec.paths)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("-o", "--overwrite", action="store_true")
    args = parser.parse_args()

    print("BalatroBot Fixture Generator v2")
    print(f"Connecting to {HOST}:{PORT}")
    print(f"Mode: {'Overwrite all' if args.overwrite else 'Generate missing only'}\n")

    json_data = load_fixtures_json()
    fixtures = aggregate_fixtures(json_data)
    print(f"Loaded {len(fixtures)} unique fixture configurations\n")

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.connect((HOST, PORT))
            sock.settimeout(10)

            success = 0
            skipped = 0
            failed = 0

            with tqdm(
                total=len(fixtures), desc="Generating fixtures", unit="fixture"
            ) as pbar:
                for spec in fixtures:
                    if should_generate(spec, overwrite=args.overwrite):
                        if generate_fixture(sock, spec, pbar):
                            success += 1
                        else:
                            failed += 1
                    else:
                        relative_path = spec.paths[0].relative_to(FIXTURES_DIR)
                        pbar.write(f"  Skipped: {relative_path}")
                        skipped += 1
                    pbar.update(1)

            api(sock, "menu", {})

            corrupted_path = FIXTURES_DIR / "load" / "corrupted.jkr"
            corrupt_file(corrupted_path)
            success += 1

            print(f"\nSummary: {success} generated, {skipped} skipped, {failed} failed")
            return 1 if failed > 0 else 0

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
