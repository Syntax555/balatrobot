from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


@dataclass(frozen=True)
class VanillaContentKeys:
    jokers: frozenset[str]
    tarots: frozenset[str]
    planets: frozenset[str]
    spectrals: frozenset[str]
    vouchers: frozenset[str]

    @property
    def consumables(self) -> frozenset[str]:
        return self.tarots | self.planets | self.spectrals


_ALIAS_LINE_RE = re.compile(r"^---@alias\s+([A-Za-z0-9_.]+)\s*$")
_QUOTED_RE = re.compile(r"\"([^\"]+)\"")

_INTERESTING_ALIASES: dict[str, str] = {
    "Card.Key.Joker": "jokers",
    "Card.Key.Consumable.Tarot": "tarots",
    "Card.Key.Consumable.Planet": "planets",
    "Card.Key.Consumable.Spectral": "spectrals",
    "Card.Key.Voucher": "vouchers",
}


def _default_enums_path() -> Path:
    # src/balatro_ai/content_keys.py -> src -> lua/utils/enums.lua
    return Path(__file__).resolve().parents[1] / "lua" / "utils" / "enums.lua"


def parse_enums_lua(text: str) -> VanillaContentKeys:
    buckets: dict[str, set[str]] = {name: set() for name in _INTERESTING_ALIASES.values()}
    active_bucket: str | None = None

    for line in text.splitlines():
        alias_match = _ALIAS_LINE_RE.match(line)
        if alias_match:
            alias = alias_match.group(1)
            active_bucket = _INTERESTING_ALIASES.get(alias)
            continue

        if not active_bucket:
            continue

        if not line.lstrip().startswith("---|"):
            continue

        for key in _QUOTED_RE.findall(line):
            buckets[active_bucket].add(key)

    return VanillaContentKeys(
        jokers=frozenset(buckets["jokers"]),
        tarots=frozenset(buckets["tarots"]),
        planets=frozenset(buckets["planets"]),
        spectrals=frozenset(buckets["spectrals"]),
        vouchers=frozenset(buckets["vouchers"]),
    )


@lru_cache(maxsize=2)
def load_vanilla_content_keys(enums_path: str | Path | None = None) -> VanillaContentKeys:
    path = Path(enums_path) if enums_path is not None else _default_enums_path()
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return VanillaContentKeys(
            jokers=frozenset(),
            tarots=frozenset(),
            planets=frozenset(),
            spectrals=frozenset(),
            vouchers=frozenset(),
        )
    return parse_enums_lua(text)

