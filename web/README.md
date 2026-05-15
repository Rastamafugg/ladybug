# Ladybug retro-dev web app

Locally-hosted browser UI wrapping `scripts/build.sh`, XRoar (with `-gdb`), and a
6809 GDB client into a single dev environment. Designed to run **entirely in
WSL** with the browser pointed at `http://127.0.0.1:8765`.

See [wiki/backlog/retro-dev-web-app.md](../wiki/backlog/retro-dev-web-app.md)
for the larger design context.

## Status

Scaffold only. The directory structure, API surface, and frontend pane
breakdown are in place; most handlers are TODO stubs. Nothing here drives a
real XRoar yet.

## Quick start (once handlers land)

```bash
cd web
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
./run.sh
# open http://127.0.0.1:8765
```

## Architecture

- **Backend** (`backend/`) — FastAPI app. Owns the XRoar lifecycle for every
  instance and is the **sole** GDB client per instance. Fans state out to
  WebSocket subscribers.
- **Frontend** (`frontend/`) — Plain HTML + vanilla JS + web components. No
  build step. Edit `.js` files, refresh browser.

### Single-GDB-client rule

XRoar 1.10's GDB stub accepts one active client at a time. **Do not run
`gdb-mcp` or any other GDB client against an instance the web app owns** — they
will fight. To inspect an instance from Codex, stop the web-app instance
first (or launch a separate XRoar manually on a different port).

### Instance lifecycle

```
creating → launching → attaching → running ⇄ halted → stopping → stopped
                                                              ↘ crashed
```

Every transition is published on `WS /ws/instances/{id}`.

### Port pool

XRoar `-gdb-port` is allocated round-robin from `65520..65540` per instance.

## Known constraints honored by the scaffold

- `-load <snap>` + `-gdb` together silently drops the stub in XRoar 1.10 — the
  backend does **not** offer snapshot-skip-autorun.
- Cart-autorun handshake takes several wall-clock seconds — the attach step
  retries with generous timeout, not the GDB-MCP default 30 s.
- `SWI` at a trap point segfaults XRoar 1.10 — if you want a deterministic
  halt, use `bra .` in source. See [wiki/tooling/xroar.md](../wiki/tooling/xroar.md).
