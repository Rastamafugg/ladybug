from __future__ import annotations
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class InstanceState(str, Enum):
    CREATING = "creating"
    LAUNCHING = "launching"
    ATTACHING = "attaching"
    RUNNING = "running"
    HALTED = "halted"
    STOPPING = "stopping"
    STOPPED = "stopped"
    CRASHED = "crashed"


class CreateInstanceRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    rom_path: str = "build/ladybug.rom"
    extra_flags: list[str] = Field(default_factory=list)


class InstanceSummary(BaseModel):
    id: str
    name: str
    state: InstanceState
    gdb_port: int
    rom_path: str
    pc: Optional[int] = None


class Registers(BaseModel):
    a: int; b: int; x: int; y: int
    u: int; s: int; pc: int
    dp: int; cc: int


class MemoryRead(BaseModel):
    addr: int
    length: int
    bytes_hex: str


class Breakpoint(BaseModel):
    id: str
    addr: int
    symbol: Optional[str] = None
    enabled: bool = True


class WsEvent(BaseModel):
    """Envelope for events fanned out to WS subscribers."""
    kind: str  # "state" | "halt" | "log" | "build" | "bp"
    instance_id: str
    payload: dict
