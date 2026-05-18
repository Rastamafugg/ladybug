"""User-defined memory regions: CRUD, JSON persistence, halt-time resolution.

Distinct from web/backend/memory_map.py, which serves the static hardware
register map ($FF00 PIA, $FFB0 palette, etc). This module owns the
dynamic per-config region definitions the user creates in the UI.

Persistence: web/configs/<config_id>.json, where config_id is the
filename stem of the instance's rom_path. All instances launched against
the same ROM share a region set.

Three definition kinds:

  * fixed:    base = addr
  * symbol:   base = symbol_addr + offset  (re-resolved from build/<stem>.map
              on every read — so a rebuild is picked up automatically)
  * pointer:  base = u16 BE word at ptr_addr  (re-resolved every halt)

Reads honor the 32 KB-per-region cap; MonitorSession.read_memory already
chunks at the 64 KB monitor limit.
"""
from __future__ import annotations
import json
import os
import tempfile
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable, Optional

from . import symbols as symbols_mod
from .monitor_session import MonitorError, MonitorSession


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIGS_DIR = PROJECT_ROOT / "web" / "configs"
CONFIG_SCHEMA_VERSION = 1

MAX_REGION_LENGTH = 32 * 1024     # 32 KB cap per architect pass
MAX_NAME_LENGTH = 64

VALID_KINDS = ("fixed", "symbol", "pointer")


# ---- types --------------------------------------------------------------

@dataclass
class RegionDef:
    id: str
    name: str
    kind: str                           # "fixed" | "symbol" | "pointer"
    length: int
    # kind-specific (exactly one set populated):
    addr: Optional[int] = None          # fixed
    symbol: Optional[str] = None        # symbol
    offset: int = 0                     # symbol
    ptr_addr: Optional[int] = None      # pointer

    def to_dict(self) -> dict:
        d = asdict(self)
        return {k: v for k, v in d.items() if v is not None or k in ("offset",)}


@dataclass
class RegionResolution:
    id: str
    name: str
    kind: str
    length: int
    base: Optional[int] = None
    bytes_hex: Optional[str] = None
    error: Optional[str] = None


# ---- config-id derivation + persistence --------------------------------

def config_id_for_rom(rom_path: str) -> str:
    """`build/tester.rom` -> `tester`. Filesystem-safe stem."""
    stem = Path(rom_path).stem or "default"
    # Belt-and-braces: strip anything that isn't filesystem-safe.
    return "".join(c if (c.isalnum() or c in "-_") else "_" for c in stem)


def _config_path(config_id: str) -> Path:
    return CONFIGS_DIR / f"{config_id}.json"


def _ensure_dir() -> None:
    CONFIGS_DIR.mkdir(parents=True, exist_ok=True)


def load_config(config_id: str) -> list[RegionDef]:
    p = _config_path(config_id)
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    out: list[RegionDef] = []
    for r in data.get("regions", []):
        try:
            out.append(RegionDef(
                id=str(r["id"]),
                name=str(r["name"]),
                kind=str(r["kind"]),
                length=int(r["length"]),
                addr=r.get("addr"),
                symbol=r.get("symbol"),
                offset=int(r.get("offset", 0)),
                ptr_addr=r.get("ptr_addr"),
            ))
        except (KeyError, TypeError, ValueError):
            continue  # skip malformed entries silently — UI will show absence
    return out


def save_config(config_id: str, defs: list[RegionDef]) -> None:
    """Atomic write via temp file + os.replace."""
    _ensure_dir()
    p = _config_path(config_id)
    payload = {
        "version": CONFIG_SCHEMA_VERSION,
        "config_id": config_id,
        "regions": [r.to_dict() for r in defs],
    }
    # Write to a temp file in the same directory so os.replace is atomic.
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=str(CONFIGS_DIR),
        prefix=f".{config_id}.", suffix=".tmp", delete=False,
    ) as tf:
        json.dump(payload, tf, indent=2)
        tf.flush()
        os.fsync(tf.fileno())
        tmpname = tf.name
    os.replace(tmpname, p)


# ---- validation --------------------------------------------------------

def _validate_addr_u16(name: str, val) -> int:
    if not isinstance(val, int) or not (0 <= val <= 0xFFFF):
        raise ValueError(f"{name}: must be int in 0..65535")
    return val


def _validate_length(val) -> int:
    if not isinstance(val, int) or not (1 <= val <= MAX_REGION_LENGTH):
        raise ValueError(f"length: must be int in 1..{MAX_REGION_LENGTH}")
    return val


def _validate_name(val) -> str:
    if not isinstance(val, str) or not val.strip():
        raise ValueError("name: must be a non-empty string")
    if len(val) > MAX_NAME_LENGTH:
        raise ValueError(f"name: max {MAX_NAME_LENGTH} chars")
    return val.strip()


