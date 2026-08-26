"""Parse lwasm map symbols."""

from __future__ import annotations

import re
from pathlib import Path

from .model import Symbol


MAP_SYMBOL_RE = re.compile(r"^Symbol:\s+(\S+)\s+.*\s=\s([0-9A-Fa-f]+)$")


class MapParseError(ValueError):
    """Raised when a map has no usable symbols or conflicting definitions."""


def parse_map(path: Path, module: str) -> tuple[Symbol, ...]:
    symbols: dict[str, int] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = MAP_SYMBOL_RE.match(line)
        if not match:
            continue
        name, value_text = match.groups()
        value = int(value_text, 16)
        if name in symbols and symbols[name] != value:
            raise MapParseError(f"conflicting map values for {name} in {path}")
        symbols[name] = value
    if not symbols:
        raise MapParseError(f"no symbols found in {path}")
    return tuple(
        Symbol(module=module, name=name, assembled_address=value)
        for name, value in sorted(symbols.items())
    )
