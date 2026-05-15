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
