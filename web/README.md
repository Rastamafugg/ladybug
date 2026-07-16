# Ladybug retro-dev web app

Locally hosted browser UI that combines the Ladybug ROM build, the patched
XRoar `-monitor` JSON-RPC interface, and a 6809-aware debugger. The backend
owns every emulator session; the frontend is plain JavaScript and web
components with no build step.

The app currently supports ROM builds, multiple XRoar instances, run/pause/
step/reset control, executable breakpoints, register and memory inspection,
source/listing display, instruction annotation, GIME state, framebuffer and
palette rendering, and user-defined memory regions.

See the [web-app architecture](../wiki/internal/tooling/web-app-architecture.html)
and [XRoar monitor protocol](../wiki/internal/implementation/xroar-monitor.html)
for the design details.

## Recommended start: Docker

The container includes lwtools 4.24, the pinned monitor-enabled XRoar fork,
FastAPI, and a headless X/noVNC stack. Supply the required CoCo 3 system ROMs,
then run:

```bash
cd web/docker
docker compose up --build
```

Open `http://127.0.0.1:8765` for the debugger and
`http://127.0.0.1:6080/vnc.html` for the XRoar display. See
[web/docker/README.md](docker/README.md) for ROM requirements and details.

## Direct WSL start

Direct hosting requires Python dependencies, a built `xroar-monitor`, and the
CoCo 3 system ROMs in XRoar's normal search path.

```bash
cd web
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
./run.sh
```

Set `XROAR_BIN=/path/to/xroar-monitor` when the patched binary is not at the
repository default, `docs/reference/xroar/build/xroar-monitor`.

## Architecture

- `backend/` is the FastAPI application. It owns XRoar processes and one
  `MonitorSession` JSON-RPC connection per instance.
- `frontend/` contains the static HTML, CSS, and JavaScript components.
- `data/` contains 6809 opcode, register, memory-map, and symbol reference data.
- `scripts/` contains protocol probes and end-to-end verification utilities.

Instance lifecycle:

```text
creating -> launching -> attaching -> running <-> halted -> stopping -> stopped
                                                              -> crashed
```

State and halt updates are published on `WS /ws/instances/{id}`. Monitor ports
are allocated from `65520..65539`.

## Monitor ownership

The backend connection is the authoritative controller for an instance. Do not
attach another interactive monitor client to the same instance while the web
app owns it. Launch a separate XRoar process and port for independent probing.

Known emulator and protocol constraints are maintained in the
[XRoar tooling page](../wiki/internal/tooling/xroar.html) and
[lessons learned](../wiki/internal/implementation/lessons-learned.html).
