"""Base launcher class for all platforms."""

import asyncio
import subprocess
from abc import ABC, abstractmethod
from pathlib import Path

import httpx

from balatrobot.config import Config

HEALTH_TIMEOUT = 30.0


class BaseLauncher(ABC):
    """Abstract base class for platform-specific launchers."""

    @abstractmethod
    def validate_paths(self, config: Config) -> None:
        """Validate paths exist, apply platform defaults if None.

        Mutates config in-place with platform-specific defaults.

        Raises:
            RuntimeError: If required paths are missing or invalid.
        """
        ...

    @abstractmethod
    def build_env(self, config: Config) -> dict[str, str]:
        """Build environment dict for subprocess.

        Returns:
            Environment dict including os.environ and platform-specific vars.
        """
        ...

    @abstractmethod
    def build_cmd(self, config: Config) -> list[str]:
        """Build command list for subprocess.

        Returns:
            Command list suitable for subprocess.Popen.
        """
        ...

    async def wait_for_health(
        self, host: str, port: int, timeout: float = HEALTH_TIMEOUT
    ) -> None:
        """Wait for health endpoint to respond.

        Retries HTTP health check until success or timeout.

        Args:
            host: Host to connect to.
            port: Port to connect to.
            timeout: Maximum time to wait in seconds.

        Raises:
            RuntimeError: If health check fails after timeout.
        """
        url = f"http://{host}:{port}"
        payload = {"jsonrpc": "2.0", "method": "health", "params": {}, "id": 1}
        start = asyncio.get_event_loop().time()

        while asyncio.get_event_loop().time() - start < timeout:
            try:
                async with httpx.AsyncClient(timeout=2.0) as client:
                    response = await client.post(url, json=payload)
                    data = response.json()
                    if "result" in data and data["result"].get("status") == "ok":
                        return
            except (httpx.ConnectError, httpx.TimeoutException):
                pass
            await asyncio.sleep(0.5)

        raise RuntimeError(f"Health check failed after {timeout}s on {host}:{port}")

    async def start(self, config: Config, session_dir: Path) -> subprocess.Popen:
        """Start Balatro with the given configuration.

        Args:
            config: Launcher configuration (mutated with defaults).
            session_dir: Directory for log files.

        Returns:
            The subprocess.Popen object.

        Raises:
            RuntimeError: If startup fails.
        """
        self.validate_paths(config)
        env = self.build_env(config)
        cmd = self.build_cmd(config)

        # Start process
        log_path = session_dir / f"{config.port}.log"
        print(f"Starting Balatro on port {config.port}...")

        with open(log_path, "w") as log:
            process = subprocess.Popen(
                cmd,
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
            )

        # Wait for health
        print(f"Waiting for health check on {config.host}:{config.port}...")
        try:
            await self.wait_for_health(config.host, config.port)
        except RuntimeError as e:
            if process.poll() is None:
                process.terminate()
            raise RuntimeError(f"{e}. Check log file: {log_path}") from e

        print(f"Balatro started (PID: {process.pid})")
        return process
