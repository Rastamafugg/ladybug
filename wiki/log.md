# Wiki Log

Append-only chronological record of ingests, queries, and lints. Each entry prefixed `## [YYYY-MM-DD] <type> | <title>` so the log is grep-parseable.

---

## [2026-05-17] milestone | Phase 3 M2 — `-monitor` memory + registers green

Extended [monitor.c](../docs/reference/xroar/src/monitor.c) with four methods: `read_memory` / `write_memory` (CPU space, via `machine->read_byte/write_byte`), `read_registers` / `write_registers` (6809: a, b, d, cc, dp, x, y, u, s, pc). State-mutating methods enforce halted-only and return JSON-RPC error `target_running` (code `-32001`) when CPU is running. Read length capped at 64 KB per request (`-32602` if exceeded); writes capped likewise; `space="physical"` is rejected in M2 (`-32602`, deferred to M3). `MONITOR_LINE_MAX` raised to 192 KB so a 64 KB hex payload fits. `d` register is read-only (derived from `a:b`); `write_registers` accepts any subset of fields. Probe [probe_monitor_m2.py](../web/scripts/probe_monitor_m2.py) green with 7 sub-tests including the plan's mandatory cases (`$FE00-$FEFF` round-trip; `target_running` on both write methods while running; reads-while-running permitted). One twist surfaced: `$FE00-$FEFF` is RAM only when GIME's `MC3` bit is set, which Color BASIC does during init — so the probe issues `run`, sleeps 2 s for BASIC to come up, then `pause` before the round-trip test. `read_only_region` error for CPU-space ROM writes deferred to M3 (per plan, needs GIME-state probe to do the S/RAS precheck). Existing-file delta this milestone is monitor.c only; no other XRoar files touched.

---

## [2026-05-17] milestone | Phase 3 M1 — XRoar `-monitor` listener + hello + run/pause green

M1 implementation complete on branch `ladybug/monitor` (XRoar nested repo). Vendored cJSON v1.7.18 ([cJSON.c/h](../docs/reference/xroar/src/cJSON.c)). New module [monitor.c](../docs/reference/xroar/src/monitor.c) (~390 LOC) + [monitor.h](../docs/reference/xroar/src/monitor.h) parallels gdb.c structurally: one blocking-accept pthread, BSD sockets, `pthread_mutex` + `pthread_cond` run-state gate consulted by the machine's `coco3_run` per-frame callback. Line-delimited JSON-RPC 2.0 framing. M1 surface = hello notification + `get_run_state` / `run` / `pause`. Existing-file delta matches the plan within tolerance: [configure.ac](../docs/reference/xroar/configure.ac) ~14 lines (`--enable-monitor` + `WANT_MONITOR`), [src/Makefile.am](../docs/reference/xroar/src/Makefile.am) 5 lines (`if MONITOR` block), [src/xroar.h](../docs/reference/xroar/src/xroar.h) 3 lines (cfg fields), [src/xroar.c](../docs/reference/xroar/src/xroar.c) ~12 lines (include + option table + help + config-print), [src/coco3.c](../docs/reference/xroar/src/coco3.c) ~25 lines (include + struct field + new/free + run-loop gate; gdb takes precedence when both flags set, monitor passive in that case). Built clean with `./configure --enable-monitor && make -j16`; side-by-side binary at `docs/reference/xroar/build/xroar-monitor` (4.6 MB; baseline at `xroar-baseline`). New probe [web/scripts/probe_monitor_m1.py](../web/scripts/probe_monitor_m1.py) — 7 sub-tests covering: hello fields, halt-on-start initial state, `get_run_state` round-trip, `run`→`running`, `pause`→`halted`, unknown-method JSON-RPC `-32601`, malformed-JSON `-32700` + connection survives, disconnect-reconnect with run-state preserved across reconnect. All green on first run. Reads `XROAR_BIN` env var (defaults to the in-tree `xroar-monitor`). Next: M2 (memory + registers, halted-only enforcement).

---

## [2026-05-17] bring-up | Phase 3 M1 — XRoar repo bring-up complete

Verified `docs/reference/xroar/` clean at pinned HEAD `1e5e9552` (XRoar 1.11-4-g1e5e9552). `git fetch origin` showed only one trivial unrelated cleanup commit (`a2d31903 mpi: remove unused global`) ahead and no new release tags — stayed pinned per plan. Tagged baseline `ladybug-monitor-base`; created and checked out branch `ladybug/monitor`. Hit a Windows-checkout gotcha: nested repo had `core.autocrlf=true` which CRLF-corrupted `autogen.sh` shebang under WSL (`bad interpreter: /bin/sh^M`). Disabled (`core.autocrlf=false`) and `git reset --hard` to rehydrate the working tree with native LF — lesson captured in [implementation/lessons-learned.md §Nested Unix repo autocrlf](implementation/lessons-learned.md). Ran `./autogen.sh && ./configure && make -j16` clean on Ubuntu WSL — XRoar 1.11 built with GTK3+OpenGL UI (SDL2 not needed, not installed). Stashed baseline binary at `docs/reference/xroar/build/xroar-baseline` (ELF, 4.45 MB, `--version` reports XRoar 1.11). Next: vendor cJSON, add `--enable-monitor` autoconf glue, implement `src/monitor.{c,h}` M1 scope (listener + hello + `run`/`pause`/`get_run_state`).

---

## [2026-05-16] plan | XRoar `-monitor` Phase 2 implementation plan approved

Appended Phase 2 plan section to [implementation/xroar-monitor.md](implementation/xroar-monitor.md). Decisions: pin XRoar at upstream `1e5e9552` (4 commits past tag `1.11`); local feature branch `ladybug/monitor` (no GitHub fork yet); new module `src/monitor.c` + `monitor.h` paralleling `src/gdb.c`; vendor cJSON for JSON parsing; threaded blocking-accept model mirroring gdb; wired into `coco3.c` only (CoCo 3-only scope). Existing-file delta ~35 lines across `Makefile.am`, `configure.ac`, `xroar.h`, `xroar.c`, `coco3.c` — all gated behind `if MONITOR` + runtime cfg check. Side-by-side install as `xroar-monitor` binary with `XROAR_BIN` env override in [scripts/build.sh](../scripts/build.sh) and [web/backend/instance.py](../web/backend/instance.py). Physical address representation: flat 19-bit `$00000-$7FFFF`, internally split to `(bank, offset)`. Phase 3 broken into six milestones (M1 listener/hello/run-control → M6 SHOULD-tier capabilities), each a separate conversation closing in qa-reviewer. Web-backend integration is post-Phase-3 follow-up. Ready to start Phase 3 M1 in a new conversation.

---

## [2026-05-16] plan | XRoar `-monitor` Phase 1 requirements filed; cart-window write decode traced

Filed [implementation/xroar-monitor.md](implementation/xroar-monitor.md) as the Phase 1 requirements doc for a custom JSON-RPC "monitor" server inside XRoar. Architecture: XRoar speaks project-private JSON-RPC over TCP (default `127.0.0.1:17654`); the Ladybug web backend brokers commands to MCP-speaking clients (XRoar itself is not MCP-aware). Flag `-monitor [host:]port` plus `-monitor-halt-on-start`. Address-space model exposes both CPU-virtual (PAR-resolved) and physical (19-bit, bypass) reads/writes. State-writes are halted-only; CPU-space writes to ROM-backed addresses return `read_only_region`; physical-space writes always land in RAM. Both `-monitor` and `-gdb` allowed concurrently (unsupported). On last-client disconnect: CPU stays halted, awaiting reconnect; web backend tracks session liveness. Supersedes the deferred [backlog/mcp-xroar-server.md](backlog/mcp-xroar-server.md) sketch. Root cause of XRoar's cart-shadow no-op traced via Explore agent through `tcc1014.c` / `coco3.c` / `cart.c` / `rombank.h` — added to [implementation/lessons-learned.md §XRoar cart-window write decode](implementation/lessons-learned.md) (verdict: intentional XRoar simplification, not faithful to CoCo 3 silicon). Filed [backlog/mame-cart-ram-comparison.md](backlog/mame-cart-ram-comparison.md) to cross-check via MAME on WSL. Next role: coding-architect (Phase 2 implementation plan).

