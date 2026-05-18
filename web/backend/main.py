"""FastAPI app for the Ladybug retro-dev web UI."""
from __future__ import annotations
import asyncio
import json
from pathlib import Path
from typing import List

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import Response, FileResponse
from fastapi.staticfiles import StaticFiles

from .build import run_build
from .framebuffer import placeholder_png, render as render_framebuffer
from . import gime_state as gime_state_mod
from . import palette as palette_mod
from .instances import InstanceManager
from .models import CreateInstanceRequest, InstanceSummary
from .source import parse_lst
from . import memory_map as memory_map_mod
from . import regions as regions_mod
from . import symbols as symbols_mod
from . import decoder as decoder_mod
from . import annotation as annotation_mod
from . import opcode_table  # eager-load JSON at startup
import json as _json
from pathlib import Path as _Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIR = PROJECT_ROOT / "web" / "frontend"

app = FastAPI(title="Ladybug retro-dev web")
manager = InstanceManager(PROJECT_ROOT)


# ---- instances ---------------------------------------------------------

@app.get("/api/instances", response_model=List[InstanceSummary])
async def list_instances():
    return [i.summary() for i in manager.list()]


@app.post("/api/instances", response_model=InstanceSummary)
async def create_instance(req: CreateInstanceRequest):
    inst = await manager.create(
        name=req.name, rom_path=req.rom_path, extra_flags=req.extra_flags
    )
    return inst.summary()


@app.delete("/api/instances/{instance_id}")
async def delete_instance(instance_id: str):
    if manager.get(instance_id) is None:
        raise HTTPException(404, "no such instance")
    await manager.remove(instance_id)
    return {"ok": True}


# ---- build (project-global, not per-instance) -------------------------

@app.post("/api/build")
async def build():
    result = await run_build(PROJECT_ROOT)
    return result.__dict__


# ---- per-instance execution + state (stubs) ---------------------------

@app.post("/api/instances/{instance_id}/actions/{action}")
async def exec_action(instance_id: str, action: str):
    inst = manager.get(instance_id)
    if inst is None:
        raise HTTPException(404, "no such instance")
    try:
        if action == "continue":
            await inst.session.cont()
        elif action == "step":
            await inst.session.step()
        elif action == "interrupt":
            await inst.session.interrupt()
        elif action == "reset":
            await inst.stop()
            await inst.start()
        else:
            raise HTTPException(400, f"unknown action: {action}")
    except Exception as e:
        return {"ok": False, "error": str(e)}
    return {"ok": True}


@app.get("/api/instances/{instance_id}/registers")
async def get_registers(instance_id: str):
    inst = manager.get(instance_id)
    if inst is None:
        raise HTTPException(404, "no such instance")
    try:
        return await inst.session.read_registers()
    except Exception as e:
        raise HTTPException(503, f"monitor: {e}")


@app.get("/api/regions")
async def get_regions():
    """Static hardware-region map (PIA, GIME, palette, etc).

    Distinct from the user-defined region CRUD under
    /api/instances/{id}/regions. Kept at this URL for frontend back-compat
    with store.regionFor(addr).
    """
    return memory_map_mod.all_regions()


# ---- user-defined regions (per-config persistence) ---------------------

def _config_id_for(instance_id: str) -> tuple:
    inst = manager.get(instance_id)
    if inst is None:
        raise HTTPException(404, "no such instance")
    return inst, regions_mod.config_id_for_rom(inst.rom_path)


@app.get("/api/instances/{instance_id}/regions")
async def list_user_regions(instance_id: str):
    _, cid = _config_id_for(instance_id)
    return [r.to_dict() for r in regions_mod.list_regions(cid)]


@app.post("/api/instances/{instance_id}/regions")
async def add_user_region(instance_id: str, body: dict):
    _, cid = _config_id_for(instance_id)
    try:
        r = regions_mod.add_region(cid, body)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return r.to_dict()


@app.patch("/api/instances/{instance_id}/regions/{region_id}")
async def patch_user_region(instance_id: str, region_id: str, body: dict):
    _, cid = _config_id_for(instance_id)
    try:
        r = regions_mod.update_region(cid, region_id, body)
    except KeyError:
        raise HTTPException(404, "no such region")
    except ValueError as e:
        raise HTTPException(400, str(e))
    return r.to_dict()


@app.delete("/api/instances/{instance_id}/regions/{region_id}")
async def delete_user_region(instance_id: str, region_id: str):
    _, cid = _config_id_for(instance_id)
    try:
        regions_mod.delete_region(cid, region_id)
    except KeyError:
        raise HTTPException(404, "no such region")
    return {"ok": True}


