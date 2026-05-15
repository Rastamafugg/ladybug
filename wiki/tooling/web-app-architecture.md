---
name: web/ retro-dev app architecture
description: Module split + data-layer conventions for the locally-hosted retro-dev web UI. v2 scope — extends backlog/retro-dev-web-app.md (which captured the MVP).
type: design
tags: [tooling, web, architecture]
updated: 2026-05-15
---

# web/ retro-dev app architecture

The MVP scope is at [../backlog/retro-dev-web-app.md](../backlog/retro-dev-web-app.md). This page is the v2 architectural design that incorporates: instruction annotation, register/region/symbol wiki surfaces, persistent named configurations, and snapshot save/load. Reverse-step/time-travel was explicitly deferred — see [log.md 2026-05-15](../log.md).

## Two design principles

1. **Static data lives in flat JSON under `web/data/`.** Opcode table, region map, register glossary, symbol→wiki map. Loaded once at backend startup; served verbatim to frontend on demand.
2. **Dynamic resolution lives in the backend.** "Decode bytes at PC + tell me what this will do with these regs" is computed Python-side per halt and returned as a structured Instruction + annotation; the frontend treats it as opaque.

## File layout

```
web/
├── data/
│   ├── 6809-opcodes.json           hand-curated, opcodes Ladybug emits
│   ├── 6809-indexed-postbyte.json  6809 indexed-addressing postbyte table
│   ├── 6809-regions.json           memory-map regions + wiki anchors
│   ├── 6809-registers.json         per-register + per-CC-bit doc strings
│   └── symbols.json                symbol-name → wiki anchor
├── configs/
│   └── *.json                      one per named instance configuration
├── snapshots/
│   ├── <id>.sna                    XRoar snapshot file
│   └── <id>.json                   sidecar manifest (config_id, ROM hash, PC, timestamp)
├── backend/
│   ├── opcode_table.py             load + index opcode + postbyte JSON
│   ├── decoder.py                  bytes + 6809 state → Instruction
│   ├── annotation.py               Instruction + state → annotation payload
│   ├── regions.py                  region lookup by addr
│   ├── symbols.py                  parse build/ladybug.map; nearest-symbol lookup
│   ├── configs.py                  CRUD over web/configs/*.json
│   ├── snapshots.py                save via -trap-snap; load with patched-XRoar detect
│   ├── instance.py                 [modified] config-driven launch
│   ├── instances.py                [modified] create_from_config + ephemeral synthesis
│   └── main.py                     [modified] new endpoints (decode, regions, symbols, configs, snapshot)
└── frontend/
    ├── components/
    │   ├── instance-list.js        [modified] config-aware
    │   ├── instruction-annotation.js     NEW
    │   ├── register-view.js        [modified] hover/click → reg-doc tooltip
    │   ├── memory-view.js          [modified] region shading + hex hover
    │   ├── symbol-context.js       NEW
    │   ├── config-editor.js        NEW
    │   ├── logs-view.js            [modified] add Snapshot button
    │   ├── source-view.js          unchanged
    │   └── framebuffer-view.js     unchanged (placeholder)
    ├── app.js
    ├── store.js                    [modified] configs + regions + register-doc fetching
    ├── app.css
    └── index.html
```

## API surface (additions)

| Method | Path | Purpose |
|-|-|-|
| GET | `/api/decode/{instance_id}?addr=&len=` | Decode + annotate bytes at addr against current state |
| GET | `/api/regions` | Static region map |
| GET | `/api/registers-doc` | Static register/CC doc |
| GET | `/api/symbols/lookup?addr=` | Nearest symbol + wiki anchor |
| GET POST PUT DELETE | `/api/configs[/{id}]` | Persistent configs CRUD |
| POST | `/api/instances/{id}/snapshot` | Save snapshot (terminates instance per `-trap` segfault quirk) |

WS protocol unchanged — fan-out already covers state/halt/log.

## Halt-event data flow

```
gdb *stopped
  → instance state HALTED + halt event with regs
  → frontend: parallel REST fetches
       /api/decode/{id}?addr=PC&len=4
       /api/symbols/lookup?addr=PC
       /api/instances/{id}/memory?addr=PC&len=4   (already exists)
  → instruction-annotation + symbol-context + memory-view repaint
```

## Schemas

### Opcode JSON (`web/data/6809-opcodes.json`)

Keyed by primary opcode hex byte. Page-2/3 prefixes (`$10`, `$11`) marked with `"page2": true` / `"page3": true`; nested under `10xx` / `11xx` keys.

```json
{
  "86": {
    "mnemonic": "LDA",
    "mode": "immediate",
    "length": 2,
    "cycles": 2,
    "operand_kind": "imm8",
    "cc": {"N": "bit7(result)", "Z": "result==0", "V": "0"},
    "summary": "Load A from immediate byte",
    "effect_template": "A ← #${imm8}",
    "wiki": "platform/6809.md"
  }
}
```

`operand_kind` enum: `imm8` | `imm16` | `direct` | `extended` | `indexed_postbyte` | `relative8` | `relative16` | `inherent` | `tfr_exg_postbyte` | `psh_pul_postbyte`. The decoder dispatches on this.

