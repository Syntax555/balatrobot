"""CLI entry point for BalatroBot launcher."""

import argparse
import asyncio

from balatrobot.config import Config
from balatrobot.manager import InstanceManager


def create_parser() -> argparse.ArgumentParser:
    """Create the argument parser for balatrobot CLI."""
    # fmt: off
    parser = argparse.ArgumentParser(prog="balatrobot", description="Start Balatro with BalatroBot mod loaded")

    # No defaults - env vars and dataclass defaults handle it
    parser.add_argument("--host", help="Server hostname (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, help="Server port (default: 12346)")
    parser.add_argument( "--parallel", type=int, help="Number of parallel instances (default: 1)")
    parser.add_argument("--logs-path", help="Directory for log files (default: logs)")

    # Boolean flags - store_const so None means "not provided" -> check env var
    parser.add_argument("--fast", action="store_const", const=True, help="Enable fast mode (10x speed)")
    parser.add_argument("--headless", action="store_const", const=True, help="Enable headless mode")
    parser.add_argument("--render-on-api", action="store_const", const=True, help="Render only on API calls")
    parser.add_argument("--audio", action="store_const", const=True, help="Enable audio")
    parser.add_argument("--debug", action="store_const", const=True, help="Enable debug mode")
    parser.add_argument("--no-shaders", action="store_const", const=True, help="Disable shaders")

    # Path args
    parser.add_argument("--balatro-path", help="Path to Balatro executable")
    parser.add_argument("--lovely-path", help="Path to lovely library")
    parser.add_argument("--love-path", help="Path to LOVE executable")
    parser.add_argument("--mods-path", help="Path to Mods directory")
    parser.add_argument("--settings-path", help="Path to game settings directory")
    parser.add_argument("--platform", choices=["darwin", "linux", "windows", "native"])
    # fmt: on

    return parser


async def async_main(argv: list[str] | None = None) -> int:
    """Async main entry point."""
    parser = create_parser()
    args = parser.parse_args(argv)
    config = Config.from_args(args)
    manager = InstanceManager(config)
    try:
        tasks = []
        for i in range(config.parallel):
            port = config.port + i
            tasks.append(manager.start(port))

        await asyncio.gather(*tasks)
        print(f"Started {config.parallel} instance(s). Press Ctrl+C to stop.")

        while True:
            await manager.check_all()
            await asyncio.sleep(5)

    finally:
        await manager.stop_all()

    return 0


def main(argv: list[str] | None = None) -> int:
    """Main entry point for balatrobot CLI."""
    try:
        return asyncio.run(async_main(argv))
    except KeyboardInterrupt:
        return 0
