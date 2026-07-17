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

- Resume game work from the active phase in [wiki/internal/implementation/roadmap.html](wiki/internal/implementation/roadmap.html).
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

## Wiki Maintenance

Keeping the wiki current is part of doing work on this project — see [wiki/CLAUDE.md](wiki/CLAUDE.md) for the full HTML schema and ingest/query/lint workflows. Do not create Markdown wiki pages. In brief:

- **Ingest new source files as needed.** When a task reads a raw source not yet reflected in the wiki, update `wiki/internal/sources/` and propagate to the pages it informs.
- **Record new lessons learned.** Hardware quirks, GIME register gotchas, memory/packing constraints, timing findings → the relevant `wiki/internal/platform/` or `wiki/internal/implementation/` HTML page.
- **Record new plans and decisions.** Capture the decision AND its rationale (especially arcade-fidelity vs CoCo-3-adaptation choices, scope changes, workflow shifts).
- **Update the index.** Any new page must be linked from [wiki/internal/index.html](wiki/internal/index.html) or the appropriate section index.
- **Append to the log.** Every ingest, substantive query, or lint pass gets a dated HTML section in [wiki/internal/log.html](wiki/internal/log.html).
- **Prefer updating over creating.** Before adding a page, check whether the concept already has one.
