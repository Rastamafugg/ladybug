"""MCP server that exposes GDB debugging as tools.

Clients should use these tools to debug and understand program behavior through gdb/rr.
This is critical for understanding crashes, memory issues, execution flow, and state mutations.
Time-travel debugging with rr is especially recommended for non-deterministic bugs.

Run directly:  python server.py
Or via MCP CLI: mcp run server.py

Each tool takes a session_id (returned by start_session) plus command-specific
parameters.  Use exec_command for anything not covered by the named tools.

Note the server may be upgraded via: uv tool upgrade gdb-mcp
"""

import asyncio
import re
from contextlib import asynccontextmanager

from mcp.server.fastmcp import FastMCP

from gdb import GdbError, GdbManager, OwnedSessionSnapshot

# Matches: rr: Saving execution to trace directory `/path/to/trace'.
_RR_TRACE_RE = re.compile(r"Saving execution to trace directory `([^']+)'")

manager = GdbManager()


@asynccontextmanager
async def _lifespan(app):
    yield
    await manager.close_all()


mcp = FastMCP("gdb-mcp", lifespan=_lifespan)


# ── Session management ────────────────────────────────────────────────────────

@mcp.tool()
async def start_session(
    binary: str | None = None,
    args: list[str] | None = None,
    cwd: str | None = None,
) -> dict:
    """Start a new GDB session. Returns session_id for all other tools.

    binary: path to executable
    args: command-line arguments for the inferior
    cwd: working directory for GDB
    """
    s = await manager.create(binary=binary, args=args, cwd=cwd)
    return {"session_id": s.id, "binary": binary}


@mcp.tool()
async def start_owned_session(
    owner_id: str,
    binary: str | None = None,
    args: list[str] | None = None,
    cwd: str | None = None,
    *,
    budget_ms: int,
) -> OwnedSessionSnapshot:
    """Start or observe a session bound to a caller-known owner token."""
    return await manager.start_owned_session(
        owner_id, binary=binary, args=args, cwd=cwd, budget_ms=budget_ms
    )


@mcp.tool()
async def stop_session_by_owner(
    owner_id: str, *, budget_ms: int
) -> OwnedSessionSnapshot:
    """Stop an owned session, or tombstone its token before a delayed start."""
    return await manager.stop_session_by_owner(owner_id, budget_ms=budget_ms)


@mcp.tool()
async def stop_session(session_id: str) -> dict:
    """Stop and clean up a GDB session (kills the GDB process)."""
    removed = await manager.remove(session_id)
    return {"stopped": removed}


# ── rr record / replay ────────────────────────────────────────────────────────

@mcp.tool()
async def rr_record(
    binary: str,
    args: list[str] | None = None,
    cwd: str | None = None,
    timeout: float = 300.0,
) -> dict:
    """Record a program execution with rr for time-travel debugging.

    Returns trace_dir for start_replay_session. Crashes/non-zero exits are
    recorded normally. Stdin is unavailable during recording.

    binary: path to executable
    args: command-line arguments
    cwd: working directory
    timeout: max seconds to wait (default 300)
    """
    cmd = ["rr", "record", binary]
    if args:
        cmd.extend(args)

    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,   # capture rr's "Saving to..." message
            cwd=cwd,
        )
        try:
            stdout_bytes, _ = await asyncio.wait_for(
                process.communicate(), timeout=timeout
            )
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            raise GdbError(f"rr record timed out after {timeout}s")
    except FileNotFoundError:
        raise GdbError("rr not found in PATH")

    output = stdout_bytes.decode(errors="replace")
    m = _RR_TRACE_RE.search(output)
    trace_dir = m.group(1) if m else None

    return {
        "trace_dir": trace_dir,
        "output": output,
    }


@mcp.tool()
async def start_replay_session(
    trace_dir: str | None = None,
    cwd: str | None = None,
) -> dict:
    """Start an rr replay session for time-travel debugging.

    The returned session_id works with all standard tools. Use reverse=True
    on continue_exec/step/finish to run backwards.

    trace_dir: trace directory from rr_record; omit for most recent recording
    cwd: working directory for rr
    """
    s = await manager.create_replay(trace_dir=trace_dir, cwd=cwd)
    return {"session_id": s.id, "trace_dir": trace_dir}


# ── Universal fallback ────────────────────────────────────────────────────────

@mcp.tool()
async def exec_command(
    session_id: str,
    command: str,
    timeout: float = 30.0,
) -> str:
    """Execute any GDB command and return its output.

    Resuming commands (run, continue, step, next, finish, until, etc.) block
    until the inferior stops again.

    command: GDB command string
    timeout: max seconds (default 30)
    """
    return await manager.get(session_id).send(command, timeout=timeout)


@mcp.tool()
async def batch_commands(
    session_id: str,
    commands: list[str],
    timeout: float = 15.0,
    stop_on_error: bool = False,
) -> list[dict]:
    """Execute GDB commands sequentially, returning each output.

    commands: list of GDB command strings
    timeout: max seconds per command (default 15)
    stop_on_error: halt on first error (default: continue)
    """
    s = manager.get(session_id)
    results: list[dict] = []
    for cmd in commands:
        try:
            out = await s.send(cmd, timeout=timeout)
            # send() only raises GdbError for infrastructure failures (timeout,
            # process exit).  GDB-level errors (^error records) are returned as
            # "Error: ..." strings, so we detect them here for stop_on_error.
            is_error = out.startswith("Error: ")
            results.append({"command": cmd, "output": out, "error": is_error})
            if is_error and stop_on_error:
                break
        except GdbError as e:
            results.append({"command": cmd, "output": str(e), "error": True})
            if stop_on_error:
                break
    return results