---

## [2026-05-16] plan | Tester WS-A architect pass — design locked, ready for implementation

Designed the GIME-visibility probe + WS-A tester ROM v0 structure + WS-B `gime_state.py` API surface. Captured in [implementation/emulator-monitor-tester.md](implementation/emulator-monitor-tester.md) §"WS-A architect-pass decisions". Probe lands as `web/scripts/probe_gime_readback.py` against a running diag_minimal instance (no new ROM); pass/fail mapping selects between DirectReadStrategy / ProgramStateStrategy / ShadowBlockStrategy. Tester ROM goes in `src/tester/` subtree (7 files: tester.s + dp.inc + input.s + render.s + pat_bars.s + pat_check.s + modes.inc), DP slots at $0200-$020C all named symbols, key bindings 1-8 = modes (v0 honors 1), B/C = patterns. Build target `cmd_tester` + `cmd_tester_run` added to scripts/build.sh, Ladybug build paths untouched. Tester exports both `tester_mode_idx` and `tester_mode_table` so option 2 is available regardless of probe outcome. All five user-approval items resolved. Ready for implementation.

---

## [2026-05-16] plan | Emulator-monitor tester initiative — requirements filed

Captured the four-workstream tester+webapp initiative as [implementation/emulator-monitor-tester.md](implementation/emulator-monitor-tester.md). WS-A tester ROM (evolved from [src/diag_minimal.s](../src/diag_minimal.s), keyboard key-per-option, no on-screen HUD, continuous loop + 60 Hz Vbord IRQ, v0 patterns = horizontal bars + checkerboard, v0 mode = 320×192×16). WS-B live FB renderer (new `web/backend/gime_state.py`, RGB-decode, halt-driven + optional free-run poll). WS-C mapped regions feature (per-config persistence, addr/symbol+offset/follow-pointer definitions, 32 KB cap, every-halt refresh, extensible viewer plugins with hex baseline; new `web/backend/regions.py` + `web/frontend/components/memory-regions.js`). WS-D mode-matrix expansion (all four hi-res families, blank-during-switch). Step-sync = all panels every halt. **Shadow-register convention demoted** — the user pushed back on it as load-bearing infrastructure; it's now option 3 of three, behind direct-read-via-gdb and tester-program-state. Empirical probe of `read_memory($FF98, 8)` against XRoar gates the choice. New `tester` build target, `gime_state.py`, `regions.py`, `memory-regions.js`, and viewer-plugin convention all approved by user. Next role: coding-architect.

---

## [2026-05-16] build | Convert to RGB tv-input + rebuild palette tables; isolate Phase 2.x FB-render regression

Executed [backlog/rgb-tv-input-palette.md](backlog/rgb-tv-input-palette.md). Added `-tv-input rgb` to both XRoar launch sites ([scripts/build.sh](../scripts/build.sh) and [web/backend/instance.py](../web/backend/instance.py)) and the canonical-invocation snippets in [tooling/xroar.md](tooling/xroar.md) + [tooling/build-workflow.md](tooling/build-workflow.md). Built a minimal-from-scratch hi-res cart ([src/diag_minimal.s](../src/diag_minimal.s)) — no MMU, no cart self-copy, FB at phys $072000 = virt $2000 (top-64K mapping) — that displays 16 clean horizontal stripes under `-tv-input rgb`. Used it to derive the empirical RGB 6-bit→colour table now in [implementation/lessons-learned.md](implementation/lessons-learned.md) §"XRoar RGB monitor palette mapping" (key finding: full white is `$3F`, not `$38`; `$38` is light grey). Updated `palette_table` in [src/main.s](../src/main.s) accordingly: indices 0-3 = `$00 $30 $08 $3F` (black / bright yellow / bright blue / full white). Composite-NTSC table preserved in the same lessons-learned section, clearly labelled as historical/secondary. **Surfaced regression:** Phase 2.x main.s renders the FB as red+green noise under *both* RGB and composite, contradicting the lessons-learned claim that the 3-tile render works. Minimal cart works perfectly, so the bug is somewhere in main.s's MMU / PAR-load / cart-self-copy chain. Filed [backlog/phase2-fb-render-regression.md](backlog/phase2-fb-render-regression.md) with observed facts, candidate causes (ranked), and a bisect-from-diag-minimal investigation plan. Acceptance criterion "Phase 2.4 isolation build renders three tiles correctly under RGB" in the rgb-tv-input-palette backlog item now blocked on that regression and explicitly noted.

---

## [2026-05-15] build | B2 backend wiring — opcode decoder, annotation engine, regions, symbols, endpoints

Wired the v2 web app's backend annotation pipeline. New modules: `opcode_table.py` (loads + indexes opcode + indexed-postbyte JSON at startup), `decoder.py` (bytes + 6809 state → structured Instruction; handles imm8/imm16/direct/extended/relative8/relative16/indexed_postbyte/tfr_exg_postbyte/psh_pul_postbyte/inherent operand kinds; page-2 prefix handled; ~24 indexed-postbyte forms cover every 6809 indexed mode with pre/post-inc/dec, A/B/D-offset, PCR, and extended-indirect), `annotation.py` (Instruction + regs → JSON payload with disassembly, effect text, CC predictions, region notes, cart-window write-warning when applicable), `regions.py`, `symbols.py` (parses `build/ladybug.map`, falls back to nearest-symbol-at-or-before-addr; merges with `web/data/symbols.json` for wiki anchors). New endpoints: `/api/regions`, `/api/registers-doc`, `/api/symbols/lookup?addr=`, `/api/decode/{id}?addr=&len=`. Smoke-tested against 8 hand-crafted instructions (LDA imm, ORCC imm, LDX imm, LDD indexed-zero-offset with EA resolution, STA indexed write triggering cart-window warning, BNE relative branch with target computation, TFR postbyte, page-2 LDS imm) — all produce correct disassembly + effect + notes. Live decode against the running XRoar instance returns gracefully-degraded "(opcode not curated)" for the $00/$FF padding bytes BASIC sees at $C002 pre-autorun, confirming the stub path is honest. No regressions to the existing instance/memory/register/source/breakpoint endpoints. Next: B3 — frontend panes (instruction-annotation, register hover, memory-region hover, symbol-context).

---

## [2026-05-15] build | B1 punch-list fixes; mnemonic-family anchors added to platform/6809.md

QA punch-list disposition (user chose "fix all five before B2"): (1) broken `warning-under-xroar-110-...` anchor in `6809-regions.json` cart-window entry corrected to `important-under-xroar-110-the-self-copy-is-a-no-op`; (2) added `$FF40-$FF8F` "FDC / reserved I/O" region so every I/O-page hover resolves; (3) architecture page (`tooling/web-app-architecture.md`) now formally documents `length: int | "variable"` and `cycles: int | {min,max,note}` to cover indexed-mode and path-dependent opcodes — locked before B2 decoder work; (4) RTI updated to use the conditional-cycles object (6/15 with note); (5) added `## Mnemonic reference` section to `platform/6809.md` with nine family anchors (load-ops, store-ops, lea-ops, branch-ops, push-pull-ops, tfr-exg-ops, return-halt-ops, cc-ops, arith-bit-ops); opcode JSON `wiki` fields retargeted to those anchors via script (82 entries changed, SWI kept on the xroar-gotcha link). Next: B2 — backend wiring (opcode_table.py, decoder.py, annotation.py, regions.py, symbols.py, endpoints).

---

## [2026-05-15] build | web/data/ JSON authoring (Track B sub-task 1)

