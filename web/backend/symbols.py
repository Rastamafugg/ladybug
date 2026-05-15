"""Symbol resolution. Parses build/ladybug.map (lwasm format) for addr → symbol;
merges with web/data/symbols.json for symbol → wiki anchor.

The map file is small and re-read on each request — cheap, and reflects fresh
builds without a backend restart.
"""
from __future__ import annotations
import json
import re
from pathlib import Path
from typing import Optional


PROJECT_ROOT = Path(__file__).resolve().parents[2]
_DATA_DIR = PROJECT_ROOT / "web" / "data"

_RE_MAP_LINE = re.compile(r"^Symbol:\s+(\S+)\s+\([^)]+\)\s*=\s*([0-9A-Fa-f]+)\s*$")


def _load_wiki_map():
    p = _DATA_DIR / "symbols.json"
    if not p.exists():
        return {}
    with p.open("r", encoding="utf-8") as f:
        return json.load(f).get("symbols", {})


_wiki_map = _load_wiki_map()


def _parse_map(path: Path) -> list:
    """Return a list of (addr, name) sorted by addr."""
    if not path.exists():
        return []
    out = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            m = _RE_MAP_LINE.match(line.rstrip("\n"))
            if not m:
                continue
            name, hexv = m.group(1), m.group(2)
            try:
                addr = int(hexv, 16)
            except ValueError:
                continue
            out.append((addr, name))
    out.sort()
    return out


def lookup(addr: int) -> Optional[dict]:
    """Return the nearest symbol at or before addr, with its wiki entry if any.

    Confines its search to the cart-window range to avoid matching tiny EQU
    constants that happen to be ≤ addr.
    """
    syms = _parse_map(PROJECT_ROOT / "build" / "ladybug.map")
    if not syms:
        return None
    # Prefer code-range symbols (>= $C000) when addr is in cart code; otherwise
    # match any.
    candidates = [s for s in syms if s[0] <= addr]
    if not candidates:
        return None
    if addr >= 0xC000:
        cand = [s for s in candidates if s[0] >= 0xC000]
        if cand:
            candidates = cand
    nearest_addr, name = candidates[-1]
    wiki = _wiki_map.get(name, {})
    return {
        "addr": nearest_addr,
        "offset": addr - nearest_addr,
        "name": name,
        "wiki": wiki.get("wiki"),
        "summary": wiki.get("summary"),
    }
