"""Native LOVE launcher for Linux environments."""

import os
import platform
import shutil
from pathlib import Path

from balatrobot.config import Config
from balatrobot.platforms.base import BaseLauncher


def _detect_love_path() -> Path | None:
    """Detect LOVE executable in PATH."""
    found = shutil.which("love")
    return Path(found) if found else None


def _detect_lovely_path() -> Path | None:
    """Detect liblovely.so in standard locations."""
    candidates = [
        Path("/usr/local/lib/liblovely.so"),
        Path.home() / ".local/lib/liblovely.so",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


class NativeLauncher(BaseLauncher):
    """Native LOVE launcher using LD_PRELOAD injection (Linux only).

    This launcher is designed for:
    - Docker containers with LOVE installed
    - Linux development environments with native LOVE

    Requirements:
    - Linux operating system
    - `love` executable in PATH or specified via --love-path
    - liblovely.so specified via --lovely-path
    - Game directory specified via --balatro-path
    """

    def validate_paths(self, config: Config) -> None:
        """Validate and auto-detect paths for native Linux launcher."""
        if platform.system().lower() != "linux":
            raise RuntimeError("Native launcher is only supported on Linux")

        errors: list[str] = []

        # balatro_path (required, no auto-detect)
        if config.balatro_path is None:
            errors.append(
                "Game directory is required.\n"
                "  Set via: --balatro-path or BALATROBOT_BALATRO_PATH"
            )
        else:
            balatro = Path(config.balatro_path)
            if not balatro.is_dir():
                errors.append(f"Game directory not found: {balatro}")

        # lovely_path (required, auto-detect)
        if config.lovely_path is None:
            detected = _detect_lovely_path()
            if detected:
                config.lovely_path = str(detected)
            else:
                errors.append(
                    "Lovely library is required.\n"
                    "  Set via: --lovely-path or BALATROBOT_LOVELY_PATH\n"
                    "  Expected: /usr/local/lib/liblovely.so"
                )
        if config.lovely_path:
            lovely = Path(config.lovely_path)
            if not lovely.is_file():
                errors.append(f"Lovely library not found: {lovely}")
            elif lovely.suffix != ".so":
                errors.append(f"Lovely library has wrong extension: {lovely}")

        # love_path (required, auto-detect via PATH)
        if config.love_path is None:
            detected = _detect_love_path()
            if detected:
                config.love_path = str(detected)
            else:
                errors.append(
                    "LOVE executable is required.\n"
                    "  Set via: --love-path or BALATROBOT_LOVE_PATH\n"
                    "  Or install love and ensure it's in PATH"
                )
        if config.love_path:
            love = Path(config.love_path)
            if not love.is_file():
                errors.append(f"LOVE executable not found: {love}")

        if errors:
            raise RuntimeError("Path validation failed:\n\n" + "\n\n".join(errors))

    def build_env(self, config: Config) -> dict[str, str]:
        """Build environment with LD_PRELOAD."""
        assert config.lovely_path is not None
        env = os.environ.copy()
        env["LD_PRELOAD"] = config.lovely_path
        env.update(config.to_env())
        return env

    def build_cmd(self, config: Config) -> list[str]:
        """Build native LOVE launch command."""
        assert config.love_path is not None
        assert config.balatro_path is not None
        return [config.love_path, config.balatro_path]
