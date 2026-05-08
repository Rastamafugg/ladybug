---
name: Coding conventions
description: Project-level 6809 assembly conventions for Ladybug, derived from Dungeons of Daggorath's idioms.
type: convention
tags: [implementation, conventions, 6809, style]
updated: 2026-05-08
---

# Coding conventions

These are the conventions we adopt for Ladybug source under `src/`. Most are lifted from the Dungeons of Daggorath cartridge source — see [sources/dod-source.md](../sources/dod-source.md). Each convention cites the DoD evidence so a future maintainer can see the precedent.

## 1. Static direct page

DP is set **once** at boot and never changes. All hot variables (per-frame state, scratch, scheduler pointers) live in a single page so they get short addressing for free without any per-file `setdp` directive.

- DoD: [`ONCE.ASM:59-60`](../../docs/reference/DungeonsOfDaggorath-main/ONCE.ASM) — `LDA #2 / TFR A,DP`. Variables thereafter referenced by bare label, e.g. [`RANDOM.ASM:13-27`](../../docs/reference/DungeonsOfDaggorath-main/RANDOM.ASM) using `SEED`, `SEED+1`, `SEED+2`.
- For Ladybug: pick a DP page during the cartridge boot sequence (see [platform/cartridge.md](../platform/cartridge.md)), document it, and never change it.

## 2. Module decomposition by domain

Split files by **what they do**, not by data type. DoD's split: bootstrap, common-services / "OS layer," display, text/parser, per-command player handlers, world generators, RNG, static data tables.

- DoD: [`DAGGORATH.ASM:91-136`](../../docs/reference/DungeonsOfDaggorath-main/DAGGORATH.ASM) — the include order is itself documentation.
- For Ladybug: keep a clear common-services layer (renderer, input, RNG, sound, scheduler) separate from per-entity game logic (bug, skull, vegetable, score-cycle).

### File naming

- 6-char abbreviations, prefix-encoded domain (e.g. `BUG_AI.S`, `SND_FX.S`, `DAT_VEG.S`).
- Record-field offset constants use dot notation: `BUG.X`, `BUG.Y`, `BUG.LEN`.

## 3. Table-driven dispatch and data

Wherever there's a list of "things that behave the same with parameters" — commands, entities, init steps — define a record format with `EQU` offsets, build a contiguous array via macros, and iterate with `LEAX REC.LEN,X`.

- DoD records: `P.CCROW`, `P.CCTYP`, `P.CCUSE`, `P.CCOBJ`, with `CC.LEN` as stride. Iteration in [`COMCRE.ASM:67-78`](../../docs/reference/DungeonsOfDaggorath-main/COMCRE.ASM) (`CFIND`).
- DoD macro-built tables: command table built by `CMDXXX` ([`DTABAS.ASM:29-45`](../../docs/reference/DungeonsOfDaggorath-main/DTABAS.ASM)); object table by `GENXXX` / `OBJXXX`; init pairs by `INI` ([`COMDAT.ASM:55-58`](../../docs/reference/DungeonsOfDaggorath-main/COMDAT.ASM)).
- For Ladybug: bug records, vegetable cycle entries, sound-effect descriptors, and any score-cycle state belong in tables, not per-entity code.

## 4. SWI as syscall layer

Hot, ubiquitous services (render, RNG, text, sound) are reached through `SWI` followed by an inline parameter byte that indexes a service table. Avoids long `JSR` import chains and keeps per-call site one byte slimmer than a 16-bit address.

- DoD: [`COMSWI.ASM`](../../docs/reference/DungeonsOfDaggorath-main/COMSWI.ASM) — handler reads the parameter from `PC`, indexes `SWITAB`, jumps. Call sites look like `SWI / FCB <SVCID>`, e.g. [`CRETUR.ASM:62-63`](../../docs/reference/DungeonsOfDaggorath-main/CRETUR.ASM).
- For Ladybug: candidate SWI services — `SVC_RENDER`, `SVC_RNG`, `SVC_PUTC`, `SVC_PLAYSFX`, `SVC_VBLANK_WAIT`. Decide the full table when implementing the renderer.
- **Resolved 2026-05-08 (Phase 1 gate):** no collision with the GIME interrupt path. SWI/SWI2/SWI3 vectors (`$FFFA/$FFF4/$FFF2`) are disjoint from IRQ/FIRQ vectors (`$FFF8/$FFF6`); BASIC's SWI2/SWI3 use is moot in all-RAM mode. See [lessons-learned.md "SWI / IRQ vector collision"](lessons-learned.md).

## 5. Routine header contract

Every non-trivial routine starts with a banner block stating `Inputs:` and `Returns:` for every register and significant memory location it reads or writes. No prose paragraphs in the header.

DoD example, lifted verbatim from [`COMCRE.ASM:58-65`](../../docs/reference/DungeonsOfDaggorath-main/COMCRE.ASM):

```
;  CFIND: Find a creature based on position
;
;  Inputs:
;       A - Row
;       B - Column
;  Returns:
;       X - Pointer to CCB
;       Z - condition code set if search fails
```

For Ladybug: same format. Title line, blank, `Inputs:`, list, blank, `Returns:`, list. Side effects on memory or DP variables go under a third heading `Side effects:` if present.

## 6. Comment style

- Section banners use a row of `;!` or `;` — DoD uses `;!!!!!!!!!!!` for top-of-file titles ([`DAGGORATH.ASM:1-3`](../../docs/reference/DungeonsOfDaggorath-main/DAGGORATH.ASM)).
- Inline comments aligned to a fixed column. Don't restate the opcode — annotate the *intent*.
- Tag temporary scaffolding with `;TODO:` or `;FIXME:` plus a short reason.

## 7. Skip these (DoD-specific)

See [lessons-learned.md](lessons-learned.md) §"DoD anti-patterns" for the full list. Headlines: no tape I/O, no SAM/PIA legacy init, no 3D vector-graphics macros, no 24-bit fixed-point shift chains unless we add fade effects.

## Sources

- [sources/dod-source.md](../sources/dod-source.md) — overall provenance and module map.
- DoD file-line citations are inline above.