**`length` field.** For most addressing modes this is a fixed integer (e.g. 2 for `LDA #imm8`, 3 for `LDA $extended`). For `indexed_postbyte` opcodes the byte count depends on the postbyte, so `length` is the string `"variable"` and the decoder MUST compute the actual length by parsing the postbyte against `6809-indexed-postbyte.json` (`1 + extra_bytes` from the matched entry, plus the indexed opcode's 1-byte opcode itself, plus any page-prefix byte). Consumers must accept `int | "variable"` for this field.

**`cycles` field.** Integer for fixed-cycle opcodes. For path-dependent opcodes (notably `RTI`, where the FIRQ path takes 6 cycles and the IRQ/SWI/NMI path takes 15), the value is an object `{"min": int, "max": int, "note": str}`. Consumers must accept `int | {min, max, note}`. Indexed-mode base cycles do NOT use this form — addressing-mode cycle additions come from the postbyte table.

### Indexed-postbyte JSON (`web/data/6809-indexed-postbyte.json`)

Separate file. ~32 postbyte patterns covering `,X`, `n,X` (5/8/16-bit), `,X+`, `,X++`, `,-X`, `,--X`, `B,X`, `D,X`, indirect `[…]` variants, and PC-relative forms. Each entry: `{mask, value, form, extra_bytes, description}`.

### Region JSON (`web/data/6809-regions.json`)

```json
[
  {"lo": "0x0200", "hi": "0x02FF", "name": "DP page",
   "summary": "Direct-page hot variables. FRAMES at $0202.",
   "wiki": "implementation/memory-map.md#direct-page-allocation"},
  {"lo": "0xC000", "hi": "0xFDFF", "name": "Cart window",
   "summary": "Cart ROM virtual mapping. On XRoar 1.10 always cart-backed; on hardware switches to RAM at phys $3E-$3F post-self-copy.",
   "wiki": "implementation/memory-map.md#phase-2-mapping-current-target"}
]
```

### Config JSON (`web/configs/<id>.json`)

```json
{
  "id": "fresh-boot-default",
  "name": "Fresh Boot",
  "rom_path": "build/ladybug.rom",
  "launch_kind": "fresh_boot",
  "snapshot_path": null,
  "halt_on_first_instruction": false,
  "gdb_enabled": true,
  "machine": "coco3",
  "extra_xroar_flags": []
}
```

`halt_on_first_instruction` validated at save: meaningful only when `launch_kind == from_snapshot && gdb_enabled == true`.

### Snapshot manifest (`web/snapshots/<id>.json`)

```json
{"config_id": "...", "rom_sha256": "...", "capture_pc": 49340, "captured_at": "2026-05-15T13:42:00Z"}
```

ROM-hash check at load surfaces a warning on mismatch.

## Wiki-content sourcing convention

**Hybrid.** Short `summary` field inline in JSON for fast tooltip rendering; `wiki` field is a deep link. The JSON's `summary` is the canonical UI surface text and is authored deliberately. No "always-fetch wiki on hover" pattern.

## XRoar-patch dependency handling

Snapshot-load-with-debug needs the `SO_REUSEADDR` patch ([../backlog/xroar-load-gdb-patch.md](../backlog/xroar-load-gdb-patch.md)). No version probe — design is **attempt-and-detect**:

- On `from_snapshot + gdb_enabled` launch, the existing 4 s wait-then-attach path naturally exposes the bind failure. The XRoar log line `[gdb] WARNING: bind ... failed` is captured by `_pump_xroar_log` and parsed to set a specific error state on the instance: *"snapshot+debug requires the SO_REUSEADDR XRoar patch — see wiki/backlog/xroar-load-gdb-patch.md."*
- `from_snapshot + gdb_disabled` always works (no listener attempt).

## Compliance with documented XRoar quirks

- **`-trap` segfaults after write** → snapshot save is **instance-terminating**. UI surfaces this; endpoint returns success only after the file is on disk and instance state transitions to STOPPED.
- **Cart-window writes are no-ops on XRoar 1.10** ([../implementation/memory-map.md §Important](../implementation/memory-map.md)) → annotation engine flags this when the target ea lies in `$C000-$FDFF`: appends "(write is a no-op on XRoar 1.10 — cart window)".
- **Single-active-client / vMustReplyEmpty / no-TCP-probe / raw-stdin attach** — all already honored in `gdb_session.py`. No changes.

## Decisions and rationale

- **3-layer decode pipeline (opcode_table → decoder → annotation)** rather than a single module. Rationale: each layer has independent testability; the opcode table evolves independently of decoder logic; annotation prose authoring is decoupled from byte parsing.
- **Flat snapshot directory + sidecar manifest** rather than directory-per-config. Rationale: simpler listing and ROM-mismatch validation; manifest carries the config_id link.
- **Indexed-postbyte table as a separate JSON** rather than inlined per opcode. Rationale: the ~32 postbyte forms are their own little universe; inlining would multiply identical logic across every indexed opcode.
- **Time-travel deferred** — see [log.md 2026-05-15](../log.md). No record/replay infrastructure in v2.
- **Configs as per-file JSON** rather than single instances.json. Rationale: git-friendlier for individual edits and history.

## Sources

- [../backlog/retro-dev-web-app.md](../backlog/retro-dev-web-app.md) — MVP scope this page extends
- [../backlog/xroar-load-gdb-patch.md](../backlog/xroar-load-gdb-patch.md) — snapshot-load-with-debug dependency
- [../platform/6809.md](../platform/6809.md) — addressing modes the opcode table must enumerate
- [../implementation/memory-map.md](../implementation/memory-map.md) — region map authority
- [./xroar.md](xroar.md) — gdb-attach gotchas already honored
