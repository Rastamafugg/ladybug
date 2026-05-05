# Wiki Schema & Workflow

This directory is an LLM-maintained wiki for the **Ladybug** project — a 6809 assembly port of the 1981 arcade game *Lady Bug* targeting the Tandy Color Computer 3 (512K) on **native hardware (no NitrOS-9)**. The wiki compiles knowledge from the repo's raw sources (`docs/`, `src/`) into a persistent, interlinked set of markdown pages so future sessions don't have to re-derive everything.

## Layering

- **Raw sources** — `../docs/`, `../src/`. Immutable; the wiki reads from them but never edits them.
- **Wiki** (this directory) — everything here is LLM-written.
- **Schema** (this file) — describes structure and workflows.

## Directory layout

```
wiki/
├── CLAUDE.md              — this file
├── index.md               — content catalog (read first when answering a query)
├── log.md                 — chronological append-only log of ingests/queries/lints
├── sources/               — one page per raw source document, with summary + pointers
├── game/                  — game design: entities, levels, mechanics (derived from arcade reference)
├── platform/              — technical platform: CoCo 3, GIME, 6809, bare-metal memory map, graphics/sound/timing
└── implementation/        — project-specific: data structures, lessons learned, build workflow
```

Pages link each other with relative markdown links (e.g. `[GIME](../platform/gime.md)`), not Obsidian `[[wikilinks]]`, so they render in both Obsidian and plain markdown viewers.

## Page conventions

- Each page starts with a one-sentence **purpose** line, then content.
- Cite the raw source at the bottom under `## Sources`: e.g. `- docs/reference/coco3-asm.md §5.2` or `- src/asm/sprite.s:L40-60`.
- When a claim has competing values between sources, record BOTH with their sources — don't silently pick one.
- Prefer small interlinked pages over long monolithic ones. If a page exceeds ~300 lines consider splitting.
- Frontmatter (optional) for queryable pages:
  ```
  ---
  type: entity | concept | source | finding
  tags: [game, gime, ...]
  updated: 2026-05-05
  ---
  ```

## Workflows

### Ingest (new source)

1. Read the source.
2. Discuss key takeaways with the user before writing (unless they said "just file it").
3. Write/update the source summary page under `sources/`.
4. Propagate: update every entity/concept page the source touches.
5. Update [index.md](index.md) with any new pages.
6. Append a line to [log.md](log.md): `## [YYYY-MM-DD] ingest | <Source Title>` + one paragraph on what changed.

### Query

1. Read [index.md](index.md) first — it's the map.
2. Drill into relevant pages. If you need to, fall back to reading raw sources in `../docs/` or `../src/`.
3. Synthesize the answer with citations (wiki page + raw source).
4. If the answer contains new synthesis worth keeping (a comparison, a derived table, a decision rationale), **file it back** as a new wiki page and link it from the index. Don't let valuable exploration disappear into chat history.
5. Append to [log.md](log.md): `## [YYYY-MM-DD] query | <one-line question>` + one line on the answer or page created.

### Lint

Periodically, scan for:
- Contradictions between pages.
- Orphan pages (no inbound links).
- Concepts mentioned but lacking their own page.
- Stale claims where code has moved on.
- Raw sources that have not yet been ingested.

Record findings in `log.md` and fix what's cheap; surface the rest as a todo list for the user.

## Things to prefer

- **Link early.** When you mention a concept that has (or should have) its own page, link it even if the page is a stub.
- **Record "why".** When the project chooses one option over another (arcade-fidelity vs adaptation, register vs memory layout, ROM vs RAM placement), write the choice AND the rationale.
- **Keep the index tight.** One line per page under ~150 chars. The index is always in context; long-form belongs in the page.
- **Prefer updating over creating.** Before adding a page, grep for the concept in existing pages.
