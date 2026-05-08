---
name: Dungeons of Daggorath — cartridge source
description: 1983 cartridge port source (Keith S. Kiyohara / Unified Technologies, lwasm-compatible reconstruction by MJS, 2022). Mined for transferable 6809 idioms.
type: source
tags: [reference, 6809, coco-cartridge, idioms]
updated: 2026-05-08
---

# Dungeons of Daggorath — source archive

Located at [`docs/reference/DungeonsOfDaggorath-main/`](../../docs/reference/DungeonsOfDaggorath-main/). 47 `.ASM` files plus `missing-macros.asm`. Entry point [`DAGGORATH.ASM`](../../docs/reference/DungeonsOfDaggorath-main/DAGGORATH.ASM) which `INCLUDE`s every module in dependency order.

Verified buildable end-to-end with our toolchain on 2026-05-08: `lwasm -9 --format=raw DAGGORATH.ASM` → 8192 bytes, ORG `$C000`. Pads to 16 KB and autoruns under XRoar via the same flow as `scripts/build.sh`.

## Provenance

- **Original:** 1983 cartridge release, Unified Technologies. Code header preserves the original copyright. Source published under a grant of license — see `grant_of_license.png` in the source folder.
- **Reconstruction:** Macro invocations were largely unexpanded from the original listings; some macros that lacked definitions were recreated and isolated in `missing-macros.asm` (per the comment at [DAGGORATH.ASM:81-89](../../docs/reference/DungeonsOfDaggorath-main/DAGGORATH.ASM)).
- **lwasm compatibility:** Single pragma at top — `pragma nodollarlocal,6809` — then plain `INCLUDE` chain.

## Module map (functional grouping)

| Domain | Files |
|-|-|
| Bootstrap & top-level | `DAGGORATH.ASM`, `ONCE.ASM` |
| Common services / OS layer | `COMMON.ASM`, `COMSWI.ASM`, `COMTXT.ASM`, `COMCRE.ASM`, `COMPLR.ASM`, `COMDAT.ASM` |
| Definitions | `CD.ASM` (common), `missing-macros.asm` |
| Display / rendering | `VCTLST.ASM`, `VECTOR.ASM`, `VIEWER.ASM`, `EXPAND.ASM`, `CLEAR.ASM`, `PUPDAT.ASM`, `STATUS.ASM`, `MAPPER.ASM`, `SWCHAR.ASM` |
| Text / parser | `TXTSER.ASM`, `PARSER.ASM`, `TOKEN.ASM` |
| Game logic — player commands | `PATTK.ASM`, `PCLIMB.ASM`, `PEXAM.ASM`, `PGET.ASM`, `PINCAN.ASM`, `PLOOK.ASM`, `PREVEA.ASM`, `PTURN.ASM`, `PUSE.ASM` |
| Game logic — world / creatures | `CRETUR.ASM`, `OBIRTH.ASM`, `NEWLVL.ASM`, `DGNGEN.ASM`, `HUMAN.ASM`, `HUPDAT.ASM` |
| Math / RNG / misc | `RANDOM.ASM`, `MISC.ASM`, `SOUNDS.ASM` |
| Static data tables | `DTABAS.ASM`, `VARC.ASM`, `VOBJ.ASM`, `VERT.ASM`, `D3.ASM`, `D4.ASM`, `KSK.ASM` |
| **Skip — not transferable** | `PZTAPE.ASM` (cassette I/O), `VCTLST.ASM` macros (3D vector graphics) |

## Naming conventions observed

- File names: 6-char abbreviations. Prefix encodes domain — `P*` = player command, `COM*` = common service, `V*` = vector data table.
- Labels: ALL CAPS, dot-notation for record-field offsets (`P.CCROW`, `P.CCTYP`, `CC.LEN`).
- Record-size constants: `<RECORD>.LEN` (e.g. `OC.LEN`, `CC.LEN`).

## What we mined for

See [implementation/coding-conventions.md](../implementation/coding-conventions.md) for the patterns we are adopting, [implementation/scheduler.md](../implementation/scheduler.md) for the TCB scheduler sketch, and [implementation/lessons-learned.md](../implementation/lessons-learned.md) for DoD-specific patterns we are explicitly **not** copying.

## Sources

- [`DAGGORATH.ASM:78-136`](../../docs/reference/DungeonsOfDaggorath-main/DAGGORATH.ASM) — the include manifest.
- [`missing-macros.asm`](../../docs/reference/DungeonsOfDaggorath-main/missing-macros.asm) — recreated macro definitions.
- [`grant_of_license.png`](../../docs/reference/DungeonsOfDaggorath-main/grant_of_license.png) — license grant from Douglas J. Morgan / Richard Daniels (2008-era release).
