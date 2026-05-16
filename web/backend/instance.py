"""One managed XRoar instance: process + GDB session + WS subscribers."""
from __future__ import annotations
import asyncio
import socket
import uuid
from pathlib import Path
from typing import Optional

from .gdb_session import GdbSession, GdbError
from .models import InstanceState, InstanceSummary, WsEvent


XROAR_BIN = "/usr/local/bin/xroar"


class Instance:
    def __init__(
        self,
        name: str,
        rom_path: str,
        gdb_port: int,
        project_root: Path,
        extra_flags: Optional[list] = None,
    ):
        self.id = uuid.uuid4().hex[:8]
        self.name = name
        self.rom_path = rom_path
        self.gdb_port = gdb_port
        self.project_root = project_root
        self.extra_flags = list(extra_flags or [])
        self.state = InstanceState.CREATING
        self.pc: Optional[int] = None
        self.gdb = GdbSession(
            gdb_port,
            on_async=self._on_gdb_async,
            on_log=self._on_gdb_log,
        )
        self._proc: Optional[asyncio.subprocess.Process] = None
        self._xroar_log_task: Optional[asyncio.Task] = None
        self._subscribers: set = set()

    # ---- lifecycle ----------------------------------------------------

    def launch_cmd(self):
        return [
            XROAR_BIN,
            "-machine", "coco3",
            "-ram", "512",
            "-cart", "ladybug",
            "-cart-type", "rom",
            "-cart-rom", str(self.project_root / self.rom_path),
            "-cart-autorun",
            "-tv-input", "rgb",
            "-gdb",
            "-gdb-ip", "127.0.0.1",
            "-gdb-port", str(self.gdb_port),
            *self.extra_flags,
        ]

    async def start(self) -> None:
        await self._set_state(InstanceState.LAUNCHING)
        try:
            self._proc = await asyncio.create_subprocess_exec(
                *self.launch_cmd(),
                cwd=str(self.project_root),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                stdin=asyncio.subprocess.DEVNULL,
            )
        except FileNotFoundError as e:
            await self._emit("log", {"text": f"xroar launch failed: {e}"})
            await self._set_state(InstanceState.CRASHED)
            return

        self._xroar_log_task = asyncio.create_task(self._pump_xroar_log())

        # XRoar's gdb stub gets confused if we probe-connect then disconnect
        # before the real attach — give it a few seconds to come up and avoid
        # any TCP probing.
        await asyncio.sleep(4.0)

        await self._set_state(InstanceState.ATTACHING)
        try:
            await self.gdb.attach()
        except (GdbError, asyncio.TimeoutError) as e:
            await self._emit("log", {"text": f"gdb attach failed: {e}"})
            await self.stop()
            await self._set_state(InstanceState.CRASHED)
            return

        # The *stopped event from gdb already drove us into HALTED via
        # `_on_gdb_async` and emitted a halt event with registers — don't
        # double-fire it here.

    async def stop(self) -> None:
        if self.state in (InstanceState.STOPPED, InstanceState.STOPPING):
            return
        await self._set_state(InstanceState.STOPPING)
        try:
            await self.gdb.detach()
        except Exception:
            pass
        if self._proc and self._proc.returncode is None:
            self._proc.terminate()
            try:
                await asyncio.wait_for(self._proc.wait(), timeout=3.0)
            except asyncio.TimeoutError:
                self._proc.kill()
        if self._xroar_log_task:
            self._xroar_log_task.cancel()
            try:
                await self._xroar_log_task
            except Exception:
                pass
        self._proc = None
        await self._set_state(InstanceState.STOPPED)

    # ---- gdb callbacks ----------------------------------------------

    async def _on_gdb_async(self, cls: str, info: dict) -> None:
        if cls == "stopped":
            self.pc = info.get("pc")
            await self._set_state(InstanceState.HALTED)
            # IMPORTANT: this callback runs inside the gdb reader loop.
            # Reading registers issues another MI command whose ^done can
            # only be dispatched by the very same reader — deadlock. So
            # schedule the regs refresh as an independent task.
            asyncio.create_task(self._refresh_regs())
        elif cls == "running":
            await self._set_state(InstanceState.RUNNING)

    async def _on_gdb_log(self, text: str) -> None:
        await self._emit("log", {"text": text})

    async def _safe_regs(self) -> dict:
        try:
            return await self.gdb.read_registers()
        except Exception as e:
            return {"_error": str(e)}

    async def _refresh_regs(self) -> None:
        regs = await self._safe_regs()
        self.pc = regs.get("pc")
        await self._emit("halt", {"pc": self.pc, "registers": regs})

    # ---- xroar stdout pump -------------------------------------------

    async def _pump_xroar_log(self) -> None:
        assert self._proc and self._proc.stdout
        while True:
            line = await self._proc.stdout.readline()
            if not line:
                if self._proc.returncode is not None and self.state not in (
                    InstanceState.STOPPING, InstanceState.STOPPED, InstanceState.CRASHED
                ):
                    await self._set_state(InstanceState.CRASHED)
                return
            await self._emit("log", {"text": "[xroar] " + line.decode("utf-8", "replace").rstrip()})

    # ---- subscribers / events ----------------------------------------

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=256)
        self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subscribers.discard(q)

    async def _emit(self, kind: str, payload: dict) -> None:
        ev = WsEvent(kind=kind, instance_id=self.id, payload=payload)
        for q in list(self._subscribers):
            try:
                q.put_nowait(ev)
            except asyncio.QueueFull:
                try:
                    q.get_nowait()
                    q.put_nowait(ev)
                except Exception:
                    pass

    async def _set_state(self, state: InstanceState) -> None:
        self.state = state
        await self._emit("state", {"state": state.value})

    def summary(self) -> InstanceSummary:
        return InstanceSummary(
            id=self.id,
            name=self.name,
            state=self.state,
            gdb_port=self.gdb_port,
            rom_path=self.rom_path,
            pc=self.pc,
        )


async def _wait_for_port(host: str, port: int, timeout: float) -> bool:
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        try:
            r, w = await asyncio.open_connection(host, port)
            w.close()
            try:
                await w.wait_closed()
            except Exception:
                pass
            return True
        except (ConnectionRefusedError, OSError):
            await asyncio.sleep(0.1)
    return False
