"""Wraps scripts/build.sh."""
from __future__ import annotations
import asyncio
from pathlib import Path
from dataclasses import dataclass


@dataclass
class BuildResult:
    ok: bool
    stdout: str
    stderr: str
    rom_size: int | None


async def run_build(project_root: Path) -> BuildResult:
    script = project_root / "scripts" / "build.sh"
    proc = await asyncio.create_subprocess_exec(
        "bash", str(script), "build",
        cwd=str(project_root),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out, err = await proc.communicate()
    rom = project_root / "build" / "ladybug.rom"
    return BuildResult(
        ok=proc.returncode == 0,
        stdout=out.decode("utf-8", errors="replace"),
        stderr=err.decode("utf-8", errors="replace"),
        rom_size=rom.stat().st_size if rom.exists() else None,
    )
