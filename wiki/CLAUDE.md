# Wiki Schema & Workflow

This directory is an LLM-maintained wiki for the **Ladybug** project — a 6809 assembly port of the 1981 arcade game *Lady Bug* targeting the Tandy Color Computer 3 (512K) on **native hardware (no NitrOS-9)**. The wiki compiles knowledge from the repo's raw sources (`docs/`, `src/`) into a persistent, interlinked set of HTML pages so future sessions don't have to re-derive everything.

## Layering

- **Raw sources** — `../docs/`, `../src/`. Immutable; the wiki reads from them but never edits them.
- **Wiki** (this directory) — everything here is LLM-written, hand-authored HTML.
- **Schema** (this file) — describes structure and workflows.

## Directory layout

```
wiki/
├── CLAUDE.md                 — this file
├── index.html                — landing page, links to internal/ and release/
├── shared/
│   ├── css/wiki.css          — single stylesheet for every page
│   ├── js/                   — (reserved, currently empty)
│   └── assets/               — screenshots, diagrams
├── internal/                 — team-only docs; NOT shipped with the game
│   ├── index.html
│   ├── log.html              — append-only chronological log
│   ├── game/                 — game-design pages
│   ├── implementation/       — coding conventions, data structures, lessons learned, roadmap
│   ├── platform/             — project-specific platform commentary
│   ├── tooling/              — build workflow, lwtools, XRoar, web-app architecture
│   ├── tickets/              — approval queue, workflow, template, and executable work items
│   ├── sources/              — one page per raw source under ../docs/
│   └── backlog/              — open issues, deferred investigations
└── release/                  — stable public reference; independent of the deferred web app
    └── reference/
        ├── 6809/             — one HTML page per Motorola 6809 instruction
        ├── coco3/            — CoCo 3 memory map, GIME, modes, palette, MMU, IRQ, sound, input, timing
        └── asm-tips/         — DP conventions, register allocation, addressing patterns, timing
```

## Hand-authored HTML — no build step

