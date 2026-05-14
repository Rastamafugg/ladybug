---
name: Locally-hosted retro-dev web app with LLM-managed tooling
description: Web UI wrapping the lwasm + XRoar + gdb-mcp + LLM-agent stack into a closed-loop retro development environment, accessible from a browser.
type: backlog
tags: [tooling, infrastructure, llm, ui]
updated: 2026-05-14
---

# Locally-hosted retro-dev web app

## Why

Today the Ladybug dev loop is split across several windows: an editor for `src/*.s`, a WSL shell for `./scripts/build.sh`, the XRoar window for visual output, and a Claude Code session for LLM-driven debugging through the `gdb-mcp` bridge. The LLM has powerful capabilities through the GDB stub (read/write memory, breakpoints, watchpoints, framebuffer dumps) but no way to **see the screen** or **inject input**, and the human has no unified view of what's happening.

The same stack can be wrapped into a single browser tab that:

- Shows the XRoar framebuffer live (reconstructed from FB RAM via the GDB stub, palette, and GIME mode regs).
- Shows registers, MMU PARs, palette, and arbitrary memory views that update on every halt.
- Lets the human set breakpoints by clicking source lines from the `.lst`, and lets the LLM agent set them via tool calls.
- Streams an LLM-managed chat that can drive the same tools (build, attach, breakpoint, dump, restart) and gets the rendered framebuffer as multimodal input — closing the loop on "the agent can see the screen."
- Injects keyboard/joystick input via an X11 control path (`xdotool` against the XRoar window) so test scenarios can be scripted.

This becomes a reusable platform for any retro target the underlying tools support (CoCo 3 today; MAME, Stella, FCEUX in principle).

## Scope (MVP)

1. **Backend service.** Small process (Python/FastAPI or Node) running on the WSL/Linux host, with HTTP + WebSocket endpoints for:
   - `POST /build` → run `scripts/build.sh build`, return ROM size + map symbols.
   - `POST /launch` → start XRoar with `-gdb` on a managed port; return port + window ID.
   - `WS /gdb` → multiplex GDB-MI traffic (so multiple clients can subscribe to halts/state changes).
   - `GET /framebuffer.png` → read FB RAM + palette + GIME mode regs via the GDB stub, render to PNG. Cache per halt-event.
   - `POST /input` → forward key/joystick events to XRoar via `xdotool` against the window ID.
   - `POST /agent/message` → forward to an LLM tool-calling loop with access to the same tools the human has.

2. **Browser UI.** Single-page app (React or plain web components) with:
   - Live framebuffer canvas (polls or subscribes to halt events).
   - Source pane that loads `.lst` and lets you click to set breakpoints.
   - Memory view widgets: registers, MMU PARs, palette swatches, arbitrary hex-dump windows.
   - LLM chat pane with tool-call traces.
   - Build / run / reset buttons.

3. **LLM tool surface.** The agent has access to a curated subset of the GDB-MI bridge plus the framebuffer reader. It receives screenshots as multimodal input on every halt and can request more. Initial tool set: `read_memory`, `write_memory`, `set_breakpoint`, `continue`, `step`, `dump_framebuffer`, `inject_input`, `read_symbols`.

## Open design questions

- **Process model.** One backend per repo, or a daemon that manages multiple repos? Start with one-per-repo — simpler, no auth needed when bound to `127.0.0.1`.
- **GDB stub multiplexing.** XRoar's stub accepts one active client. Either route everything through a single backend-side GDB session that fans out, or run a tiny proxy. Backend-side session is easier.
- **Framebuffer rendering correctness.** The translation of GIME mode + palette + FB bytes → pixels is non-trivial (mode-dependent bpp, alpha vs graphics, scroll). Start with the modes Ladybug actually uses (320×192×16, 640×192×4); generalize later.
- **LLM cost / latency.** Pushing a framebuffer PNG per halt is heavy if halts are frequent. Strategies: only attach the FB image when the agent explicitly requests it; sub-sample; or send a hash + diff hint and let the agent ask for the full image.
- **Input injection reliability.** `xdotool` requires the XRoar window to be focused or addressed by window ID. WSLg's X11 forwarding may have quirks; verify per-keystroke timing.

## Non-goals (for the MVP)

- Authenticating multiple users or running on the public internet. **Localhost only.**
- Replacing the editor. Open the editor in another window; the web UI focuses on running/debugging.
- Building a new emulator. XRoar stays; the web app is a control surface.

## Done when

- A single command (`./scripts/dev-ui.sh` or similar) brings up backend + browser.
- Browser tab shows live framebuffer + registers + source for Ladybug.
- Click-to-breakpoint, step, continue all work.
- The LLM chat can drive an end-to-end scenario: "rebuild after edit, attach, set breakpoint at `blit_tile`, run, dump FB at halt, describe what it sees."
- Input injection drives a keypress (e.g. spacebar to advance a future title screen) and the FB reflects the change.

## Risks

- **Scope creep.** A full IDE is months of work; the MVP must stay small. Pick one source pane, one chat pane, one canvas — no fancy debugger UI.
- **GDB-MI quirks across emulator versions.** Build against XRoar 1.10 first; abstract the GDB layer only when a second emulator joins.
- **The "agent sees the screen" loop has cost implications.** Token cost for multimodal calls adds up fast in a tight build-debug cycle. Budget it explicitly.

## Starting prompt for the spin-off session

> Read [wiki/backlog/retro-dev-web-app.md](wiki/backlog/retro-dev-web-app.md). Design and scaffold the MVP described there. Start by drafting the backend HTTP/WS API surface (write it as a single-file FastAPI sketch under `tools/dev-ui/`), then a minimal HTML page that polls `/framebuffer.png` and shows registers. Use the existing `scripts/build.sh` and `gdb-mcp` bridge — don't replace them, just wrap them. The LLM tool surface comes after the backend works end-to-end with manual `curl`.

## Sources

- [tooling/xroar.md §GDB-MCP round trip](../tooling/xroar.md)
- [tooling/build-workflow.md](../tooling/build-workflow.md)
- [implementation/lessons-learned.md](../implementation/lessons-learned.md) — XRoar quirks the framebuffer reader will have to honour
- [platform/gime.md](../platform/gime.md) — GIME mode → pixel-format mapping the framebuffer renderer needs
