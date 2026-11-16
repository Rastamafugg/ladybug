---
name: project-management
description: The mandatory first role for every new task on Ladybug. Classifies the task, sets scope, identifies affected artifacts, and routes to the next role. Invoke at the start of any new task before coding, analysis, design, or debugging begins.
---

# Project Management role

This is the **first role for every new task** on Ladybug. Do not begin coding, architectural design, analysis, or debugging until this role has run.

## Step 1 — Classify

Determine and state explicitly:

1. **The task objective** — what outcome the user wants.
2. **The scope boundaries** — what is in and out of scope.
3. **The affected code, docs, scripts, and workflow artifacts** — concrete files/paths.
4. **The most appropriate next role** — using the routing criteria below.
5. **The ticket disposition** — identify an existing ticket, create a `Draft`/`Proposed` ticket for substantive new work, or state why the request is a minor query that needs no ticket.
6. **The cost class** — for bug work, use the eligibility definitions in [Bug cost classes](#bug-cost-classes) and state the risks that determine verification scope.
7. **The smallest sufficient verification set** — map each proposed scenario to a distinct identified risk and reject redundant mode/owner/phase combinations.
8. **Test sign-off** — apply [DOC-014](../../../wiki/internal/tickets/doc-014-test-signoff-contract.html#card). Embed a card for every new/materially changed gate: purpose/risk/type, controlled setup and identities, independent expected result/oracle, justified tolerance and negative control, exact command/prerequisites, entire-phase deadline and bounded cost, evidence/result classes, automated/manual split, approval and owner. Qualify relevant existing gates against their baseline before reuse; do not require a whole-suite rerun. For a new regression check, good/broken fixtures qualify the harness even when the target defect still fails.
9. **Manual-session applicability** — apply [DOC-014's manual-session rule](../../../wiki/internal/tickets/doc-014-test-signoff-contract.html#manual-session-policy). Do not require a duration, deadline or agent monitoring for the user's session unless requested. Retain the approved bounds and requirements of automated preparation or observation; missing manual observations remain pending.

For each proposed gate, classify it as a recurring regression check or one-time repair/migration evidence. For a recurring check, name the future failure it is meant to catch. Treat fixed fixture values as test inputs, not product requirements, unless approved behavior makes them requirements. If no continuing risk needs the check, record its one-time result rather than making it a routine gate.

For behavior changes, record the natural user-visible sequence and state whether the request adds behavior or replaces an existing default owner. Name the displaced owner or path.

For assembly changes, identify generated or exported symbols affected by the edit. Trace build aliases to their owner and include the correct source-reference import/routine records, primary-source DOC-002 mirror, and new routine-catalog semantic anchor where needed in the Ready artifact list. Record when the automated source-documentation audit runs; a post-build audit is not a pre-build check.

Consult [the ticket workflow](../../../wiki/internal/tickets/workflow.html) and [active ticket index](../../../wiki/internal/tickets/index.html) before routing. Do not duplicate an existing ticket; update it or link the relationship.

### Bug cost classes

Classify bugs before preparing the assignment:

- **Compact** requires a confirmed cause, an existing implementation pattern, no new runtime ownership or protocol, no loader/MMU/mapping change, no hard-boundary pressure, at most two projected production files, and no unresolved behavior question.
- **Standard** covers a bounded change that fails one or more Compact conditions but does not introduce a new technical pattern or material architectural risk.
- **High-risk** covers runtime ownership, protocol, loader/MMU/mapping, hard memory or timing boundaries, persistent-framebuffer interaction, cross-phase handoffs, or unresolved corruption.

Keep the user-facing classification brief and explain the specific risk in plain language. If the boundary is unclear, route to the relevant specialist before recommending implementation.

## Step 2 — Route

Pick exactly one next role:

- **`business-analyst`** — task is ambiguous, requirement-heavy, behavior-changing, or likely to depend on edge-case clarification.
- **`coding-architect`** — task involves module boundaries, memory pressure, runtime ownership, packing implications, protocol changes, or new technical patterns.
- **`debugger`** — task begins from a reported error, unexpected runtime behavior, failed output, or an unverified regression.
- **Direct implementation** — when the requested code change is narrow, already approved, sufficiently specified, and Ready. This is the default execution route for Compact bugs.
- **`qa-reviewer`** — task is primarily about verification, review, regression checking, acceptance, or completion readiness.

## Step 3 — Guardrails before handoff

- Do not classify a bug as Compact when it changes runtime ownership, protocols, loader/MMU/mapping behavior, hard memory or timing boundaries, persistent-framebuffer interaction, cross-phase handoffs, or unresolved corruption.
- Use cost classes to select verification proportional to risk. Do not apply weekly-token projections or percentage stop gates; historical ticket ceilings are superseded by the current project policy.
- Do not require a worktree, delegation, exhaustive scenario matrix, or new ticket-specific harness for a Compact bug unless a named risk requires it.
- If the task would introduce a new abstraction, helper module, protocol, workflow change, or architectural refactor that the user did not explicitly request, **obtain approval before implementation**.
- For a runtime symptom, route to debugger before architecture or platform-defect analysis. A user correction to expected behavior invalidates conflicting assumptions; update the ticket's observed/expected sequence before more implementation or verification.
- After any implementation task, finish in `qa-reviewer`.
- Do not route implementation until the canonical ticket is `Approved` and its dependencies, assignment contract, and verification plan make it `Ready`.
- Missing test-card approval or an unqualified gating setup prevents `Ready` and dispatch. Do not depend on random enemy movement to find a fixture; select a reviewed legal predecessor or approved manual coverage, keeping required natural progression separate. A fixed seed does not qualify unrelated chooser/input/clock/framebuffer state.
- Executors cannot invent additional gates, widen targets/tolerances or state-write authority, change automated/manual coverage, or repair unrelated test/product debt. Material contract/cost-risk changes require renewed approval; ordinary mechanics within the approved card do not. Label and bound non-gating diagnostics. Historical exceptions permit named failures without requiring their persistence.
- Preserve the existing two-rejected-probe/two-tool-timeout/material-expansion reassessment boundary. Report product assertion failure, setup/observer failure, missing coverage, approved waiver and pending manual result separately. Stop rather than retry until pass or expand a route-search framework.
- When several tickets are candidates, state their dependency order and select the highest-ordered ready item. Parallel delegation requires independent scope and non-overlapping writable artifacts.

## Output of this role

A short classification block naming objective, scope, affected artifacts, ticket/status, cost class, smallest sufficient verification set, ordering or dependencies, and the next role — then invoke that role's skill.
