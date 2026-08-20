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
6. **The cost class and ceiling** — classify bug work as Compact, Standard, or High-risk using `AGENTS.md`; record the projected weekly-token share and applicable approval ceiling.
7. **The smallest sufficient verification set** — map each proposed scenario to a distinct identified risk and reject redundant mode/owner/phase combinations.

For behavior changes, record the natural user-visible sequence and state whether the request adds behavior or replaces an existing default owner. Name the displaced owner or path.

Consult [the ticket workflow](../../../wiki/internal/tickets/workflow.html) and [active ticket index](../../../wiki/internal/tickets/index.html) before routing. Do not duplicate an existing ticket; update it or link the relationship.

## Step 2 — Route

Pick exactly one next role:

- **`business-analyst`** — task is ambiguous, requirement-heavy, behavior-changing, or likely to depend on edge-case clarification.
- **`coding-architect`** — task involves module boundaries, memory pressure, runtime ownership, packing implications, protocol changes, or new technical patterns.
- **`debugger`** — task begins from a reported error, unexpected runtime behavior, failed output, or an unverified regression.
- **Direct implementation** — when the requested code change is narrow, already approved, sufficiently specified, and Ready. This is the default execution route for Compact bugs.
- **`qa-reviewer`** — task is primarily about verification, review, regression checking, acceptance, or completion readiness.

## Step 3 — Guardrails before handoff

- Do not classify a bug as Compact when it changes runtime ownership, protocols, loader/MMU/mapping behavior, hard memory or timing boundaries, persistent-framebuffer interaction, cross-phase handoffs, or unresolved corruption.
- If the projected work approaches its cost ceiling, stop before implementation or further investigation and obtain approval for a revised ceiling or reduced scope.
- Do not require a worktree, delegation, exhaustive scenario matrix, or new ticket-specific harness for a Compact bug unless a named risk requires it.
- If the task would introduce a new abstraction, helper module, protocol, workflow change, or architectural refactor that the user did not explicitly request, **obtain approval before implementation**.
- For a runtime symptom, route to debugger before architecture or platform-defect analysis. A user correction to expected behavior invalidates conflicting assumptions; update the ticket's observed/expected sequence before more implementation or verification.
- After any implementation task, finish in `qa-reviewer`.
- Do not route implementation until the canonical ticket is `Approved` and its dependencies, assignment contract, and verification plan make it `Ready`.
- When several tickets are candidates, state their dependency order and select the highest-ordered ready item. Parallel delegation requires independent scope and non-overlapping writable artifacts.

## Output of this role

A short classification block naming objective, scope, affected artifacts, ticket/status, cost class, budget ceiling, smallest sufficient verification set, ordering or dependencies, and the next role — then invoke that role's skill.