Authored the five data files for the v2 web/ wiki-UI architecture: 6809-opcodes.json (83 encodings: 68 primary + 15 page-2; scoped to Ladybug's current vocabulary), 6809-indexed-postbyte.json (24 postbyte patterns covering every 6809 indexed-addressing form including pre/post inc/dec, accumulator-offset, PC-relative, and extended-indirect), 6809-regions.json (17 memory regions matching implementation/memory-map.md), 6809-registers.json (10 regs + 8 CC bits with per-bit semantics), symbols.json (5 seed entries pointing into the wiki). All JSON-validates. Hybrid wiki-content convention honored: short `summary` inline + `wiki` deep link. Schema matches tooling/web-app-architecture.md. Next sub-task (B2): backend wiring — opcode_table.py, decoder.py, annotation.py, regions.py, symbols.py, and the new endpoints. Closing this sub-task in qa-reviewer.

---

## [2026-05-15] design | web/ v2 architecture filed; reverse-step deferred; XRoar patch chosen for local-only apply

User locked scope for the v2 web/ work: instruction annotation, register/region/symbol wiki surfaces, persistent configs as `web/configs/*.json` per-file, snapshot save/load (with patched XRoar). Reverse-step / time-travel / change-log deferred entirely. XRoar SO_REUSEADDR patch chosen for local apply (not upstreaming). Architect-role pass produced the module split, schema decisions, halt-event data flow, and XRoar-patch dependency handling (attempt-and-detect, no version probe). Three approval gates passed: module split (3-layer decode pipeline + separate regions/symbols/configs modules + web/data/ convention); flat snapshot directory + sidecar manifest; indexed-postbyte table as separate JSON. Full design: [tooling/web-app-architecture.md](tooling/web-app-architecture.md).

---

## [2026-05-15] research | XRoar `-load + -gdb` bug is a missing SO_REUSEADDR; one-line fix viable

Feasibility report on patching XRoar 1.10 to fix snapshot-load dropping the gdb listener. Root cause: `gdb_interface_new` ([src/gdb.c:185](../../docs/reference/xroar/src/gdb.c)) is called twice when `-load` is given — once in the initial `coco3_init` from `xroar_hard_reset`, once in the deserialised machine's `coco3_init` after `read_snapshot` ([src/snapshot.c:236-241](../../docs/reference/xroar/src/snapshot.c)) frees and replaces the machine. The first listener is closed cleanly, but the listening socket lacks `SO_REUSEADDR`, so the kernel's `TIME_WAIT` window blocks the second `bind()`. XRoar *does* log the failure (`[gdb] WARNING: bind 127.0.0.1:PORT failed`) — wiki's "silently drops" framing was inaccurate and is corrected in the report. Fix is a single `setsockopt(SO_REUSEADDR)` call between `socket()` and `bind()`; ~2-3 h to apply + verify + upstream. Full report: [backlog/xroar-load-gdb-patch.md](backlog/xroar-load-gdb-patch.md). User decision pending: don't-patch / local-only / upstream.

---

## [2026-05-15] research | gdb `record full` / reverse-step is not viable against m6809-gdb + XRoar 1.10

Empirical probe to inform the web/ time-travel design. Result: **no path through gdb works**. Two independent rejections from a single attached session: gdb refuses `record full` with `Process record: the current architecture doesn't support record function` (m6809 isn't in gdb's record-supported architecture list); separately, XRoar's stub rejects `reverse-stepi`/`reverse-continue`/`record btrace` with `Target remote does not support this command`. Forward stepping is unaffected and works normally. Either layer alone would close this path; both being closed means a fix requires patches in both gdb (m6809 record port) and XRoar (reverse-protocol packets), which is multi-day work in each. Recorded in [tooling/xroar.md §Reverse execution / `record full` — not viable on this stack](tooling/xroar.md). Practical consequence for the web/ app: any time-travel feature must be backend-recorded (per-step state snapshots) rather than gdb-mediated — directly affects the upcoming architecture pass.

---

## [2026-05-15] build | Scaffolded `web/` retro-dev backend + frontend; landed five XRoar-stub gdb gotchas

Stood up the locally-hosted web app described in [backlog/retro-dev-web-app.md](backlog/retro-dev-web-app.md): FastAPI backend owning XRoar lifecycle on a 65520..65540 port pool, vanilla-JS+web-components frontend, ephemeral UI-created instances. Live attach to XRoar's GDB stub via `m6809-gdb --interpreter=mi`, registers + memory readable, WS fan-out delivers state/halt/log events. The chat pane was dropped per user direction (Codex stays the LLM-facing surface). During bring-up, five XRoar-1.10 + m6809-gdb integration gotchas surfaced — all now recorded in [tooling/xroar.md §Known XRoar 1.10 limitations](tooling/xroar.md): stub answers `vMustReplyEmpty` with `"timeout"` (fatal in MI; only raw-stdin CLI `target remote` survives it); probe-connect+disconnect wedges the stub; `info registers` always trails with a benign `^error: Register 12 is not available`; MI stream records split `NAME=VAL` across chunks; and the gdb reader loop deadlocks if you read regs synchronously from inside an async-event callback. Three of these are project-property of *m6809-gdb against this stub*, not XRoar alone, so they're also relevant to the gdb-mcp workflow.

---

## [2026-05-15] debug | L4 sentinel probe at `$FEF7` did not execute; boot likely derails at MMU-enable

Fifth pass on cart-ram-corruption. Inserted sentinel `STA #$55 / STA $FEF7 / LDA $FEF7 / STA $0FFE / STA $0FFF` at `$C0BE-$C0CD` immediately before `phase24_halt`. Built, ran XRoar 1.10 with `-gdb`, attached via gdb-mcp + m6809-gdb. **Probe did not execute** — both `$0FFE` and `$0FFF` read `$FF` (DRAM init pattern). Registers at attach: `A=$68` consistently (= the byte loaded by `LDA #%01101000` at `$C078`, one instruction before the MMU-enable at `$C07A`). Boot reaches at least `$C078`, then derails; most likely at the MMU-enable when subsequent instruction fetches route through PAR6 → phys `$3E` → uninitialised DRAM (cart-shadow self-copy is a no-op per the 2026-05-14 finding). The narrow "IRQ vector doesn't install" framing is wrong; the real failure is earlier and broader. Also discovered: gdb-mcp reads at `$C000+` now return DRAM init pattern (not cart bytes), contradicting the 2026-05-14 fourth-pass finding — gdb-mcp's cart-window read path cannot be trusted. The "Phase 2.4 reaches halt from cold start" verification via `-trap pc=0xC0BE -trap-snap` is also retroactively suspect because that trap fires on any PC match, including wandering-CPU drive-bys to a `BRA self` byte sequence. Recommended next session: ditch the cart-window gdb-mcp reads, use behavioural sentinel stores in DP page `$0200+` at multiple checkpoints (specifically just before and just after `$C07A` MMU-enable) to discriminate where execution stops. Also re-verify the "three tiles render" claim by reading the framebuffer phys pages directly. Full session notes in [backlog/cart-ram-corruption.md §2026-05-15](backlog/cart-ram-corruption.md).

---

## [2026-05-15] propagate | Cart-shadow no-op finding rolled into memory-map and lessons-learned

Followed up the four-pass cart-ram-corruption investigation by updating the wiki to match the new mental model. [implementation/memory-map.md](implementation/memory-map.md): added an "⚠️ Important: under XRoar 1.10 the self-copy is a no-op" subsection to the boot data-copy procedure, qualified the Phase 2.1 verification as non-discriminating, documented implications for self-modifying code / data tables / the `org $C0DC` workaround, and added an "open items" entry for the XRoar source-review gap. [implementation/lessons-learned.md](implementation/lessons-learned.md): added a new entry "Cart-shadow self-copy is a no-op under XRoar 1.10 — we execute from cart ROM throughout" with why, applies-to, and citations. Long-term plan: keep the self-copy in source for hardware-correctness (Phase 10), treat as dead code when reasoning about XRoar. Next debugger session pivots to L4 — probe MC3/MMU/PAR state at the exact moment of `STA $FEF7` to explain the IRQ-install bug.

---

## [2026-05-14] debug | Phase 2.4 boot confirmed working from cold start; source-review gap remains but project unblocked

Fourth pass on cart-ram-corruption. Three discriminating probes:
1. Cold-start verification: cleared `~/.xroar/`, ran clean Phase 2.4 build with `-trap pc=0xC0BE -trap-snap`. Trap fired; snapshot was written. **Phase 2.4 reaches `phase24_halt` from cold start — not stale state.**
2. Post-SAM_ALLRAM probe at $C05E: boot survives `sta SAM_ALLRAM`; `$C000+` reads continue to return cart bytes.
3. Pre-cart-shadow probe at $C02A: `$C000+` already returns cart bytes BEFORE the self-copy runs. **The self-copy is irrelevant** to cart accessibility; XRoar serves cart bytes through a path my source-review couldn't fully trace.

Decisive empirical confirmation: cart bytes accessible at `$C000-$FDFF` throughout the boot, pre- and post-SAM_ALLRAM, with or without the self-copy. The Phase 2.4 boot architecture WORKS on XRoar 1.10. The IRQ-vector bug from the original investigation is therefore a real, isolated problem — not a symptom of broader boot breakage. Next debugger session should pivot back to L4 (probe MC3/MMU/PAR state at `STA $FEF7` time). Also identified one XRoar 1.10 bug worth filing: **`-load` + `-gdb` together fails to bind the gdb listener** ([tooling/xroar.md](tooling/xroar.md) updated). The `swi`-segfault is a separate known bug.

Source-review gap: my decode trace of `tcc1014.c` predicts `$E000` should return cart padding via `case 1`/`cart_rom_read`, but empirically returns SECB-style vector-table bytes. Something about MC1/MC0 selection or the case-1 read path differs from my reading. Not blocking; documented as a known knowledge gap.

---

## [2026-05-14] debug | cart-shadow self-copy CONFIRMED non-functional; what we read at $C000+ is cart ROM via the S=1/CTS path, not RAM

Third gdb-mcp pass on cart-ram-corruption with a `bra .` halt inserted at `copy_done` (PC=$C047, pre-SAM_ALLRAM). Attached cleanly. Reads of `$C000-$C05F` matched the cart ROM file byte-for-byte — but this is NOT because the cart-shadow copy populated RAM. With MC3=1, MMUEN=0, TY=0, the GIME's address decoder ([tcc1014.c:716-737](../docs/reference/xroar/src/tcc1014/tcc1014.c)) routes `$C000-$FDFF` through S=1 (CTS, cart ROM) with RAS=0. In `coco3.c read_byte`, the case-1 branch returns cart ROM bytes via `cart_rom_read`/`rombank_d8`, and the `if (RAS)` ram-overlay block is SKIPPED. So gdb-mcp reads at `$C000+` see cart ROM directly. The cart-shadow loop's `std ,x` writes for x in `$C000-$FDFE` go to `cart_rom_write` (no-op) and skip ram_d8 (RAS=0) — they don't reach RAM. For x in `$FE00-$FEFE` (MC3 inner check sets RAS=1), the writes DO reach RAM, but the `ldd ,x` source is also RAM (cart_rom_read overwritten by ram_d8) — it's a RAM→RAM round-trip with no cart bytes involved. **Net: the self-copy is a no-op on XRoar 1.10. RAM at `$C000-$FEFF` is never populated by our boot.** The boot has been running directly from cart ROM all along; our mental model of "self-copy then all-RAM execution" is wrong. New open question: how does Phase 2.4 render 3 tiles, since the post-SAM_ALLRAM code path should fetch uninitialized RAM? Two next-probes captured in [backlog/cart-ram-corruption.md](backlog/cart-ram-corruption.md). The IRQ-vector bug is still seen as a symptom, not the root cause.

---

## [2026-05-14] debug | cart-shadow self-copy appears non-functional under XRoar 1.10

Second gdb-mcp pass on cart-ram-corruption using the new SWI-trap + snapshot workflow. Key blockers and findings:
- SWI in cart code makes XRoar 1.10 **segfault** at snapshot time. Avoid `swi` for halt-and-inspect; use `bra .` instead. [tooling/xroar.md](tooling/xroar.md) updated.
- After inserting a `lda#$7E / sta $FEF7 / lda $FEF7 / sta $1000 / probe_halt: bra .` probe and attaching, found PC wild ($B977 in BASIC ROM disassembling uninit memory), `$1000=00 00` (probe sentinel never persisted), and `$C000-$C0FF` filled with `00 00 00 00 FF FF FF FF` pattern — which exactly matches XRoar's default DRAM init fill ([ram.c:296-302](../docs/reference/xroar/src/ram.c)).
- **The cart-shadow self-copy at [src/main.s:102-118](../src/main.s) is non-functional under XRoar 1.10.** Pre-SAM_ALLRAM with MC3=1, MMUEN=0, the GIME's address decode for `$C000-$DFFF` returns `S=1 (CTS)` with `RAS=0` ([tcc1014.c:729-737](../docs/reference/xroar/src/tcc1014/tcc1014.c)). In coco3.c write_byte, the `if (RAS)` block is therefore skipped; the cart's write callback runs but `cart_rom_write→rombank_d8` is **read-only** ([rombank.h:102-107](../docs/reference/xroar/src/rombank.h)). So `std ,x` writes go nowhere; cart-window RAM stays at DRAM init pattern.
- Open question: how does Phase 2.4's 3-tile render appear to work, since post-SAM_ALLRAM execution would have to come from RAM that is empty? Hypotheses captured in [backlog/cart-ram-corruption.md](backlog/cart-ram-corruption.md). Recommended next probe is to halt RIGHT after the cart-shadow loop and read `$C000+` directly.
- The IRQ-vector bug is now seen as a SYMPTOM of this deeper boot-architecture mismatch, not the root cause. Investigation should pivot to understanding cart-shadow vs. cart-ROM execution before any IRQ fix.

---

## [2026-05-14] tooling | gdb-mcp stability workarounds + mcp-xroar backlog

Captured three current-stack workarounds for gdb-mcp instability during early-boot inspection in [tooling/xroar.md](tooling/xroar.md): explicit `timeout: 60+` on continue commands, temporary `swi` opcodes in source for deterministic stops, and `-trap`/`-trap-snap`/`-load` for snapshot-based fast re-entry past the cart-autorun handshake. Also documented the cycle-/GIME-state inspection gaps that the gdb stub can't fill, and filed [backlog/mcp-xroar-server.md](backlog/mcp-xroar-server.md) as the deferred option — build only when sentinel probes have hit a wall on a critical-path investigation. Index updated.

---

## [2026-05-14] debug | cart-ram-corruption reframed via XRoar source review + gdb-mcp probe

Cloned XRoar source into `docs/reference/xroar` (gitignored). Reviewed 1.10..HEAD (= 1.11) — no GIME / MMU / force-$FExx / IRQ-vector fixes; the only CoCo3-relevant change is a keyboard-IRQ tick frequency tweak. Source review of `tcc1014/tcc1014.c` shows the GIME MMU read/write paths for `$FE00-$FEFF` are symmetric (write and read use the same decoder → same physical bank), so an emulator-side path that produces "write $7E read $16" is implausible. Ran XRoar 1.10 with `phase24_halt` bypassed and gdb-mcp attached; the readback at `$C0CB` (immediately after `STA $FEF7`) showed `$FEF7 = 0x16`, NOT `$7E`. Bumping `-ram` from 512 to 1024 (to flip XRoar's `dat.enabled`) produced identical results — confirming `dat.enabled` is NOT the gate (the real GIME MMU is in `tcc1014.c`, not in the DAT-board overlay in `coco3.c`). Also identified that the wiki backlog's quoted install bytes had a typo (`B6 7E` vs the correct `86 7E` — verified against `build/ladybug.lst:220`). Backlog updated with new leads L1-L4 and reproduction notes; gdb-mcp session stability is a separate blocker (autorun handshake takes longer than gdb-mcp's default per-command timeout).

---

## [2026-05-14] backlog | Three spin-off items filed

Filed [backlog/rgb-tv-input-palette.md](backlog/rgb-tv-input-palette.md), [backlog/cart-ram-corruption.md](backlog/cart-ram-corruption.md), and [backlog/retro-dev-web-app.md](backlog/retro-dev-web-app.md). RGB-palette comes from `scripts/build.sh` not passing `-tv-input`; cart-RAM-corruption surfaced when removing the Phase 2.4 isolation halt let the carried-forward Phase 2.3 IRQ-install path run on top of the new MMU layout and the CPU went off the rails; retro-dev-web-app is a forward-looking wrap of the lwasm + XRoar + gdb-mcp + LLM stack into a browser UI. Index updated.

---

## [2026-05-14] task | Phase 2.4 three-tile build-out

Updated [`src/main.s`](../src/main.s) to render three copies of the arcade char #432 test tile at top-left / top-center / top-right of the framebuffer, replaced the hardcoded `$1111` blit_tile body with a Y-sentinel loop reading from a passed source pointer (per the existing `LDD ,Y++ clobbers B` lesson), and shifted the XRoar-bad-window padding to an `org $C0DC` placed before `mainloop` so live code stays out of `$C0D9-$C0DB`. Removing the prior `post_blit: bra post_blit` halt to let the Phase 2.3 IRQ install run produced runaway CPU and cart-RAM corruption — captured as a separate backlog item (cart-ram-corruption) and gated behind a fresh `phase24_halt` while that's investigated.

---

## [2026-05-12] query | Full-window ROM probe update

Updated `src/rom_probe.s` so the probe loop scans the full `$C000-$FEFF` cartridge window instead of only `$C000-$C0FF`. Added the `src/rom_probe.s` one-off run command to [`tooling/build-workflow.md`](tooling/build-workflow.md), matching the existing `src/main.s` assemble/pad/load pattern. After rereading the updated GDB-MCP-hosted launch instructions, built `build/rom_probe.rom` through GDB `shell`, launched `/usr/local/bin/xroar` with `-gdb`, attached through `target remote :65520`, and dumped the mismatch log. The full-window probe reported `$50` mismatches: `$C0D9-$C0DB`, `$C8B4-$C8BE`, and `$E000-$E042`. Expanded [`implementation/lessons-learned.md`](implementation/lessons-learned.md) with the observed mapping/read result.

---

## [2026-05-12] docs | GDB-MCP-hosted XRoar launch path

Clarified [`tooling/xroar.md`](tooling/xroar.md) and [`tooling/build-workflow.md`](tooling/build-workflow.md) to distinguish the Windows PowerShell sandbox, the Linux host environment available through the already-running `gdb-mcp` process, and a manually launched Windows XRoar process. Documented the working Codex path that launches XRoar via GDB's `shell` command from a GDB-MCP session, so another model should not treat "PowerShell reports no WSL distributions" as proof that runtime launch is impossible.

---

## [2026-05-12] docs | XRoar plus GDB-MCP attach runbook

Updated [`tooling/xroar.md`](tooling/xroar.md) with the round-trip workflow for building the cartridge, launching XRoar with `-gdb`, choosing `-gdb-ip 127.0.0.1` vs `-gdb-ip 0.0.0.0`, and attaching through the `gdb-mcp` MCP server using the 6809 GDB. Added troubleshooting notes for the observed `Truncated register` error, WSL/Windows bind-address timeouts, single-endpoint attach behavior, and non-6809 GDB binaries. Updated [`tooling/build-workflow.md`](tooling/build-workflow.md) to point to the full runbook and list the relevant debug flags.

---

## [2026-05-10] finding | XRoar cartridge-window read quirk at `$C0D9-$C0DB`

Created and ran a minimal ROM probe (`src/rom_probe.s`) that reads `$C000-$C0FF` before writing that range and logs mismatches to `$01FF/$0200`. Under XRoar 1.10 it reported exactly three bad reads: `$C0D9=$7E`, `$C0DA=$E2`, `$C0DB=$9D` where the cartridge image has `$00,$00,$00`. XRoar GDB traps showed the main boot `copyloop` reads those bad bytes directly, so the broad ROM-to-RAM copy stores bad source bytes rather than suffering a later overwrite. Patched `src/main.s` to skip `$C0D9-$C0DB` during the boot copy and keep that absolute range as unused padding; documented the quirk in `implementation/lessons-learned.md`.

---

## [2026-05-05] seed | Initial wiki instantiation

Created wiki scaffolding under `wiki/` for the Ladybug project (6809 assembly port of the 1981 *Lady Bug* arcade game, targeting bare-metal CoCo 3 — no NitrOS-9). Configuration adapted from the Planet Pioneers project:

- `CLAUDE.md` schema (three-layer architecture: raw sources / wiki / schema; relative-link convention; ingest/query/lint workflows).
- `index.md` content catalog with stub entries for game / platform / implementation / sources sections.
- `log.md` (this file).
- Project-root `CLAUDE.md` adapted to Ladybug.
- `.claude/skills/` role skills (project-management, business-analyst, coding-architect, debugger, qa-reviewer) copied and adapted — references to MULE/GDD/NitrOS-9/DCC replaced with Ladybug/arcade-reference/GIME/6809-toolchain.
- `.claude/settings.local.json` permissions copied (git/gh + read access under `D:/retro/`).

No raw sources ingested yet. Next steps when work begins: pick the assembler (lwasm vs asm6809 vs EDTASM), commit a `docs/` folder with arcade reference material and a CoCo 3 hardware reference, and ingest both into corresponding `sources/` pages.

---

## [2026-05-05] ingest | Lady Bug arcade — web reference

User asked for a design doc seeded from public web sources. Searched + fetched Wikipedia, Pixelated Arcade tech specs, C64-Wiki (port reference), bitvint.com, and miscellaneous web aggregations. Created [`sources/ladybug-arcade.md`](sources/ladybug-arcade.md) cataloguing what was extracted from each source and what remains uncertain. Created [`game/overview.md`](game/overview.md) — full design doc covering: playfield (240×192 arcade → CoCo 3 horizontal with HUD relocated to side panels), 20 turnstile gates, border-circuit enemy-release timer, 8 enemy types + skull hazards, scoring table (dot 10 / blue 100 / yellow 300 / red 800 / vegetables 1000–9500), heart ×2/×3/×5 multiplier, EXTRA/SPECIAL letter cycle, full 18-vegetable cycle. Ten open questions logged for user/MAME-source resolution. Two source documents could not be fetched (arcade-museum manual PDF returned binary data; StrategyWiki blocked the fetcher).

---

## [2026-05-08] ingest | Arcade gfx extraction pipeline

Built `scripts/extract_arcade_gfx.py` to decode arcade Lady Bug graphics from `ladybug.zip` (MAME romset) into indexed pixel grids + palette JSON + per-attr PNG previews under `assets/arcade/`. Decoder mirrors MAME `ladybug.cpp` `charlayout`/`spritelayout`/`ladybug_palette()` exactly. Output: 512 × 8×8 chars, 128 × 16×16 sprites, 32-color palette, 8 char color attrs, 2×8 sprite color attrs (set A from low nibble of PROM `10-1.f4`, set B from high nibble). User-confirmed colorizations: maze/HUD = char attr 0, enemies + vegetables = various Set A attrs, death-angel-wings animation = a Set B attr. Created [`sources/arcade-gfx-extraction.md`](sources/arcade-gfx-extraction.md) with the pipeline and 7-item gotchas list (palette PROM filename ≠ role, char lookup is a formula not a PROM, sprite lookup PROM serves both color sets via low/high nibbles, palette is inverted 2bpc, MAME `planes` list is MSB-first, sprite y-offsets are scrambled).

---

## [2026-05-05] decision | Design-doc scope locked for first release

User answered the 10 open questions in [`game/overview.md`](game/overview.md). Locked: HUD split panels (left = score/lives/level; right = EXTRA/SPECIAL/vegetable); `SPECIAL` reward = 10,000 points (no bonus round in v1); 3 lives + one-time 30K bonus life; single fixed maze across all stages; fixed skull count per stage. Explicitly skipped: MAME-source ingest, arcade-manual PDF ingest.

**Hearts and letters / colour cycle** (clarified across two follow-ups): hearts and letters are separate maze entities. The colour cycle is **global and instantaneous** — every coloured item on the playfield shares one colour state that flips together. Each of the three targets (EXTRA word, SPECIAL word, heart multiplier) is bound to a distinct one of the three colours; an item advances its target only when collected at the matching colour. E and A apply to whichever of EXTRA/SPECIAL is currently active. No tie-break is needed because the global single-colour state plus distinct target-colour assignments make ties structurally impossible. Specific colour-to-target mapping deferred.

Five items deferred to implementation tuning: cycle period/reset, colour-to-target mapping, enemy AI, sound design, input fallback. Rewrote `game/overview.md` HUD section, hearts-vs-letters section (twice), stage-flow, and the Decisions-locked + Deferred blocks.

---

## [2026-05-07] ingest | Tepolt — Assembly Language Programming for the Color Computer (CoCo 1/2)

Read the full Tepolt CoCo 1/2 manual (`docs/reference/Assembly Language Programming for the Color Computer.md`, ~14.7K lines). Focused on the chapters Ladybug needs: ch. 3 (MC6809E architecture, programming model, interrupt sequences), ch. 4 (addressing modes + postbyte tables), ch. 5 / Appendix B (instruction set + cycle counts), ch. 9 (SAM control bits, PIA architecture, VDG modes, IRQ/FIRQ wiring), ch. 10 (keyboard matrix, joystick fire + analog A/D loop, sound paths, cartridge connector pinout), Appendix E (dedicated-address map). Skipped chapters 1-2 (binary/hex primer), 6 (EDTASM+ — not our toolchain), 7-8 (BASIC interop).

Created [`sources/coco-asm-tepolt.md`](sources/coco-asm-tepolt.md) summarising what was extracted and what was deliberately skipped.

## [2026-05-07] ingest | Tepolt — Assembly Language Programming for the CoCo 3

Read the full Tepolt CoCo 3 addendum (`docs/reference/Assembly Language Programming for the CoCo3.md`, ~1.8K lines). Captured: GIME (ACVC) overview, palette + alternate color set, virtual/physical memory and MMU PAR sets, all hi-res text and graphics modes (CRES/HRES/VRES tables, byte formats A/B/C, scrolling), low-res mode parity with the original CoCo, ACVC interrupt sources (Vbord/Hbord/Timer/SerIn/Kybd/Cart) and IRQEN/FIRQEN registers, reset-init flow, the FF22 split, the keyboard-matrix extension for F1/F2/CTRL/ALT and joystick button 2.

Created [`sources/coco3-asm-tepolt.md`](sources/coco3-asm-tepolt.md). The earlier stub for this page never existed as a file — only as an index entry — so this is a fresh write.

## [2026-05-07] propagate | Platform pages from both Tepolt manuals

Wrote/created seven platform pages from the two Tepolt source pages:

- [`platform/6809.md`](platform/6809.md) — programming model, addressing modes, interrupt sequence summary, clock-rate selection.
- [`platform/gime.md`](platform/gime.md) — full ACVC register catalog (`$FF90-$FF9F`, `$FFA0-$FFAF`, `$FFB0-$FFBF`) plus the legacy SAM bit-flip pairs.
- [`platform/memory.md`](platform/memory.md) — virtual vs physical, PAR sets, ROM/RAM modes, dedicated address map, 128 K aliasing quirk, `$FE00-$FEFF` jump-table guarantee.
- [`platform/timing.md`](platform/timing.md) — MPU clock options, IRQ source comparison, decision to use ACVC Vbord at 60 Hz, frame-budget partition at 1.78 MHz.
- [`platform/input.md`](platform/input.md) — keyboard matrix scan, fire buttons (now two each), joystick X/Y successive-approximation A/D.
- [`platform/sound.md`](platform/sound.md) — 6-bit DAC vs PB1 square wave, selector-switch setup, planned use for melody vs SFX.
- [`platform/cartridge.md`](platform/cartridge.md) — 40-pin pinout, CART/FIRQ auto-start, the boot-time sequence Ladybug must execute.

Updated [`index.md`](index.md) to list all seven new platform pages and both source pages.

## [2026-05-08] ingest | Tooling — lwtools, xroar, toolshed + build script

User requested full build/deploy runbooks for the WSL toolchain at `~/coco-tools/{lwtools,toolshed,xroar}` plus an automation script. Created a new `wiki/tooling/` section: [`index.md`](tooling/index.md), [`lwtools.md`](tooling/lwtools.md) (lwasm 4.24, `--format=raw` invocation, padding to 16 KB, gotchas), [`xroar.md`](tooling/xroar.md) (XRoar 1.10, canonical `-machine coco3 -ram 512 -cart-rom ... -cart-autorun` profile, GDB/trace flags), [`toolshed.md`](tooling/toolshed.md) (decb/os9 — explicitly **standby**, not in active build), [`build-workflow.md`](tooling/build-workflow.md) (end-to-end runbook with manual fallbacks). Wrote [`scripts/build.sh`](../scripts/build.sh) with `build`/`run`/`clean` subcommands; smoke-tested end-to-end against a 3-byte stub (`ORG $C000 / JMP entry` → 16384-byte padded ROM). Verified Windows-host Claude can drive WSL via `wsl -d Ubuntu -- bash -lc ...`.

**Decision:** deploy is **cartridge ROM image only** (option A); toolshed kept documented but unused. Rationale: matches existing cartridge boot strategy locked 2026-05-07. Reconsider if iteration becomes cumbersome — the toolshed page documents the `.dsk`/`LOADM` fallback path so the switch is fast. OS-9 path explicitly out of scope (conflicts with bare-metal constraint in `CLAUDE.md`).

`wiki/index.md` updated: new Tooling section; old `platform/toolchain.md` and `implementation/build-workflow.md` stubs marked superseded.

## [2026-05-08] phase | Phase 2.3 — GIME hi-res 320×192×16 + MMU + FB end-to-end — passed

After Path A (16 K cart) was committed, drove Phase 2 through three sub-gates: (2.1) shadow-RAM-during-write at phys $3E verified by writing a marker pre-TY=1 and reading it back post-TY=1 (got 'Z'); (2.2) full Phase 1 boot + cart self-copy + all-RAM, IRQ-driven frame counter still ticked from RAM-resident code; (2.3) GIME hi-res mode + MMU + PARs (`$38, $30..$33, $3D, $3E, $3F`) + vert-offset `$FF9D=$C0/$FF9E=$00` → FB at phys page $30 + palette load + CRES=11 blanking trick during init + IRQ-driven mainloop FB writes. Final visible: 16-stripe palette test with bright border + flashing IRQ-driven block on top of mid-screen stripe.

**Surprise:** XRoar's default CoCo 3 monitor renders the 6-bit palette via composite NTSC encoding, not the textbook RGB `RGBrgb` 2-bits-per-channel layout. `$3F` and `$30` both display as white (different luma, same chroma point); `$0C` is blue not green-ish; etc. Recorded the empirical 6-bit-value → colour mapping in [`implementation/video-mode.md`](implementation/video-mode.md) §"XRoar palette colours — empirical (composite NTSC)" and [`implementation/lessons-learned.md`](implementation/lessons-learned.md).

**Surprise (lesser):** the IRQ-driven mainloop write at row 96 produced visible tearing on the bottom edge (~7 pixels of next-row colour mid-frame). Cause is the unsynchronised fill loop racing the GIME raster — not a bug. Vsync-aware rendering will be addressed when the renderer matures.

Filed Phase 2.2 + 2.3 boot-sequence playbook to [`implementation/lessons-learned.md`](implementation/lessons-learned.md). Updated [`implementation/roadmap.md`](implementation/roadmap.md) Phase 2 with substep status (2.1, 2.2, 2.3 done; 2.4 = render arcade tile; 2.5 = automate `build_gfx.py`).

**One iteration cost:** lwasm rejected `fcb $38, $30, $31, ...` with spaces after commas — needed `fcb $38,$30,$31,...`. Filed mentally; the `coding-conventions` page should pick this up during a future lint pass.

---

## [2026-05-08] decision | Reverted to 16 K cart after XRoar boot gate failed

Phase 2 step 1 (assumption validation) caught two issues. **(1) Shadow-RAM-during-write at phys `$3E` works** — verified by writing a marker to `$C000`, going TY=1, reading it back. Boot data-copy procedure is sound. **(2) XRoar's handling of 32 K cart files via `-cart-rom` is unverified** — built a 32 K cart with the planned `$8000-$BFFF` data + `$C000-$FEFF` code split; boot landed at BASIC `OK`, consistent with XRoar mapping only the lower 16 K of the file at `$C000` regardless of size. XRoar's manual documents `-cart-rom` only as "mapped from `$C000`" — no 32 K behaviour described.

User decision: **Path A — revert to 16 K cart for now**, defer the cart-size question until Phase 4 sprite arithmetic gives real numbers. If we then need >16 K, pivot to **software bank-switched** (XRoar `-cart-type gmc` + CoCoSDC + multi-pak — universal hardware support, ~half-day refactor, only touches boot data-copy because runtime is all-RAM regardless). Not Init0 b1-b0 = `11`, since that mode is rare in actual cart hardware AND unverified in XRoar.

Reverted: `scripts/build.sh` → `CART_BYTES=16384`. Updated [`platform/cartridge.md`](platform/cartridge.md) §"Cart size — 16 K (current); 32 K and bank-switched options deferred", boot-sequence steps; [`platform/memory.md`](platform/memory.md) cart-boot section; [`tooling/build-workflow.md`](tooling/build-workflow.md), [`tooling/xroar.md`](tooling/xroar.md) (gotcha about `-cart-rom` / 32 K), [`tooling/index.md`](tooling/index.md), [`tooling/lwtools.md`](tooling/lwtools.md); [`implementation/video-mode.md`](implementation/video-mode.md) ROM-budget update (2bpp+attr sprites back as default), [`implementation/memory-map.md`](implementation/memory-map.md) cart layout + boot data-copy procedure simplified to single-org 16 K, Phase 4 sprite-data section revised; [`implementation/roadmap.md`](implementation/roadmap.md) standing-budget denominator + Phase 1/9/10 review-gate questions. Filed both findings to [`implementation/lessons-learned.md`](implementation/lessons-learned.md).

---

## [2026-05-08] decision | Memory map for Phase 2 + Phase 10 cart-shell gate

**Memory map.** Created [`implementation/memory-map.md`](implementation/memory-map.md) covering: 8-PAR allocation post-boot (1 system, 4 FB at phys `$30-$33`, 1 game-state placeholder, 2 code at phys `$3E-$3F`); 32 K cart-ROM image structure (data section at virtual `$8000-$BFFF`, code section at `$C000-$FEFF`); boot data-copy procedure relying on shadow-RAM-during-write semantics (Init0 b1-b0=11 → self-copy `$8000-$FEFF` → TY=1; ~80 ms boot-time cost). DP at `$0200-$02FF` allocation table started.

**Tight page budget surfaced.** 8 PARs vs 8-10 wanted post-Phase-4 (sprite data is the pinch point: ~15 K of sprites won't fit in 1 PAR alongside game state + FB + code + system). Documented four resolution options — (1) sprite 2bpp+attr compression — default, (2) bank-switch sprite PAR, (3) sliding FB write window, (4) shrink code to 8 K. Decision deferred to Phase 4 when real sprite count is known.

**Two open Phase-2 implementation validations** to do at first boot: shadow-RAM-during-write actually populates phys `$3C-$3F` with cart contents; XRoar correctly maps a 32 K cart image when Init0 b1-b0=11 is set.

**Phase 10 review-gate question added** (separate from memory map): does the chosen cart shell — CoCoSDC, RetroCloud, custom — actually respond to `$8000-$BFFF` accesses in Init0=11 mode? If not, half-day pivot to a software-bank-switched cart, since bank-switching only matters during boot's data-copy phase. Updated [`implementation/roadmap.md`](implementation/roadmap.md) Phase 10.

---

## [2026-05-08] decision | Cart retargeted to 32 K (Init0 b1-b0 = 11)

User pushed back on the implicit 16 K cart limit during Phase 2 ROM-budget analysis. Reviewed real options: (1) 16 K with 2bpp+attr sprite packing — fits but ties storage format to performance, (2) 32 K cart via Init0 b1-b0 = `11` — same boot model, requires 32 K EPROM + cart shell, (3) bank-switched cart — more complex, (4) floppy — reverses locked cart-only decision. Chose **(2) 32 K cart**: removes ROM pressure for full 4bpp sprite path, keeps boot model intact, defers bank-switching as a fallback if ever needed.

Updated `scripts/build.sh` (`CART_BYTES=32768`); rebuilt — Phase 1 cart still autostarts under XRoar (16 K of code/padding + 16 K trailing $FF padding). Updated wiki: [`platform/cartridge.md`](platform/cartridge.md) §"Cart size — 32 K" + revised boot sequence (Init0 b1-b0 = `11` switch comes before all-RAM, after we take control); [`platform/memory.md`](platform/memory.md) cart-boot section; [`tooling/build-workflow.md`](tooling/build-workflow.md) (32 KB pad, updated overflow guidance); [`implementation/video-mode.md`](implementation/video-mode.md) (ROM-budget update — 4bpp sprite path now default); [`implementation/roadmap.md`](implementation/roadmap.md) (Phase-9 review-gate question + standing budget-check denominator).

Cart-shell hardware implication: standard 16 K EPROM cart shells won't work. CoCoSDC, RetroCloud cart, and similar bank-switched / SD-cart hardware emulate larger ROMs transparently — likely target for development. Real-hardware bring-up at Phase 10 needs a 32 K-capable cart shell.

---

## [2026-05-08] decision | Video mode chosen — 320×192×16

Phase 2 first task: decided GIME mode for the rest of the project. Compared 320×192 vs 256×192 at 16 colours (depths below 16 ruled out by the 3-colour-cycle subsystem, hi-res text ruled out by per-pixel needs). 320×192 wins on HUD layout (64 px per side panel = 8 tiles, vs 32 px = 4 tiles in 256-wide), aspect, and familiarity in CoCo 3 ecosystem. Cost: extra 6 144 framebuffer bytes (one MMU page) and ~25 % more sprite-blit work — accepted; we have 512 K and a dirty-rect strategy regardless.

Locked formats: 8×8 px tiles (32 bytes), 16×16 px sprites (128 bytes), framebuffer at 160 bytes/row × 192 rows = 30 720 bytes. Estimated sprite-blit budget 5 400 cycles for ~9 simultaneous entities — fits the 18 000-cycle render allocation with margin. GIME register values noted as candidates (`$FF99`=`$1E`); Tepolt Table 4-10 to be re-verified at code time. Single-buffer with sprite save-restore is the default; double-buffer reconsidered at Phase 4 only if tearing is visible.

Created [`implementation/video-mode.md`](implementation/video-mode.md) with the full analysis, layout diagram, format definitions, six deferred sub-decisions, and three named risks. Fixed a stale claim in [`sources/coco3-asm-tepolt.md`](sources/coco3-asm-tepolt.md) line 84 about HRES=4 byte counts. Updated [`index.md`](index.md).

---

## [2026-05-08] phase | Phase 1 — Boot init + 60 Hz Vbord — passed

`src/main.s` grew to 95 bytes: DP=$02, PIA interrupts quieted, GIME `Init0=$A8` (COCO legacy, MMU off, ACVC-IRQ on, force-`$FExx`=$3F), TY=1 all-RAM, R1=1 fast clock, JMP-handler installed at `$FEF7`, Vbord enabled via `$FF92` b3, I-mask cleared. IRQ handler increments a 16-bit `FRAMES` counter at `$0202` and acks via `$FF92` read. Main loop renders both bytes to `$0400/$0401` on the legacy VDG screen — observed on XRoar at expected rates (high byte ~4.27 s/cycle, low byte fast flicker). No stray IRQ/FIRQ from PIA or other GIME sources.

**Resolved deferred question:** SWI/IRQ vector collision (flagged in [`coding-conventions.md §4`](implementation/coding-conventions.md) at ingest, gated to Phase 1). No collision — SWI vectors `$FFFA/$FFF4/$FFF2` are disjoint from IRQ/FIRQ at `$FFF8/$FFF6`, and BASIC's SWI2/SWI3 use is moot in all-RAM mode. Updated coding-conventions.md to remove the warning. Filed both Phase 1 results and the SWI resolution to [`implementation/lessons-learned.md`](implementation/lessons-learned.md). Roadmap Phase 1 marked done.

---

## [2026-05-08] phase | Phase 0 — Hello cart — passed

22-byte stub at `$C000` with `FCC "DK"` autostart magic + entry code took control under XRoar via the BASIC CART/FIRQ handshake. Screen showed our 32-byte `$AA` marker on row 0 over BASIC's default `$60` green fill — no banner, no `OK` prompt. Confirmed [`platform/cartridge.md`](platform/cartridge.md)'s boot handshake description is correct as written. Filed Phase-0 finding to [`implementation/lessons-learned.md`](implementation/lessons-learned.md), including a sanity-note on CoCo VDG SG4 byte semantics. Roadmap Phase 0 marked done. Created [`src/main.s`](../src/main.s) (first source file in `src/`).

---

## [2026-05-08] phase | Phase 2.4 — first arcade tile rendered (after debugging session)

Hand-converted arcade `chars.json[432]` (dense tile that uses all four pixvals 0/1/2/3) to 32 bytes of 4bpp GIME tile data with direct pixval→palette mapping. Reassigned palette idx 0-3 to a 4-colour sub-palette (black/yellow/blue/white) per the empirical XRoar table in [video-mode.md](implementation/video-mode.md). Wrote `blit_tile` and rendered three copies on a black-cleared FB at tile coords (2,4), (10,20), (20,36). Replaced the FRAMES ticker with `sync; bra *` so the tiles remain stable while IRQ continues. ROM size 294 bytes / 16384.

**Bug found and fixed during the session:** the obvious `ldb #8` / `decb` / `bne` loop in `blit_tile` is broken because `ldd ,y++` clobbers B (D=A:B). The counter gets overwritten with tile-data low bytes each iteration. Fixed by switching to a `cmpy ,s` against an end-of-tile sentinel pushed onto the stack at entry. Filed in [implementation/lessons-learned.md](implementation/lessons-learned.md) as a recurring 6809 idiom-trap to avoid in future blit/copy loops.

A separate observation during a 64×64 solid-block diagnostic: identical write code at three FB positions produced a clean rectangle at top-left (PAR1) and bottom-right (PAR4) but a partially-striped rectangle at the middle position (PAR2). Cause unknown; probably an interaction between specific scan-line ranges and XRoar's composite-NTSC artifacting, since the 8×8 tiles render correctly. Flag for follow-up if Phase 2.5's automated tile pipeline reproduces the symptom.

Phase 2.5 will automate the chars.json → GIME tile-data conversion via `build_gfx.py`.

---

## [2026-05-08] decision | Implementation roadmap committed

User asked for a phased plan from current state to finished game with POCs and review gates. Wrote [`implementation/roadmap.md`](implementation/roadmap.md) — 11 phases (0: hello cart, 1: boot init, 2: display, 3: tile/maze, 4: input/sprite, 5: HUD/maze logic, 6: enemies, 7: letters+veg+colour cycle, 8: sound, 9: polish, 10: real hardware). Each phase has POC tasks, exit criterion, and review-gate questions. Ties to existing locked decisions ([game/overview.md](game/overview.md), [platform/cartridge.md](platform/cartridge.md), [coding-conventions.md](implementation/coding-conventions.md)) and surfaces deferred items (cycle period + colour-to-target mapping at Phase 7, scheduler choice at Phase 4, SWI/IRQ collision check at Phase 1) at the gates where they need to land. Documented standing review checklist (wiki updates, roadmap drift, ROM/cycle budget, scope) and four named risks the plan won't surface on its own.

---

## [2026-05-08] ingest | Dungeons of Daggorath cartridge source — coding idioms

User requested a scan of the DoD source under `docs/reference/DungeonsOfDaggorath-main/` (47 `.ASM` files, lwasm-compatible reconstruction by MJS over Kiyohara's 1983 original) for transferable 6809 conventions. Verified end-to-end build of the source first: `lwasm DAGGORATH.ASM` → 8192 bytes ORG `$C000`, padded to 16 KB, autoruns under XRoar via the same flow as `scripts/build.sh`. Spawned an Explore agent to extract patterns; approved findings list with the user before filing.

Created [`sources/dod-source.md`](sources/dod-source.md) (provenance, module map, naming conventions). Created [`implementation/coding-conventions.md`](implementation/coding-conventions.md) adopting six DoD idioms as Ladybug project conventions: static DP set once at boot, domain-based module split with 6-char prefixed names, table-driven dispatch with `EQU` offset records, SWI as syscall layer (with a flag to verify against GIME IRQ choices), routine header contract format (`Inputs:` / `Returns:`), banner comment style. Created [`implementation/scheduler.md`](implementation/scheduler.md) as a *candidate* pattern — DoD's TCB round-robin scheduler sketched and weighed against a flat main loop, decision deferred to implementation. Created [`implementation/lessons-learned.md`](implementation/lessons-learned.md) (was index-only, never written) with the "DoD anti-patterns we won't copy" list: tape I/O, CoCo 1/2 SAM/PIA legacy init, 3D vector-graphics macros, 24-bit fixed-point shift chains, BASIC ROM trampolines (incompatible with our locked all-RAM mode).

Updated [`index.md`](index.md) for the new pages.

---

## [2026-05-07] decision | Bare-metal boot strategy locked

Documented the Ladybug boot path: cartridge ROM at `$C000`, control taken via the BASIC reset-init's CART → PIA2 CB1 → FIRQ handshake, then immediate switch to all-RAM mode + 1.78 MHz clock + ACVC Vbord IRQ for the 60 Hz tick. We will not depend on BASIC's PIA initialisation; we re-init both PIAs ourselves. Init0 bit 3 will be set so the primary IRQ jump table at `$FEEE-$FEFF` remains reachable independently of PAR7. Rationale captured in [`platform/cartridge.md`](platform/cartridge.md).

---

## [2026-05-16] implement | WS-A milestone 2 — IRQ + keyboard + checkerboard

Tester ROM now installs a Vbord ISR at `$FEF7`, scans the PIA1 keyboard matrix each frame with edge-detected dispatch via a `(col_idx, row_mask, handler)` `key_table` (`'1'` → mode 0, `'B'` → bars, `'C'` → checker), and runs a dirty-flag-driven mainloop that calls `redraw_with_blank`. Adds [src/tester/input.s](../src/tester/input.s) and [src/tester/pat_check.s](../src/tester/pat_check.s); extends [src/tester/tester.s](../src/tester/tester.s) with PIA1 init, IRQ vector install, and mainloop. Verified by [web/scripts/probe_tester_m2.py](../web/scripts/probe_tester_m2.py): frame_ctr advances, ISR vector at `$FEF7` points to `vbord_isr`, bars FB intact, kbd_prev populated. Two new lessons-learned entries logged: XRoar gdb-stub mid-run-inspection constraints and palette-readback `$C0` artifact.

---

## [2026-05-16] probe | WS-A GIME-readback gate resolved → Option 2

Ran [`web/scripts/probe_gime_readback.py`](../web/scripts/probe_gime_readback.py) against a live `build/diag.rom` instance. XRoar's gdb stub returns sentinel `$1B` for every read of `$FF90` and `$FF98..$FF9E` regardless of writes; palette `$FFB0..$FFBF` reads back exactly, PARs `$FFA0..$FFA7` return reset-state `38..3F`. Option 1 (DirectReadStrategy) eliminated. **WS-A adopts Option 2 (ProgramStateStrategy)** — tester ROM will export `tester_mode_idx` + `tester_mode_table`. Finding recorded in [`implementation/lessons-learned.md`](implementation/lessons-learned.md); sequencing note added to [`implementation/emulator-monitor-tester.md`](implementation/emulator-monitor-tester.md) step 1.