@app.post("/api/instances/{instance_id}/regions/values")
async def read_user_region_values(instance_id: str, body: dict):
    """Resolve + read the regions whose ids appear in body.visible_ids.

    Empty visible_ids → empty result. The frontend calls this on ws:halt
    with the currently-expanded region ids; collapsed regions don't fetch.
    """
    inst, cid = _config_id_for(instance_id)
    visible = body.get("visible_ids") or []
    if not isinstance(visible, list):
        raise HTTPException(400, "body.visible_ids must be a list of region ids")
    all_defs = regions_mod.list_regions(cid)
    want = [r for r in all_defs if r.id in set(visible)]
    if not want:
        return []
    map_path = symbols_mod.map_path_for_rom(inst.rom_path)
    try:
        results = await regions_mod.read_values(want, inst.session, map_path)
    except Exception as e:
        raise HTTPException(503, f"monitor: {e}")
    return [
        {
            "id": r.id, "name": r.name, "kind": r.kind, "length": r.length,
            "base": r.base, "bytes_hex": r.bytes_hex, "error": r.error,
        }
        for r in results
    ]


@app.get("/api/roms")
async def list_roms():
    """Auto-discover build/*.rom for the instance-creation picker."""
    build_dir = PROJECT_ROOT / "build"
    if not build_dir.is_dir():
        return []
    roms = sorted(
        f.relative_to(PROJECT_ROOT).as_posix()
        for f in build_dir.glob("*.rom")
    )
    return roms


@app.get("/api/registers-doc")
async def get_registers_doc():
    p = PROJECT_ROOT / "web" / "data" / "6809-registers.json"
    with p.open("r", encoding="utf-8") as f:
        return _json.load(f)


@app.get("/api/symbols/lookup/{instance_id}")
async def lookup_symbol(instance_id: str, addr: int):
    inst = manager.get(instance_id)
    if inst is None:
        raise HTTPException(404, "no such instance")
    result = symbols_mod.lookup(addr, symbols_mod.map_path_for_rom(inst.rom_path))
    if result is None:
        raise HTTPException(404, "no symbol at or before that address")
    return result


# Back-compat: legacy path served from the default (Ladybug) build.
@app.get("/api/symbols/lookup")
async def lookup_symbol_legacy(addr: int):
    result = symbols_mod.lookup(addr)
    if result is None:
        raise HTTPException(404, "no symbol at or before that address")
    return result


@app.get("/api/decode/{instance_id}")
async def decode_at(instance_id: str, addr: int, length: int = 4):
    inst = manager.get(instance_id)
    if inst is None:
        raise HTTPException(404, "no such instance")
    if length < 1 or length > 8:
        raise HTTPException(400, "length must be 1..8")
    try:
        blob = await inst.session.read_memory(addr, length)
    except Exception as e:
        raise HTTPException(503, f"monitor: {e}")
    # Pull a fresh register snapshot to ground operand resolution.
    try:
        regs = await inst.session.read_registers()
    except Exception:
        regs = {}
    decoded = decoder_mod.decode(addr, blob, regs)
    return annotation_mod.annotate(decoded, regs)


def _lst_path_for_rom(rom_path: str) -> Path:
    from pathlib import Path as _P
    return PROJECT_ROOT / _P(rom_path).with_suffix(".lst")


@app.get("/api/source/{instance_id}")
async def get_source_for(instance_id: str):
    inst = manager.get(instance_id)
    if inst is None:
        raise HTTPException(404, "no such instance")
    lst = _lst_path_for_rom(inst.rom_path)
    rel = lst.relative_to(PROJECT_ROOT).as_posix()
    if not lst.exists():
        raise HTTPException(404, f"{rel} not found — run a build first")
    return {"path": rel, "lines": parse_lst(lst)}


# Back-compat: legacy path always serves the default (Ladybug) listing.
@app.get("/api/source")
async def get_source_legacy():
    lst = PROJECT_ROOT / "build" / "ladybug.lst"
    if not lst.exists():
        raise HTTPException(404, "build/ladybug.lst not found — run a build first")
    return {"path": "build/ladybug.lst", "lines": parse_lst(lst)}


async def _with_paused(session, coro_factory):
    """Auto-pause / op / resume helper for halted-only monitor calls.

    Monitor protocol enforces halted-only for breakpoint mutations and
    register writes. The UI commonly invokes those while the CPU is
    running (clicking source rows mid-execution). This wrapper takes a
    transient pause so the user-visible behavior is "click always works".

    The pause + resume go through session.interrupt() / session.cont()
    which emit running/stopped events as a side effect. Callers see a
    brief flicker on the UI but no error.
    """
    run_state = "halted"
    try:
        st = await session.get_run_state()
        run_state = st.get("state", "halted")
    except Exception:
        pass

    if run_state == "running":
        await session.interrupt()
    try:
        return await coro_factory()
    finally:
        if run_state == "running":
            try:
                await session.cont()
            except Exception:
                pass


