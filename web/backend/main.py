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
from .framebuffer import placeholder_png
from .instances import InstanceManager
from .models import CreateInstanceRequest, InstanceSummary
from .source import parse_lst
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

@app.post("/api/instances/{instance_id}/{action}")
async def exec_action(instance_id: str, action: str):
    inst = manager.get(instance_id)
    if inst is None:
        raise HTTPException(404, "no such instance")
    try:
        if action == "continue":
            await inst.gdb.cont()
        elif action == "step":
            await inst.gdb.step()
        elif action == "interrupt":
            await inst.gdb.interrupt()
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
        return await inst.gdb.read_registers()
    except Exception as e:
        raise HTTPException(503, f"gdb: {e}")


@app.get("/api/regions")
async def get_regions():
    return regions_mod.all_regions()


@app.get("/api/registers-doc")
async def get_registers_doc():
    p = PROJECT_ROOT / "web" / "data" / "6809-registers.json"
    with p.open("r", encoding="utf-8") as f:
        return _json.load(f)


@app.get("/api/symbols/lookup")
async def lookup_symbol(addr: int):
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
        blob = await inst.gdb.read_memory(addr, length)
    except Exception as e:
        raise HTTPException(503, f"gdb: {e}")
    # Pull a fresh register snapshot to ground operand resolution.
    try:
        regs = await inst.gdb.read_registers()
    except Exception:
        regs = {}
    decoded = decoder_mod.decode(addr, blob, regs)
    return annotation_mod.annotate(decoded, regs)


@app.get("/api/source")
async def get_source():
    lst = PROJECT_ROOT / "build" / "ladybug.lst"
    if not lst.exists():
        raise HTTPException(404, "build/ladybug.lst not found — run a build first")
    return {"path": "build/ladybug.lst", "lines": parse_lst(lst)}


@app.post("/api/instances/{instance_id}/breakpoints")
async def add_breakpoint(instance_id: str, body: dict):
    inst = manager.get(instance_id)
    if inst is None:
        raise HTTPException(404, "no such instance")
    addr = body.get("addr")
    if not isinstance(addr, int):
        raise HTTPException(400, "body.addr (int) required")
    try:
        bp_id = await inst.gdb.set_breakpoint(addr)
        return {"id": bp_id, "addr": addr}
    except Exception as e:
        raise HTTPException(503, f"gdb: {e}")


@app.delete("/api/instances/{instance_id}/breakpoints/{bp_id}")
async def del_breakpoint(instance_id: str, bp_id: str):
    inst = manager.get(instance_id)
    if inst is None:
        raise HTTPException(404, "no such instance")
    try:
        await inst.gdb.clear_breakpoint(bp_id)
        return {"ok": True}
    except Exception as e:
        raise HTTPException(503, f"gdb: {e}")


@app.patch("/api/instances/{instance_id}/breakpoints/{bp_id}")
async def patch_breakpoint(instance_id: str, bp_id: str, body: dict):
    inst = manager.get(instance_id)
    if inst is None:
        raise HTTPException(404, "no such instance")
    enabled = body.get("enabled")
    if not isinstance(enabled, bool):
        raise HTTPException(400, "body.enabled (bool) required")
    try:
        if enabled:
            await inst.gdb.enable_breakpoint(bp_id)
        else:
            await inst.gdb.disable_breakpoint(bp_id)
        return {"ok": True}
    except Exception as e:
        raise HTTPException(503, f"gdb: {e}")


@app.get("/api/instances/{instance_id}/memory")
async def get_memory(instance_id: str, addr: int, length: int = 64):
    inst = manager.get(instance_id)
    if inst is None:
        raise HTTPException(404, "no such instance")
    try:
        data = await inst.gdb.read_memory(addr, length)
        return {"addr": addr, "length": length, "bytes_hex": data.hex()}
    except Exception as e:
        raise HTTPException(503, f"gdb: {e}")


@app.get("/api/instances/{instance_id}/framebuffer.png")
async def framebuffer(instance_id: str):
    inst = manager.get(instance_id)
    if inst is None:
        raise HTTPException(404, "no such instance")
    return Response(content=placeholder_png(inst.name), media_type="image/png")


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
