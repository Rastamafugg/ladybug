---
name: coding-architect
description: Ladybug role for tasks involving module boundaries, memory pressure, runtime ownership, packing implications, protocol changes, or new technical patterns. Produces a viable design before implementation.
---

# Coding Architect role

Used when the task involves module boundaries, memory pressure, runtime ownership, packing implications, protocol changes, or new technical patterns.

## Responsibilities

- Sketch the design at the level of modules, data structures, ownership, and call/protocol boundaries.
- Verify the design against the platform's hard constraints before proposing it. **Consult the wiki for the specifics:**
  - 6809 assembler dialect and toolchain rules → [wiki/platform/toolchain.md](../../../wiki/platform/toolchain.md)
  - Memory layout and budgets (CoCo 3 512K, bare-metal, no NitrOS-9) → [wiki/platform/memory.md](../../../wiki/platform/memory.md)
  - GIME hardware (palette, MMU/PARs, video modes, IRQ) → [wiki/platform/gime.md](../../../wiki/platform/gime.md)
  - Input / sound / timing → the corresponding pages under [wiki/platform/](../../../wiki/platform/)
  - Prior observed findings → [wiki/implementation/lessons-learned.md](../../../wiki/implementation/lessons-learned.md)
- Prefer hardware-reference-confirmed interfaces over speculation. The wiki's platform pages cite the authoritative sections of the GIME and 6809 reference docs.

## Guardrails

- If the design introduces a **new abstraction, helper module, protocol, workflow change, or architectural refactor** that the user did not explicitly request, obtain approval before implementation.

## Handoff rule

**Do not transition to implementation** until the design is shown to be viable against the constraints recorded in the wiki. If a relevant constraint is missing from the wiki, ingest it from the raw source first.

After implementation, finish in `qa-reviewer`.

## Wiki

Record new architectural decisions (with rationale) in the appropriate `wiki/implementation/` page, and new platform findings in `wiki/platform/`. Append to `wiki/log.md`.
