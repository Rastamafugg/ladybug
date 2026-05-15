"""Load and index the 6809 opcode JSON + indexed-postbyte table.

One-time load at import. Lookups return dicts straight from JSON; the decoder
is the only consumer that interprets them.
"""
from __future__ import annotations
import json
from pathlib import Path
from typing import Optional


_DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def _load_json(name):
    with (_DATA_DIR / name).open("r", encoding="utf-8") as f:
        return json.load(f)


_opcodes = _load_json("6809-opcodes.json")
_indexed_postbyte = _load_json("6809-indexed-postbyte.json")


def lookup_primary(byte):
    """Return the entry for a non-prefixed opcode byte, or None."""
    return _opcodes["primary"].get(f"{byte:02X}")


def lookup_page2(byte):
    """Return the entry for a $10-prefixed opcode's second byte, or None."""
    return _opcodes.get("page2", {}).get(f"{byte:02X}")


def lookup_page3(byte):
    """Return the entry for a $11-prefixed opcode's second byte, or None."""
    return _opcodes.get("page3", {}).get(f"{byte:02X}")


def indexed_postbyte_entries():
    """All postbyte patterns, in match order."""
    return _indexed_postbyte["entries"]


def register_codes():
    return _indexed_postbyte.get("register_codes", ["X", "Y", "U", "S"])
