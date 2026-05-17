"""InstanceManager: tracks all live XRoar instances and the monitor port pool."""
from __future__ import annotations
from pathlib import Path
from typing import Optional

from .instance import Instance


MONITOR_PORT_BASE = 65520
MONITOR_PORT_LIMIT = 65540  # exclusive


class InstanceManager:
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self._instances: dict[str, Instance] = {}

    # ---- port pool ---------------------------------------------------

    def _allocate_port(self) -> int:
        used = {i.monitor_port for i in self._instances.values()}
        for p in range(MONITOR_PORT_BASE, MONITOR_PORT_LIMIT):
            if p not in used:
                return p
        raise RuntimeError(
            f"monitor port pool exhausted ({MONITOR_PORT_LIMIT - MONITOR_PORT_BASE} instances)"
        )

    # ---- CRUD --------------------------------------------------------

    def list(self) -> list[Instance]:
        return list(self._instances.values())

    def get(self, instance_id: str) -> Optional[Instance]:
        return self._instances.get(instance_id)

    async def create(
        self,
        name: str,
        rom_path: str,
        extra_flags: Optional[list] = None,
    ) -> Instance:
        import asyncio
        port = self._allocate_port()
        inst = Instance(
            name=name,
            rom_path=rom_path,
            monitor_port=port,
            project_root=self.project_root,
            extra_flags=extra_flags,
        )
        self._instances[inst.id] = inst
        # Kick off start() in the background so the HTTP POST returns fast.
        # The UI watches state transitions via WS.
        asyncio.create_task(inst.start())
        return inst

    async def remove(self, instance_id: str) -> None:
        inst = self._instances.pop(instance_id, None)
        if inst is not None:
            await inst.stop()
