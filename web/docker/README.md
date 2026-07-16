# Ladybug web app — Docker

Runs the full dev-tool stack in one container: the **lwtools** 6809
assembler, the patched **`xroar-monitor`** emulator (built from pinned project
fork commit `7787ad937b15102bf8cb8eb81b92e29f5ba7169d`), the **FastAPI**
backend, and a headless X stack (**Xvfb → x11vnc → noVNC**) so the emulator
GUI is viewable in a browser.

No Python or backend code changes — this is purely additive tooling. The
backend still spawns each XRoar instance itself; the container just gives it a
virtual display and a way to look at it.

## Prerequisites — system ROMs (required)

`xroar-monitor -machine coco3 -cart-autorun` boots through Tandy BASIC, so
XRoar needs two **copyrighted** Microsoft/Tandy ROM images that are **not**
included in this repo or image. Supply your own legally obtained copies:

```
web/docker/roms/coco3.rom      32768 bytes   (Tandy Super ECB, CoCo 3)
web/docker/roms/extbas11.rom    8192 bytes   (Tandy Extended BASIC)
```

The `roms/` directory is mounted read-only at the container's `/root/.xroar`,
which is XRoar's default ROM search path. Without these files the container
still starts, but instances will not autorun into the cartridge (the
entrypoint prints a warning).

## Run

```bash
cd web/docker
docker compose up --build
```

Then open:

| URL | What |
|-----|------|
| <http://127.0.0.1:8765> | the web app |
| <http://127.0.0.1:6080/vnc.html> | live view of the XRoar emulator window (noVNC) |

Both ports are bound to `127.0.0.1` only — localhost-only, matching the app's
"no auth, localhost" design.

## How it fits together

| Process | Role | Port |
|---------|------|------|
| `Xvfb :99` | virtual X display | — |
| `fluxbox` | window manager (frames the XRoar window) | — |
| `x11vnc` | exports `:99` over VNC | 5900 (internal) |
| `websockify`/noVNC | VNC → browser | **6080** |
| `uvicorn backend.main:app` | the FastAPI web app | **8765** |

Per-instance XRoar processes are launched by the backend as children, on
`DISPLAY=:99`, so they appear in the noVNC view. Processes are supervised by
`supervisord` (see `supervisord.conf`).

## Notes / gotchas

- **Audio** is disabled in the build (`--without-alsa/pulse/oss/jack`); XRoar
  uses its null audio module. No sound device is needed.
- **Builds** done through the web UI write to `/app/build`, which is a named
  volume (`ladybug-build`) so they survive restarts.
- The image fetches the monitor-enabled XRoar fork at an exact commit and
  verifies the lwtools 4.24 source archive before building either tool. It uses
  the same monitor protocol the backend speaks (`-monitor`), **not** GDB.
- Rebuilding after editing `src/` assembly: the repo is **copied** into the
  image at build time, so source edits need a rebuild (or mount the repo as a
  volume for live editing — not configured by default to keep the image
  self-contained).
