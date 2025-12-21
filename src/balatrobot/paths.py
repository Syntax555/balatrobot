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


def detect_mods_path() -> Path | None:
    """Detect Mods directory in standard location."""
    mods = Path.home() / ".config/love/Mods"
    return mods if mods.is_dir() else None


def detect_settings_path() -> Path | None:
    """Detect game settings directory in standard location."""
    settings = Path.home() / ".local/share/love/balatro"
    return settings if settings.is_dir() else None