@app.post("/api/instances/{instance_id}/breakpoints")
async def add_breakpoint(instance_id: str, body: dict):
    inst = manager.get(instance_id)
    if inst is None:
        raise HTTPException(404, "no such instance")
    addr = body.get("addr")
    if not isinstance(addr, int):
        raise HTTPException(400, "body.addr (int) required")
    try:
        bp_id = await _with_paused(inst.session, lambda: inst.session.set_breakpoint(addr))
        return {"id": bp_id, "addr": addr}
    except Exception as e:
        raise HTTPException(503, f"monitor: {e}")


@app.delete("/api/instances/{instance_id}/breakpoints/{bp_id}")
async def del_breakpoint(instance_id: str, bp_id: str):
    inst = manager.get(instance_id)
    if inst is None:
        raise HTTPException(404, "no such instance")
    try:
        await _with_paused(inst.session, lambda: inst.session.clear_breakpoint(bp_id))
        return {"ok": True}
    except Exception as e:
        raise HTTPException(503, f"monitor: {e}")


@app.patch("/api/instances/{instance_id}/breakpoints/{bp_id}")
async def patch_breakpoint(instance_id: str, bp_id: str, body: dict):
    inst = manager.get(instance_id)
    if inst is None:
        raise HTTPException(404, "no such instance")
    # Monitor protocol v0.6 has no per-BP enable/disable; the toggle is
    # deferred. Frontend should hide the control until this returns 200.
    raise HTTPException(501, "breakpoint enable/disable not supported by monitor protocol")


@app.get("/api/instances/{instance_id}/memory")
async def get_memory(instance_id: str, addr: int, length: int = 64):
    inst = manager.get(instance_id)
    if inst is None:
        raise HTTPException(404, "no such instance")
    try:
        data = await inst.session.read_memory(addr, length)
        return {"addr": addr, "length": length, "bytes_hex": data.hex()}
    except Exception as e:
        raise HTTPException(503, f"monitor: {e}")


@app.get("/api/instances/{instance_id}/palette")
async def get_palette(instance_id: str):
    inst = manager.get(instance_id)
    if inst is None:
        raise HTTPException(404, "no such instance")
    try:
        raw = await inst.session.read_memory(palette_mod.PALETTE_BASE, palette_mod.PALETTE_LEN)
    except Exception as e:
        raise HTTPException(503, f"monitor: {e}")
    return palette_mod.decode_all(raw)


@app.get("/api/instances/{instance_id}/framebuffer.png")
async def framebuffer(instance_id: str):
    inst = manager.get(instance_id)
    if inst is None:
        raise HTTPException(404, "no such instance")
    try:
        state = await gime_state_mod.snapshot(inst.session)
    except Exception as e:
        return Response(
            content=placeholder_png(f"gime_state failed: {e}"),
            media_type="image/png",
        )
    if not gime_state_mod.is_supported(state.mode):
        return Response(
            content=render_framebuffer(state, b""),  # render() emits the unsupported placeholder
            media_type="image/png",
        )
    fb_len = state.mode.bytes_per_row * state.mode.height
    try:
        fb = await inst.session.read_memory(
            state.fb_phys_base, fb_len, space="physical"
        )
    except Exception as e:
        return Response(
            content=placeholder_png(f"FB read failed: {e}"),
            media_type="image/png",
        )
    return Response(
        content=render_framebuffer(state, fb),
        media_type="image/png",
    )


# ---- websocket --------------------------------------------------------

@app.websocket("/ws/instances/{instance_id}")
async def ws_instance(ws: WebSocket, instance_id: str):
    inst = manager.get(instance_id)
    if inst is None:
        await ws.close(code=4404)
        return
    await ws.accept()
    q = inst.subscribe()
    try:
        # Send current state as the first event so clients sync without RTT.
        await ws.send_text(json.dumps({
            "kind": "state",
            "instance_id": inst.id,
            "payload": {"state": inst.state.value},
        }))
        while True:
            ev = await q.get()
            await ws.send_text(ev.model_dump_json())
    except WebSocketDisconnect:
        pass
    finally:
        inst.unsubscribe(q)


# ---- static frontend --------------------------------------------------

@app.get("/")
async def index():
    return FileResponse(FRONTEND_DIR / "index.html")


app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")