- Every page is hand-written HTML. There is no Markdown source and no compilation.
- All pages link the single shared stylesheet: `<link rel="stylesheet" href="{prefix}shared/css/wiki.css">` where `{prefix}` is the relative path back to `wiki/` (`./`, `../`, `../../`, or `../../../` depending on page depth).
- Every page uses the standard shell — see the [HTML page shell](#html-page-shell) below.
- Use existing classes (`wiki-shell`, `wiki-nav`, `wiki-main`, `wiki-header`, `wiki-eyebrow`, `wiki-meta`, `wiki-badge`, `wiki-footer`, `wiki-cards`, `wiki-table`, `isa-*`). If a new pattern is genuinely needed, extend `wiki.css` and document the class.

## Internal vs. release — the audience split

- **`internal/`** — anything for the team building Ladybug: design notes, decisions, lessons learned, runbooks, debugging notes, backlog. Not shipped.
- **`release/`** — stable public hardware and assembly reference content. The deferred web app can load these pages as contextual-help fragments, but the reference remains canonical independently of that app. Pages must be self-contained and reviewed for accuracy and tone.

**Dual-audience rule.** Content useful to both audiences lives in `release/` and is linked from `internal/`. Do **not** create a thin internal mirror just to provide a navigation hook — link directly to the release page from the internal index. Only create an internal page when there is genuine internal-only content (project-specific commentary, decisions, or work-in-progress); in that case, put the commentary in `internal/` and link out to the canonical release reference.

## HTML page shell

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{Title} — Ladybug</title>
  <link rel="stylesheet" href="{prefix}shared/css/wiki.css">
</head>
<body>
<div class="wiki-shell">
  <nav class="wiki-nav">
    <a href="{prefix}index.html">← Wiki home</a>
    <!-- breadcrumb links: section index, parent, etc. -->
  </nav>
  <main class="wiki-main">
    <header class="wiki-header">
      <p class="wiki-eyebrow">{Section · category}</p>
      <h1>{Title} <span class="wiki-badge">{internal|release}</span></h1>
      <p class="wiki-meta">{one-line tagline}</p>
    </header>

    <section>
      <h2>{Section heading}</h2>
      <p>{content}</p>
    </section>

    <footer class="wiki-footer">
      <p>{provenance note, source citation, or edit hint}</p>
    </footer>
  </main>
</div>
</body>
</html>
```

The badge is `internal` on `internal/` pages and `release` on `release/` pages. Landing pages (`index.html`) may omit the badge on the root.

## 6809 ISA page template

Each `release/reference/6809/{mnemonic}.html` follows this body shape:

1. **Header.** Eyebrow = category (e.g. `6809 · Load / Store`). Title = `MNEMONIC — short prose name`. Meta = one-line RTL summary.
2. **`<section class="isa-syntax-block">`** — large monospaced mnemonic and operand display.
3. **Description.** Two or three paragraphs of prose.
4. **Condition codes.** `<table class="isa-flags-table">` with E F H I N Z V C columns; legend underneath.
5. **Addressing modes.** `<table class="isa-modes-table">` with Mode, Syntax, Opcode, Cycles (`~`), Bytes (`#`).
6. **Examples.** `<pre><code>` block with annotated assembly.
7. **`<section class="isa-see-also">`** — chip list of related mnemonics.
8. **Footer.** Source citation.

## Cross-linking conventions

- Use relative `.html` links — never absolute paths.
- Within the same directory: `<a href="other.html">`.
- To the parent or a sibling directory: `<a href="../section/other.html">`.
- Internal → release: `<a href="../../release/reference/coco3/gime.html">GIME</a>` (depth-dependent).
- Release pages must be self-contained for direct reading and optional use as web-app fragments — don't depend on the nav for comprehension.

## Workflows

### Tickets (new work)

1. Consult `internal/tickets/index.html` before defining substantive new functionality, bug fixes, performance work, tooling changes, or documentation projects.
2. Create or update one canonical ticket using `internal/tickets/template.html`; do not duplicate roadmap or backlog prose as an unlinked work item.
3. Complete the approval brief and set status to `Proposed`. Only explicit user approval advances it to `Approved`.
4. Add dependencies, ordering, exact artifacts, commands, ownership, evidence, and commit boundaries before setting it to `Ready`.
5. Keep the ticket, ticket index, and decision log synchronized through `In Progress`, `Verification`, and `Done` or an explicit side state.
6. Append substantive ticket creation, approval, scope change, integration result, and closure to `internal/log.html`.

Ticket IDs use `<TYPE>-NNN` with `FEAT`, `BUG`, `PERF`, `TOOL`, `DOC`, or `RSCH`. The full lifecycle and delegation rules are canonical in `internal/tickets/workflow.html`.

### Ingest (new source)

1. Read the source under `../docs/`.
2. Discuss key takeaways with the user before writing (unless they said "just file it").
3. Write or update the source page under `internal/sources/`.
4. Propagate: update every page the source touches. If reference content, prefer adding to `release/reference/`; if project-specific, to the appropriate `internal/` page.
5. Update `internal/index.html` (and `release/.../index.html` if applicable).
6. Append a line to `internal/log.html`.

### Query

1. Read `internal/index.html` first — it's the map.
2. Drill into relevant pages. Fall back to raw sources in `../docs/` or `../src/` only if the wiki lacks the answer.
3. Synthesize the answer with citations (wiki page + raw source).
4. If the answer contains new synthesis worth keeping, **file it back** as a new wiki page and link it from the index.
5. Append to `internal/log.html`.

### Lint

Periodically scan for:

- Dead links between pages.
- Orphan pages (no inbound links).
- Concepts mentioned but lacking their own page.
- Stale claims where code has moved on.
- Raw sources not yet ingested.
- ISA pages that diverge from the established template.

Record findings in `internal/log.html` and fix what's cheap.

## Append to the log

Every ingest, substantive query, or lint pass gets a dated entry in `internal/log.html` of the form:

```html
<section>
  <h3>2026-MM-DD · {ingest|query|lint} — {short title}</h3>
  <p>{one paragraph on what changed}</p>
</section>
```

Newest entries at the top.

## Tables and numerical evidence

- Introduce terminology before the first table: define non-obvious labels, units, scenarios/owners, baseline, target, margin calculation, aggregation method, source revision/artifact, and pass/fail rule.
- State whether numerical values are measured maxima/minima/averages, single observations, historical values, projections, or requirements.
- For persistent A/B rendering, use scenario phase and executed worklist as the primary measurement label. Buffer owner is secondary metadata, not a causal attribution. Claim an owner-specific timing effect only after a controlled crossover starts from identical pixels, metadata, and render intents and reverses the starting owner.
- Do not use an empty or missing required scenario as a pass. Record missing coverage as a failed or incomplete verification.

## Things to prefer

- **Link early.** When you mention a concept that has (or should have) its own page, link it even if the page is a stub.
- **Record "why".** When the project chooses one option over another, write the choice AND the rationale.
- **Keep indices tight.** Section index pages should fit on one screen.
- **Prefer updating over creating.** Before adding a page, grep for the concept in existing pages.
- **Release-first for reference.** If new content is useful to both audiences, put it in `release/` and link from `internal/`.
