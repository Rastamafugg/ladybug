"""Memory-region map. Loads web/data/6809-regions.json once and serves
address-keyed lookups.
"""
from __future__ import annotations
import json
from pathlib import Path
from typing import Optional


_DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def _load():
    with (_DATA_DIR / "6809-regions.json").open("r", encoding="utf-8") as f:
        raw = json.load(f)
    out = []
    for r in raw:
        out.append({
            "lo": int(r["lo"], 0),
            "hi": int(r["hi"], 0),
            "name": r["name"],
            "kind": r.get("kind"),
            "summary": r.get("summary", ""),
            "wiki": r.get("wiki"),
        })
    # Sort by lo so binary-search-style scans are well-defined.
    out.sort(key=lambda r: r["lo"])
    return out


_regions = _load()


def all_regions():
    return _regions


def lookup(addr: int) -> Optional[dict]:
    # Linear scan — 18 entries; trivially cheap.
    for r in _regions:
        if r["lo"] <= addr <= r["hi"]:
            return r
    return None
