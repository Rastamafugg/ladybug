# Ladybug

A 6809 assembly-language port of the 1981 arcade game *Lady Bug* (Universal) for the Tandy Color Computer 3 (512K), running on **native hardware only — no NitrOS-9**.

## Where knowledge lives

The project has an **LLM-maintained, hand-authored HTML wiki at [wiki/](wiki/)** — read [wiki/index.html](wiki/index.html) first for the catalog. It is the source of truth for:

- Game design (derived from arcade reference material under `docs/`)
- Platform / technology (CoCo 3, 6809, GIME hardware, bare-metal memory map, timing, sound, input)
- Implementation (data structures, **lessons learned**, **build workflow**)
- Raw source pointers (design docs, hardware reference manuals)

**Always consult the wiki before answering or coding.** If a needed fact isn't there yet, read the raw source under `docs/` or `src/` and ingest the finding back into the wiki (see Wiki Maintenance below).

## Current Development Workflow

- Start new functionality, bug fixes, performance work, tooling changes, and substantive documentation work through the [ticket workflow](wiki/internal/tickets/workflow.html). The [ticket index](wiki/internal/tickets/index.html) is the active work queue; the roadmap remains the phase-level product plan.
- Do not implement a proposed ticket until the user has approved it. Approval fixes the outcome, scope, targets, and acceptance criteria. A ticket becomes `Ready` only after dependencies, assignment details, and verification commands are complete.
- Resume game work from the highest-ordered `Ready` ticket that is consistent with the active phase in [wiki/internal/implementation/roadmap.html](wiki/internal/implementation/roadmap.html).
- Build with `scripts/build.sh build`; use the [gdb-mcp round trip](wiki/internal/tooling/xroar.html#gdb-mcp-round-trip) to launch, inspect, and verify the ROM.
- The `web/` app and patched XRoar `-monitor` stack are preserved but deferred. Do not extend them unless the user explicitly reactivates that work.
- XRoar's `-monitor` endpoint is private JSON-RPC, not MCP. The missing outward MCP bridge and keyboard/control exposure are recorded in [wiki/internal/backlog/mcp-xroar-server.html](wiki/internal/backlog/mcp-xroar-server.html).

## Roles & Routing

Every new task begins in the `project-management` role, which classifies the task and routes to one of the specialist roles. Each role is a skill — invoke it via the Skill tool when entering that role:

- `project-management` — **mandatory first role**; classify objective/scope/affected-artifacts and pick the next role.
- `business-analyst` — ambiguous, requirement-heavy, behavior-changing, or edge-case-dependent tasks.
- `coding-architect` — module boundaries, memory/packing, runtime ownership, protocols, new technical patterns.
- `debugger` — reported error, unexpected runtime behavior, failed output, unverified regression.
- `qa-reviewer` — verification, review, regression checking, acceptance; **mandatory closing role after any implementation**.

Do not begin coding until `project-management` has run. Each role skill contains its own handoff rules and guardrails.

## Response and Work-Approval Standard

- Before the first table in a conversation, define every non-obvious row/column label, unit, baseline, target, margin, owner/scenario name, and pass/fail rule used in that table. State whether numbers are maxima, minima, averages, projections, or single observations and identify the source revision or artifact when material.
- For persistent A/B rendering, label performance evidence primarily by scenario phase and executed worklist. Record framebuffer owner only as secondary metadata. Do not attribute a timing difference to owner identity unless a controlled crossover begins from identical pixels, metadata, and render intents, then repeats with the starting owner reversed.
- Never use a missing scenario as passing evidence. Required rare paths must be forced or the verification must fail. Persistent or replayed systems require both isolated-owner and natural sequence coverage when those can differ.
- Suggested next steps intended for approval must state, for each item: the work, reason, expected improvement or outcome, baseline, target, success measurement, dependencies/order, material risks, and scope exclusions.
- Distinguish an approval brief from an assignment brief. An approval brief supports the user's go/no-go decision. An assignment brief adds exact artifacts, constraints, owned files/worktree, verification commands, evidence to retain, commit requirements, and the required completion report without changing approved scope.
- If a target is missed, say so directly, retain the measured result, and create or update a follow-up ticket. Do not label the work accepted because implementation or testing completed.
- Record rejected experiments when their result changes the recommended approach. Separate current-revision evidence from historical or projected evidence.

### Runtime diagnosis invariants

- Before interpreting a symbol, map label, or hardware-register access at a live PC, prove that the live bytes match the current built artifact at that address. When loading, copying, banking, relocation, or handoff is involved, compare authored/source, staged, and destination bytes before diagnosing downstream execution.
- Treat an undocumented hardware defect as a last-stage hypothesis. Do not recommend it until software state, loader/mapping, observation-tool, and emulator-control candidates have discriminating results, and either an independent emulator/physical-hardware reproduction or authoritative hardware evidence supports escalation. Label the hypothesis unconfirmed until then.
- Every runtime probe must name its phase, success marker, deadline, and the meaning of a timeout. Keep an initial diagnostic phase at or below 60 seconds. Do not increase a phase beyond 60 seconds or by more than 2x without reporting measured progress, the projected benefit, and obtaining user approval. A timeout is evidence about the probe boundary, not proof that the target code is slow.

## Ticket and Delegation Rules

- Ticket IDs use `<TYPE>-NNN`: `FEAT`, `BUG`, `PERF`, `TOOL`, `DOC`, or `RSCH`. One HTML page under `wiki/internal/tickets/` is canonical for each ticket.
- Lifecycle: `Draft` -> `Proposed` -> `Approved` -> `Ready` -> `In Progress` -> `Verification` -> `Done`. `Blocked`, `Deferred`, `Rejected`, and `Superseded` are explicit side states. Only explicit user approval advances `Proposed` to `Approved`.
- Any material change to an approved outcome, scope, target, acceptance criterion, dependency order, or risk profile returns the ticket to `Proposed` for renewed approval. Execution detail that does not alter the approved contract may be added while preparing `Ready`.
- Every ticket must contain objective, motivation, in/out scope, scenarios and edge cases, evidence/baseline with revision, acceptance criteria, dependencies and ordering, constraints/risks, assignment contract, verification plan, decision log, and completion evidence. Bug tickets also require reproduction, observed versus expected behavior, and a discriminating test. Feature tickets also require user-visible behavior and compatibility implications.
- Delegate only `Ready` tickets. Give each subagent one bounded ticket or explicitly separable ticket step, a defined ownership boundary, and a separate commit. Parallel work must not have unresolved dependencies or overlapping writable artifacts; otherwise sequence it or assign an integration owner first.
- The parent agent owns integration: inspect each commit, resolve shared generated/wiki artifacts, rebuild from combined source, rerun integration scenarios and capacity checks, and update ticket status. Isolated subagent success is not integrated acceptance.
- Completion reports must include commit, tests, measured result versus target, residual risks, rejected experiments, changed capacity/headroom, retained evidence, and whether the ticket can move to `Done`.

## Wiki Maintenance

Keeping the wiki current is part of doing work on this project — see [wiki/CLAUDE.md](wiki/CLAUDE.md) for the full HTML schema and ingest/query/lint workflows. Do not create Markdown wiki pages. In brief:

- **Ingest new source files as needed.** When a task reads a raw source not yet reflected in the wiki, update `wiki/internal/sources/` and propagate to the pages it informs.
- **Record new lessons learned.** Hardware quirks, GIME register gotchas, memory/packing constraints, timing findings → the relevant `wiki/internal/platform/` or `wiki/internal/implementation/` HTML page.
- **Record new plans and decisions.** Capture the decision AND its rationale (especially arcade-fidelity vs CoCo-3-adaptation choices, scope changes, workflow shifts).
- **Update the index.** Any new page must be linked from [wiki/internal/index.html](wiki/internal/index.html) or the appropriate section index.
- **Append to the log.** Every ingest, substantive query, or lint pass gets a dated HTML section in [wiki/internal/log.html](wiki/internal/log.html).
- **Prefer updating over creating.** Before adding a page, check whether the concept already has one.
