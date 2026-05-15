"""Parse the lwasm .lst into structured lines for the source pane.

Each .lst line is shaped like:

    "C02A 8EC000           (path):00102               ldx     #CART_BASE"

with the address in the leftmost column (blank on non-emitting lines), an
optional byte column, then `(path):lineno  source_text`. We pull out the
address (if any) and the source text — bytes are ignored for now.
"""
from __future__ import annotations
import re
from pathlib import Path


_RE_LST_LINE = re.compile(
    r"^([0-9A-Fa-f]{4,})?\s+\S*\s*\([^)]+\):(\d+)\s?(.*)$"
)


def parse_lst(path: Path) -> list:
    """Return list of dicts {addr: Optional[int], line_no: int, text: str}."""
    out: list = []
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for raw in f:
            line = raw.rstrip("\n")
            m = _RE_LST_LINE.match(line)
            if not m:
                continue
            addr_hex, line_no, text = m.group(1), m.group(2), m.group(3)
            out.append({
                "addr": int(addr_hex, 16) if addr_hex else None,
                "line_no": int(line_no),
                "text": text,
            })
    return out
