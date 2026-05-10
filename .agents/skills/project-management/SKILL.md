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

## Step 2 — Route

Pick exactly one next role:

- **`business-analyst`** — task is ambiguous, requirement-heavy, behavior-changing, or likely to depend on edge-case clarification.
- **`coding-architect`** — task involves module boundaries, memory pressure, runtime ownership, packing implications, protocol changes, or new technical patterns.
- **`debugger`** — task begins from a reported error, unexpected runtime behavior, failed output, or an unverified regression.
- **Direct implementation** — only when the requested code change is narrow, already approved, and sufficiently specified.
- **`qa-reviewer`** — task is primarily about verification, review, regression checking, acceptance, or completion readiness.

## Step 3 — Guardrails before handoff

- If the task would introduce a new abstraction, helper module, protocol, workflow change, or architectural refactor that the user did not explicitly request, **obtain approval before implementation**.
- After any implementation task, finish in `qa-reviewer`.

## Output of this role

A short classification block naming objective, scope, affected artifacts, and the next role — then invoke that role's skill.
