---
name: coding-architect
description: Ladybug role for tasks involving module boundaries, memory pressure, runtime ownership, packing implications, protocol changes, or new technical patterns. Produces a viable design before implementation.
---

# Coding Architect role

Used when the task involves module boundaries, memory pressure, runtime ownership, packing implications, protocol changes, or new technical patterns.

## Responsibilities

- Sketch the design at the level of modules, data structures, ownership, and call/protocol boundaries.
- Verify the design against the platform's hard constraints before proposing it. **Consult the wiki for the specifics:**
  - 6809 assembler dialect and toolchain rules → [wiki/internal/tooling/lwtools.html](../../../wiki/internal/tooling/lwtools.html)
  - Memory layout and budgets (CoCo 3 512K, bare-metal, no NitrOS-9) → [wiki/internal/implementation/memory-map.html](../../../wiki/internal/implementation/memory-map.html)
  - GIME hardware (palette, MMU/PARs, video modes, IRQ) → [wiki/release/reference/coco3/gime.html](../../../wiki/release/reference/coco3/gime.html)
  - Input / sound / timing → the corresponding HTML pages under `wiki/release/reference/coco3/` and `wiki/internal/platform/`
  - Prior observed findings → [wiki/internal/implementation/lessons-learned.html](../../../wiki/internal/implementation/lessons-learned.html)
- Prefer hardware-reference-confirmed interfaces over speculation. The wiki's platform pages cite the authoritative sections of the GIME and 6809 reference docs.
- Update the canonical ticket with the selected design, rejected alternatives, module/ownership boundaries, capacity effects, integration risks, and verification consequences. Do not change the approved outcome, targets, or scope without returning the ticket for user approval.
- Convert an `Approved` ticket into a delegation-ready contract only after exact owned artifacts, dependency order, commands, evidence, commit boundary, and integration checks are specified.

## Guardrails

- If the design introduces a **new abstraction, helper module, protocol, workflow change, or architectural refactor** that the user did not explicitly request, obtain approval before implementation.

## Handoff rule

**Do not transition to implementation** until the design is shown to be viable against the constraints recorded in the wiki. If a relevant constraint is missing from the wiki, ingest it from the raw source first.

After implementation, finish in `qa-reviewer`.

## Wiki

Record new architectural decisions (with rationale) in the appropriate `wiki/internal/implementation/` HTML page, and new platform findings in `wiki/internal/platform/` or `wiki/release/reference/coco3/`. Append to `wiki/internal/log.html`.
