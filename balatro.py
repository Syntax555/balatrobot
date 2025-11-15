#!/usr/bin/env python3
"""Minimal Balatro launcher for macOS."""

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

# macOS-specific paths
STEAM_PATH = Path.home() / "Library/Application Support/Steam/steamapps/common/Balatro"
BALATRO_EXE = STEAM_PATH / "Balatro.app/Contents/MacOS/love"
LOVELY_LIB = STEAM_PATH / "liblovely.dylib"
LOGS_DIR = Path("logs")


def kill():
    """Kill all running Balatro instances."""
    print("Killing all Balatro instances...")
    subprocess.run(["pkill", "-f", "Balatro\\.app"], stderr=subprocess.DEVNULL)
    time.sleep(1)
    # Force kill if still running
    subprocess.run(["pkill", "-9", "-f", "Balatro\\.app"], stderr=subprocess.DEVNULL)
    print("Done.")


def status():
    """Show running Balatro instances with ports."""
    # Find Balatro processes
    result = subprocess.run(
        ["ps", "aux"],
        capture_output=True,
        text=True,
    )

    balatro_pids = []
    for line in result.stdout.splitlines():
        if "Balatro.app" in line and "grep" not in line:
            parts = line.split()
            if len(parts) > 1:
                balatro_pids.append(parts[1])

    if not balatro_pids:
        print("No Balatro instances running")
        return

    # Find ports for each PID
    for pid in balatro_pids:
        result = subprocess.run(
            ["lsof", "-Pan", "-p", pid, "-i", "TCP"],
            capture_output=True,
            text=True,
            stderr=subprocess.DEVNULL,
        )

        port = None
        for line in result.stdout.splitlines():
            if "LISTEN" in line:
                parts = line.split()
                for part in parts:
                    if ":" in part:
                        port = part.split(":")[-1]
                        break
                if port:
                    break

        if port:
            log_file = LOGS_DIR / f"balatro_{port}.log"
            print(f"Port {port}, PID {pid}, Log: {log_file}")


def start(args):
    """Start Balatro with given configuration."""
    # Kill existing instances first
    subprocess.run(["pkill", "-f", "Balatro\\.app"], stderr=subprocess.DEVNULL)
    time.sleep(1)

    # Create logs directory
    LOGS_DIR.mkdir(exist_ok=True)

    # Set environment variables
    env = os.environ.copy()
    env["DYLD_INSERT_LIBRARIES"] = str(LOVELY_LIB)
    env["BALATROBOT_HOST"] = args.host
    env["BALATROBOT_PORT"] = str(args.port)

    if args.headless:
        env["BALATROBOT_HEADLESS"] = "1"
    if args.fast:
        env["BALATROBOT_FAST"] = "1"
    if args.render_on_api:
        env["BALATROBOT_RENDER_ON_API"] = "1"
    if args.audio:
        env["BALATROBOT_AUDIO"] = "1"
    if args.debug:
        env["BALATROBOT_DEBUG"] = "1"

    # Open log file
    log_file = LOGS_DIR / f"balatro_{args.port}.log"
    with open(log_file, "w") as log:
        # Start Balatro
        process = subprocess.Popen(
            [str(BALATRO_EXE)],
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
        )

    # Verify it started
    time.sleep(4)
    if process.poll() is not None:
        print(f"ERROR: Balatro failed to start. Check {log_file}")
        sys.exit(1)

    subprocess.Popen(
        "command -v aerospace >/dev/null 2>&1 && aerospace workspace 3",
        shell=True,
    )

    print(f"Port {args.port}, PID {process.pid}, Log: {log_file}")


def main():
    parser = argparse.ArgumentParser(description="Balatro launcher")

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Start command
    start_parser = subparsers.add_parser(
        "start",
        help="Start Balatro (default)",
    )
    start_parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Server host (default: 127.0.0.1)",
    )
    start_parser.add_argument(
        "--port",
        type=int,
        default=12346,
        help="Server port (default: 12346)",
    )
    start_parser.add_argument(
        "--headless",
        action="store_true",
        help="Run in headless mode",
    )
    start_parser.add_argument(
        "--fast",
        action="store_true",
        help="Run in fast mode",
    )
    start_parser.add_argument(
        "--render-on-api",
        action="store_true",
        help="Render only on API calls",
    )
    start_parser.add_argument(
        "--audio",
        action="store_true",
        help="Enable audio",
    )
    start_parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug mode (requires DebugPlus mod, loads test endpoints)",
    )

    # Kill command
    subparsers.add_parser(
        "kill",
        help="Kill all Balatro instances",
    )

    # Status command
    subparsers.add_parser(
        "status",
        help="Show running instances",
    )

    args = parser.parse_args()

    # Execute command
    if args.command == "kill":
        kill()
    elif args.command == "status":
        status()
    elif args.command == "start":
        start(args)


if __name__ == "__main__":
    main()