def _build_def(body: dict, existing_id: Optional[str] = None) -> RegionDef:
    """Apply validation. Raises ValueError on bad input."""
    kind = body.get("kind")
    if kind not in VALID_KINDS:
        raise ValueError(f"kind: must be one of {VALID_KINDS}")
    name = _validate_name(body.get("name"))
    length = _validate_length(body.get("length"))

    rdef = RegionDef(
        id=existing_id or uuid.uuid4().hex[:8],
        name=name, kind=kind, length=length,
    )
    if kind == "fixed":
        rdef.addr = _validate_addr_u16("addr", body.get("addr"))
    elif kind == "symbol":
        sym = body.get("symbol")
        if not isinstance(sym, str) or not sym.strip():
            raise ValueError("symbol: required and non-empty for kind='symbol'")
        rdef.symbol = sym.strip()
        rdef.offset = int(body.get("offset", 0))
    elif kind == "pointer":
        # ptr_addr 0..0xFFFE so the 2-byte read doesn't run off the end.
        pa = body.get("ptr_addr")
        if not isinstance(pa, int) or not (0 <= pa <= 0xFFFE):
            raise ValueError("ptr_addr: must be int in 0..65534 for kind='pointer'")
        rdef.ptr_addr = pa
    return rdef


def _apply_patch(rdef: RegionDef, body: dict) -> RegionDef:
    """Build a new RegionDef merging body fields onto rdef. Kind is immutable
    in v1 — to change kind, delete and re-add."""
    merged: dict = rdef.to_dict()
    # kind stays put.
    if "kind" in body and body["kind"] != rdef.kind:
        raise ValueError("kind is immutable; delete and re-add to change kind")
    for k in ("name", "length", "addr", "symbol", "offset", "ptr_addr"):
        if k in body:
            merged[k] = body[k]
    merged["kind"] = rdef.kind
    return _build_def(merged, existing_id=rdef.id)


# ---- CRUD --------------------------------------------------------------

def list_regions(config_id: str) -> list[RegionDef]:
    return load_config(config_id)


def add_region(config_id: str, body: dict) -> RegionDef:
    rdef = _build_def(body)
    defs = load_config(config_id)
    defs.append(rdef)
    save_config(config_id, defs)
    return rdef


def update_region(config_id: str, region_id: str, body: dict) -> RegionDef:
    defs = load_config(config_id)
    for i, r in enumerate(defs):
        if r.id == region_id:
            updated = _apply_patch(r, body)
            defs[i] = updated
            save_config(config_id, defs)
            return updated
    raise KeyError(region_id)


def delete_region(config_id: str, region_id: str) -> None:
    defs = load_config(config_id)
    out = [r for r in defs if r.id != region_id]
    if len(out) == len(defs):
        raise KeyError(region_id)
    save_config(config_id, out)


# ---- resolution + read -------------------------------------------------

async def _resolve_base(
    rdef: RegionDef,
    session: MonitorSession,
    map_path: Path,
) -> RegionResolution:
    res = RegionResolution(id=rdef.id, name=rdef.name, kind=rdef.kind,
                           length=rdef.length)
    if rdef.kind == "fixed":
        res.base = rdef.addr
        return res

    if rdef.kind == "symbol":
        # Use the existing parse_map (cheap; re-reads on every call so
        # rebuilds are picked up without any explicit hook).
        syms = symbols_mod._parse_map(map_path)
        if not syms:
            res.error = f"map file missing or empty: {map_path.name}"
            return res
        for addr, name in syms:
            if name == rdef.symbol:
                res.base = (addr + (rdef.offset or 0)) & 0xFFFF
                return res
        res.error = f"symbol '{rdef.symbol}' not found in {map_path.name}"
        return res

    if rdef.kind == "pointer":
        try:
            buf = await session.read_memory(rdef.ptr_addr, 2, space="cpu")
        except MonitorError as e:
            res.error = f"read_memory failed: {e}"
            return res
        if len(buf) < 2:
            res.error = f"short read at ${rdef.ptr_addr:04X}"
            return res
        res.base = (buf[0] << 8) | buf[1]  # big-endian (6809 convention)
        return res

    res.error = f"unknown kind: {rdef.kind}"
    return res


async def read_values(
    rdefs: Iterable[RegionDef],
    session: MonitorSession,
    map_path: Path,
) -> list[RegionResolution]:
    out: list[RegionResolution] = []
    for rdef in rdefs:
        res = await _resolve_base(rdef, session, map_path)
        if res.base is not None and res.error is None:
            try:
                data = await session.read_memory(res.base, rdef.length, space="cpu")
                res.bytes_hex = data.hex()
            except MonitorError as e:
                res.error = f"read_memory failed at ${res.base:04X}: {e}"
        out.append(res)
    return out
