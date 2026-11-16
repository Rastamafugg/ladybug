# Ladybug

A 6809 assembly-language port of the 1981 arcade game *Lady Bug* (Universal) for the Tandy Color Computer 3 (512K), running on **native hardware only — no NitrOS-9**.

## Where knowledge lives

The project has an **LLM-maintained, hand-authored HTML wiki at [wiki/](wiki/)** — read [wiki/index.html](wiki/index.html) first for the catalog. It is the source of truth for:

- Game design (derived from arcade reference material under `docs/`)
- Platform / technology (CoCo 3, 6809, GIME hardware, bare-metal memory map, timing, sound, input)
- Implementation (data structures, **lessons learned**, **build workflow**)
- Raw source pointers (design docs, hardware reference manuals)

**Always consult the wiki before answering or coding.** If a needed fact isn't there yet, read the raw source under `docs/` or `src/` and ingest the finding back into the wiki (see Wiki Maintenance below).

### Reuse Existing Project Work

Before recommending a new approach to meet a project need, inspect existing project work that may already solve or partly solve it.

Trace the closest relevant precedent through the steps that matter to the need. State what can be reused, what requirements it meets, and what gaps or constraints remain.

Recommend a different approach only when checked evidence shows the existing work cannot meet an identified requirement. Name the evidence and distinguish source facts, inferences, and unknowns. If no relevant precedent is found, say what was checked and what remains unknown.

## Current Development Workflow

- Start new functionality, bug fixes, performance work, tooling changes, and substantive documentation work through the [ticket workflow](wiki/internal/tickets/workflow.html). The [ticket index](wiki/internal/tickets/index.html) is the active work queue; the roadmap remains the phase-level product plan.
- For bug cost class and eligibility, use the project-management skill. For ticket verification scope and scenario coverage, use the [ticket workflow](wiki/internal/tickets/workflow.html) and QA reviewer skill.
- Do not implement a proposed ticket until the user has approved it. Approval fixes the outcome, scope, targets, and acceptance criteria. A ticket becomes `Ready` only after dependencies, assignment details, and verification commands are complete.
- For assembly changes involving generated or exported symbols, use the coding-architect skill and [DOC-002](wiki/internal/tickets/doc-002-assembly-source-traceability.html); the role skill owns the source-trace procedure.
- Resume game work from the highest-ordered `Ready` ticket that is consistent with the active phase in [wiki/internal/implementation/roadmap.html](wiki/internal/implementation/roadmap.html).
- For game-code builds and runtime inspection, follow the [build workflow](wiki/internal/tooling/build-workflow.html) and [XRoar runbook](wiki/internal/tooling/xroar.html#gdb-mcp-round-trip); use only commands included in the approved assignment.
- The `web/` app and patched XRoar `-monitor` stack are preserved but deferred. Do not extend them unless the user explicitly reactivates that work.
- The deferred XRoar bridge status is recorded in [the MCP/XRoar backlog](wiki/internal/backlog/mcp-xroar-server.html).

## Instruction Scope

This file contains project-wide instructions. Task-specific procedures are owned by the relevant role skill or linked workflow document; read those details only when the task is routed to that role or uses that workflow. Do not copy specialist procedures into this file when their authoritative source already covers them.

## Roles & Routing

Every new task begins in the `project-management` role, which classifies the task and routes to one of the specialist roles. Each role has a skill file; read and use the matching file under `.agents/skills/` when routed to that role:

- `project-management` — **mandatory first role**; classify objective/scope/affected-artifacts and pick the next role.
- `business-analyst` — ambiguous, requirement-heavy, behavior-changing, or edge-case-dependent tasks.
- `coding-architect` — module boundaries, memory/packing, runtime ownership, protocols, new technical patterns.
- `debugger` — reported error, unexpected runtime behavior, failed output, unverified regression.
- `qa-reviewer` — verification, review, regression checking, acceptance; **mandatory closing role after any implementation**.

Do not begin coding until `project-management` has run. Each role skill contains its own handoff rules and guardrails.

## Response and Work-Approval Standard

### Communication clarity

- Use plain language and define technical terms or abbreviations when they first matter.
- State what is known, what is inferred, and what remains unknown. Label calculations, estimates, and projections.
- Before the first table in a conversation, define every non-obvious row/column label, unit, scenario or owner, baseline, target, margin, and pass/fail rule; state whether each number is a maximum, minimum, average, single observation, estimate, projection, or requirement, and cite the source revision or artifact when material.
- Give enough context for a finding or next step to be understood without repeating the full work contract.

### Shared work control

- Surface proposed behavior, architecture, asset-removal, or acceptance changes before including them in approved work.
- Carry accepted corrections into later plans and authoritative records. Preserve existing user edits when changing shared files.
- Report failed steps, evidence, missing coverage, and unresolved criteria accurately. Completion of implementation or testing alone does not mean acceptance.
- Do not implement a ticket until the user has approved its outcome and scope and the ticket is Ready.
- After implementation, use the QA reviewer role before recommending completion.

### Conditional procedures

Read only the procedure relevant to the task:

- Bug intake and cost-class eligibility: [project-management skill](.agents/skills/project-management/SKILL.md).
- Runtime diagnosis, live-byte comparison, probe bounds, and hardware escalation: [debugger skill](.agents/skills/debugger/SKILL.md).
- Generated/exported assembly symbols and routine contracts: [coding-architect skill](.agents/skills/coding-architect/SKILL.md), [QA reviewer skill](.agents/skills/qa-reviewer/SKILL.md), and [DOC-002](wiki/internal/tickets/doc-002-assembly-source-traceability.html).
- Gating scenarios, manual sessions, verification evidence, ticket lifecycle, assignments, and delegation: [DOC-014](wiki/internal/tickets/doc-014-test-signoff-contract.html) and the [ticket workflow](wiki/internal/tickets/workflow.html).
- Wiki structure, ingest, query, lint, links, and logs: [wiki/AGENTS.md](wiki/AGENTS.md).

These linked sources own their detailed procedures. Do not load every specialist procedure for an unrelated task.

## Ticket and Delegation Rules

- Ticket IDs use `<TYPE>-NNN`; one HTML page under `wiki/internal/tickets/` is canonical for each ticket.
- Only explicit user approval advances a ticket from `Proposed` to `Approved`. Do not begin implementation until the ticket is `Ready`.
- A material change to an approved outcome, scope, target, acceptance criterion, dependency order, or risk profile returns the ticket to `Proposed` for renewed approval.
- Delegate only `Ready` tickets. The parent agent owns integration and final status updates.
- Use the [ticket workflow](wiki/internal/tickets/workflow.html) and [ticket template](wiki/internal/tickets/template.html) for required ticket content, verification plans, assignment details, evidence retention, and completion reports.

## Wiki Maintenance

The wiki is the project source of truth. When changing or authoring wiki content, follow [wiki/AGENTS.md](wiki/AGENTS.md) for the HTML schema, indexes, source ingest, query, lint, cross-links, and log policy. Do not create Markdown wiki content; `wiki/AGENTS.md` is an agent instruction file, not a wiki article.
