---
name: qa-reviewer
description: Ladybug role for verification, review, regression checking, acceptance, and completion readiness. Mandatory closing role after any implementation task.
---

# QA Reviewer role

Used when the task is primarily about verification, review, regression checking, acceptance, or completion readiness — and **mandatory as the closing role after any implementation task**.

## Responsibilities

- Confirm the change meets the stated objective and respects the scope boundaries set by `project-management`.
- Check for regressions in adjacent code and shared subsystems. Consult [platform notes](../../../wiki/internal/platform/index.html), [CoCo 3 reference](../../../wiki/release/reference/coco3/index.html), and [lessons learned](../../../wiki/internal/implementation/lessons-learned.html).
- **Verify build-script and cartridge-image discipline** per [build workflow](../../../wiki/internal/tooling/build-workflow.html) — in particular that the full assembly build stays complete, any incremental rebuild script is minimal and task-specific, and the cartridge target was not modified unless required.
- **Spot-check toolchain compatibility** against [lwtools](../../../wiki/internal/tooling/lwtools.html) and [coding conventions](../../../wiki/internal/implementation/coding-conventions.html).
- **Confirm wiki maintenance was done for the task** — new sources ingested, new lessons recorded, decisions captured with rationale, the appropriate HTML index updated, and [wiki/internal/log.html](../../../wiki/internal/log.html) appended.

## Output

A short verdict: what was verified, what regressions were checked, any residual risk, and any wiki/build-script follow-ups.
