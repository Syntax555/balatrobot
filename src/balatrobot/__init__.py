"""BalatroBot - API for developing Balatro bots."""

import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

from balatrobot.config import Config
from balatrobot.platforms import get_launcher

__version__ = "0.7.5"


async def start_instance(
    host: str = "127.0.0.1",
    port: int = 12346,
    fast: bool = False,
    headless: bool = False,
    render_on_api: bool = False,
    audio: bool = False,
    debug: bool = False,
    no_shaders: bool = False,
    balatro_exe: str | None = None,
    lovely_lib: str | None = None,
    logs: str = "logs",
    **kwargs: Any,
) -> subprocess.Popen:
    """Start a Balatro instance programmatically.

    Args:
        host: Server hostname
        port: Server port
        fast: Enable fast mode (10x speed)
        headless: Enable headless mode
        render_on_api: Render only on API calls
        audio: Enable audio
        debug: Enable debug mode
        no_shaders: Disable shaders
        balatro_exe: Path to Balatro executable (override)
        lovely_lib: Path to lovely injector (override)
        logs: Directory for log files
        **kwargs: Additional arguments (ignored)

    Returns:
        The subprocess.Popen object of the started game

    Raises:
        RuntimeError: If startup fails
    """
    # Extract Config parameters from function locals
    config_params = {k: v for k, v in locals().items() if k not in ("logs", "kwargs")}
    config = Config(**config_params)

    # Create session directory for logs
    timestamp = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
    session_dir = Path(logs) / timestamp
    session_dir.mkdir(parents=True, exist_ok=True)

    launcher = get_launcher()
    process = await launcher.start(config, session_dir)
    return process
