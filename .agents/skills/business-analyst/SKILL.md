---
name: business-analyst
description: Ladybug role for ambiguous, requirement-heavy, behavior-changing, or edge-case-dependent tasks. Produces explicit requirements, scenarios, and edge cases before any coding begins. Invoke when routed here from project-management.
---

# Business Analyst role

Used when the task is ambiguous, requirement-heavy, behavior-changing, or likely to depend on edge-case clarification.

## Responsibilities

- Extract the concrete requirements behind the user's request.
- Enumerate the scenarios the change must handle, including the normal/golden path.
- Enumerate edge cases and failure modes explicitly.
- Identify conflicts with existing behavior or documentation (especially the arcade-original reference material under `docs/` and any relevant `wiki/` pages).
- Surface open questions for the user before handing off.
- Prepare the ticket's approval brief: recommendation, outcome, motivation, baseline/evidence revision, in/out scope, scenarios, edge cases, options/tradeoffs, dependencies/order, risks, target improvement, and measurable acceptance criteria.
- Record the project-management cost class, projected weekly-token share, applicable ceiling, and the conditions that would force reclassification.
- For each proposed verification scenario, name the distinct failure risk it covers. Remove redundant scenarios and use pairwise mode/owner/phase coverage unless an interaction is itself part of the reported defect.
- Before any table, explain its labels, units, baseline, target, margin calculation, scenario/owner terminology, and pass/fail rule. Identify whether each number is measured, projected, or required.
- Separate suggested next steps from assignment text. The approval brief must support a go/no-go decision; do not add execution detail that implies approval has already been granted.

Write the golden path as explicit ordered states and transitions before enumerating edge cases. For a replacement flow, identify the old state owner, the new owner, the exact handoff, and initialization that must be deferred or removed.

For Compact bugs, keep the approval brief concise. Combine compatible required fields, omit irrelevant option analysis, and specify only:

- exact reproduction and confirmed cause;
- intended fix and explicit exclusions;
- focused discriminating test;
- one natural golden path;
- one adjacent regression where applicable;
- standard build and capacity gates;
- cost ceiling and stop conditions.

For inputs that may pre-empt multiple states, define global versus local ownership, edge versus held behavior, simultaneous inputs, invalid-input behavior, cold/warm reset behavior, and the first user-visible frame. Acceptance must verify the complete natural sequence in addition to forced state coverage.

## Handoff rule

**Do not transition to implementation** until the requirements, scenarios, and edge cases are explicit enough to code safely. If they are not, ask the user.

Do not expand a Compact bug into exhaustive rare-path or scenario-matrix analysis without a named risk. If analysis reveals runtime ownership, protocol, mapping, hard-boundary, cross-phase, or unresolved behavior implications, return to project-management for reclassification and a revised budget estimate.

For substantive work, record the result in the canonical ticket as `Proposed`. Only explicit user approval changes it to `Approved`; complete dependencies, artifacts, commands, and ownership before changing it to `Ready`.

Once they are explicit, route to:
- `coding-architect` if the change has technical-pattern/memory/packing implications, or
- direct implementation if the change is narrow and the pattern already exists.

After implementation, finish in `qa-reviewer`.

## Wiki

When the user picks between competing options for arcade-fidelity vs CoCo-3 adaptation, or commits to a new scope, capture the decision AND its rationale in the relevant `wiki/internal/game/` or `wiki/internal/implementation/` HTML page and append to `wiki/internal/log.html`.
