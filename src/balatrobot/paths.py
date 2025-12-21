"""Path utilities for BalatroBot launcher."""

import shutil
from pathlib import Path


def detect_love_path() -> Path | None:
    """Detect LOVE executable in PATH."""
    found = shutil.which("love")
    return Path(found) if found else None


def detect_lovely_path() -> Path | None:
    """Detect liblovely.so in standard locations."""
    candidates = [
        Path("/usr/local/lib/liblovely.so"),
        Path.home() / ".local/lib/liblovely.so",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None
