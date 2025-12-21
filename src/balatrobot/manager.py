"""Manager for multiple BalatroBot instances."""

import asyncio
import subprocess
from dataclasses import replace
from datetime import datetime
from pathlib import Path

from balatrobot.config import Config
from balatrobot.platforms import get_launcher


class InstanceManager:
    """Manages balatrobot subprocess instances."""

    def __init__(self, config: Config) -> None:
        """Initialize the manager.

        Args:
            config: Base configuration for all instances.
        """
        self._base_config = config
        self._processes: dict[int, subprocess.Popen] = {}  # port -> process
        self._logs: dict[int, Path] = {}  # port -> log file path

        # Create session directory with timestamp
        timestamp = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
        self._session_dir = Path(config.logs_path) / timestamp
        self._session_dir.mkdir(parents=True, exist_ok=True)

    async def start(self, port: int) -> subprocess.Popen:
        """Start a balatrobot instance on the specified port.

        Args:
            port: Port number for the instance.

        Returns:
            The subprocess.Popen object.
        """
        if port in self._processes:
            raise RuntimeError(f"Balatrobot already running on port {port}")

        config = replace(self._base_config, port=port)
        launcher = get_launcher(config.platform)

        try:
            process = await launcher.start(config, self._session_dir)
            log_path = self._session_dir / f"{config.port}.log"
            self._processes[config.port] = process
            self._logs[config.port] = log_path
            return process
        except Exception as e:
            print(f"Failed to start instance on port {config.port}: {e}")
            raise

    async def stop(self, port: int) -> None:
        """Stop the balatrobot instance on the given port.

        Args:
            port: Port number of the instance to stop.
        """
        if port not in self._processes:
            return

        process = self._processes.pop(port)
        self._logs.pop(port, None)

        print(f"Stopping instance on port {port}...")

        # Try graceful termination first
        process.terminate()

        # Use asyncio to wait without blocking
        loop = asyncio.get_running_loop()
        try:
            await asyncio.wait_for(
                loop.run_in_executor(None, process.wait),
                timeout=5,
            )
        except asyncio.TimeoutError:
            # Force kill if still running
            print(f"Force killing instance on port {port}...")
            process.kill()
            await loop.run_in_executor(None, process.wait)

    async def stop_all(self) -> None:
        """Stop all managed balatrobot instances."""
        ports = list(self._processes.keys())
        if not ports:
            return

        # Stop all in parallel
        await asyncio.gather(*[self.stop(port) for port in ports])

    async def check_all(self) -> bool:
        """Check if all instances are still running.

        Returns:
            True if all instances are running, False otherwise.
        """
        all_alive = True

        for port in list(self._processes.keys()):
            process = self._processes[port]
            if process.poll() is not None:
                print(
                    f"Instance on port {port} exited unexpectedly (Return Code: {process.returncode})"
                )
                all_alive = False
                self._processes.pop(port)
                self._logs.pop(port, None)

        return all_alive