# ── Execution control ─────────────────────────────────────────────────────────

@mcp.tool()
async def run(
    session_id: str,
    args: str | None = None,
    timeout: float = 30.0,
) -> str:
    """Start or restart the inferior. Blocks until it stops.

    args: override command-line arguments
    timeout: max seconds (default 30)
    """
    cmd = f"run {args}" if args else "run"
    return await manager.get(session_id).send(cmd, timeout=timeout)


@mcp.tool()
async def continue_exec(
    session_id: str,
    reverse: bool = False,
    timeout: float = 30.0,
) -> str:
    """Continue execution. Blocks until next stop.

    reverse: run backwards (rr only)
    timeout: max seconds (default 30)
    """
    cmd = "reverse-continue" if reverse else "continue"
    return await manager.get(session_id).send(cmd, timeout=timeout)


@mcp.tool()
async def step(
    session_id: str,
    over: bool = False,
    reverse: bool = False,
    count: int = 1,
    instruction: bool = False,
) -> str:
    """Step one source line or instruction. Blocks until stopped.

    over: step over calls instead of into (GDB 'next')
    reverse: step backwards (rr only)
    count: number of steps (default 1)
    instruction: step by machine instruction instead of source line
    """
    if reverse and over:
        base = "reverse-nexti" if instruction else "reverse-next"
    elif reverse:
        base = "reverse-stepi" if instruction else "reverse-step"
    elif over:
        base = "nexti" if instruction else "next"
    else:
        base = "stepi" if instruction else "step"
    return await manager.get(session_id).send(f"{base} {count}")


@mcp.tool()
async def finish(
    session_id: str,
    reverse: bool = False,
    timeout: float = 30.0,
) -> str:
    """Run until current function returns. Blocks until stopped.

    reverse: run backwards to call site (rr only)
    timeout: max seconds (default 30)
    """
    cmd = "reverse-finish" if reverse else "finish"
    return await manager.get(session_id).send(cmd, timeout=timeout)


# ── Breakpoints ───────────────────────────────────────────────────────────────

@mcp.tool(name="breakpoint")
async def set_breakpoint(
    session_id: str,
    location: str,
    condition: str | None = None,
    temporary: bool = False,
) -> str:
    """Set a breakpoint. Triggers in both directions in rr sessions.

    location: function name, file:line, or *address
    condition: expression that must be true to trigger
    temporary: auto-delete after first hit
    """
    s = manager.get(session_id)
    cmd = f"{'tbreak' if temporary else 'break'} {location}"
    output = await s.send(cmd)
    if condition:
        # Case-insensitive: GDB prints "Breakpoint N" for break and
        # "Temporary breakpoint N" (lowercase b) for tbreak.
        bp_m = re.search(r"(?i)breakpoint (\d+)", output)
        if bp_m:
            cond_out = await s.send(f"condition {bp_m.group(1)} {condition}")
            if cond_out.strip():
                output += cond_out
    return output


@mcp.tool()
async def watch(
    session_id: str,
    expression: str,
    mode: str = "write",
) -> str:
    """Set a watchpoint that stops when an expression changes.

    expression: GDB expression (variable, *address, obj->field)
    mode: "write" (default), "read", or "access"
    """
    cmds = {"write": "watch", "read": "rwatch", "access": "awatch"}
    cmd = cmds.get(mode, "watch")
    return await manager.get(session_id).send(f"{cmd} {expression}")


# ── Inspection ────────────────────────────────────────────────────────────────

@mcp.tool()
async def backtrace(
    session_id: str,
    limit: int | None = None,
) -> str:
    """Show the call stack (backtrace).

    limit: max frames (omit for full stack)
    """
    cmd = f"backtrace {limit}" if limit is not None else "backtrace"
    return await manager.get(session_id).send(cmd)


@mcp.tool()
async def context(session_id: str) -> str:
    """Snapshot of current frame, arguments, locals, and source listing.

    Call after any stop event to orient. Resets GDB's list position to current PC.
    """
    s = manager.get(session_id)
    parts: list[str] = []
    # NOTE: "frame" must come before "list". GDB's "list" without arguments
    # scrolls forward on each call, but "frame" resets the internal list
    # pointer to the current PC.  Reordering these would cause "list" to
    # show the wrong lines on repeated context() calls.
    for cmd, label in [
        ("frame",        "Frame"),
        ("info args",    "Arguments"),
        ("info locals",  "Locals"),
        ("list",         "Source"),
    ]:
        out = await s.send(cmd)
        if out.strip():
            parts.append(f"=== {label} ===\n{out}")
    return "\n".join(parts)


@mcp.tool(name="print")
async def print_expr(
    session_id: str,
    expression: str,
    fmt: str | None = None,
) -> str:
    """Evaluate a GDB expression (print).

    expression: variable, cast, function call, etc.
    fmt: output format — x=hex, d=decimal, t=binary, s=string, etc.
    """
    cmd = f"print {'/' + fmt + ' ' if fmt else ''}{expression}"
    return await manager.get(session_id).send(cmd)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import logging

    logging.getLogger("mcp.server").setLevel(logging.WARNING)
    mcp.run()
