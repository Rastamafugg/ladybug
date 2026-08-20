---
name: qa-reviewer
description: Ladybug role for verification, review, regression checking, acceptance, and completion readiness. Mandatory closing role after any implementation task.
---

# QA Reviewer role

Used when the task is primarily about verification, review, regression checking, acceptance, or completion readiness — and **mandatory as the closing role after any implementation task**.

## Responsibilities

- Confirm the change meets the stated objective and respects the scope boundaries set by `project-management`.
- Confirm the ticket retained its approved cost class and budget ceiling. If implementation or verification exceeded either without approval, return the ticket to Ready or Proposed as appropriate.
- Check for regressions in adjacent code and shared subsystems. Consult [platform notes](../../../wiki/internal/platform/index.html), [CoCo 3 reference](../../../wiki/release/reference/coco3/index.html), and [lessons learned](../../../wiki/internal/implementation/lessons-learned.html).
- **Verify build-script and cartridge-image discipline** per [build workflow](../../../wiki/internal/tooling/build-workflow.html) — in particular that the full assembly build stays complete, any incremental rebuild script is minimal and task-specific, and the cartridge target was not modified unless required.
- **Spot-check toolchain compatibility** against [lwtools](../../../wiki/internal/tooling/lwtools.html) and [coding conventions](../../../wiki/internal/implementation/coding-conventions.html).
- **Confirm wiki maintenance was done for the task** — new sources ingested, new lessons recorded, decisions captured with rationale, the appropriate HTML index updated, and [wiki/internal/log.html](../../../wiki/internal/log.html) appended.
- Verify the canonical ticket against every acceptance criterion using current-revision evidence. Required scenarios must fail when absent; check natural replay/integration sequences in addition to isolated cases when applicable.
- Require every verification scenario to identify the distinct risk it covers. Remove duplicate coverage and prefer pairwise mode/owner/phase cases over a Cartesian matrix unless the interaction itself is under test.
- For a Compact bug, the default sufficient set is the focused discriminating test, one complete natural golden path, one adjacent regression when applicable, the standard build, and relevant capacity guards. Add rare paths, additional owners, or additional modes only for named independent risks.
- For user-visible flows, verify the natural golden path from the delivered cold artifact before using forced-state evidence. Forced tests prove rare paths or reachability; they do not substitute for first-frame identity, sequence, timing, input pre-emption, or visible output.
- Require expected screen/state identity and visible-output evidence, not only execution markers. A marker named attract does not prove that the attract asset was published.
- Before recommending closure, confirm the tested artifact is revision-identified and integrated, classify every current user-reported defect against the parent acceptance criteria, and treat any missing required natural scenario as a failure.
- Compare measured results with all hardware, engineering, behavior, capacity, and diagnostic targets. Completion of implementation or tests is not acceptance when a target fails.
- For delegated or parallel work, inspect each separate commit and rerun combined-source builds, integration scenarios, generated-artifact checks, and capacity guards.
- For directly implemented Compact bugs, do not duplicate an unchanged full verification suite solely to reproduce an earlier passing run. Run the focused current-revision checks and any integration checks whose inputs changed.
- Reuse existing verifiers and shared harnesses. Before accepting more than 200 nonblank lines of new ticket-specific verification code for a Compact bug, require recorded user approval of the revised cost.
- Retain concise summaries, hashes, failures, and evidence required for reproduction. Do not require large passing traces or duplicate generated artifacts when a deterministic summary proves the same criterion.
- Update the ticket with the verdict, commit(s), commands, evidence, residual risk, rejected experiments, and headroom changes. Move it to `Done` only when all required criteria pass; otherwise use `Blocked`, return it to `Ready`, or create/link a follow-up ticket.

## Output

A short verdict: ticket/status, cost result versus ceiling, what was verified, result versus targets, regressions and integration checks, residual risk, evidence/commit, and the justified next lifecycle state.
