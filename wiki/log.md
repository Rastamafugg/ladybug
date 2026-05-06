# Wiki Log

Append-only chronological record of ingests, queries, and lints. Each entry prefixed `## [YYYY-MM-DD] <type> | <title>` so the log is grep-parseable.

---

## [2026-05-05] seed | Initial wiki instantiation

Created wiki scaffolding under `wiki/` for the Ladybug project (6809 assembly port of the 1981 *Lady Bug* arcade game, targeting bare-metal CoCo 3 — no NitrOS-9). Configuration adapted from the Planet Pioneers project:

- `CLAUDE.md` schema (three-layer architecture: raw sources / wiki / schema; relative-link convention; ingest/query/lint workflows).
- `index.md` content catalog with stub entries for game / platform / implementation / sources sections.
- `log.md` (this file).
- Project-root `CLAUDE.md` adapted to Ladybug.
- `.claude/skills/` role skills (project-management, business-analyst, coding-architect, debugger, qa-reviewer) copied and adapted — references to MULE/GDD/NitrOS-9/DCC replaced with Ladybug/arcade-reference/GIME/6809-toolchain.
- `.claude/settings.local.json` permissions copied (git/gh + read access under `D:/retro/`).

No raw sources ingested yet. Next steps when work begins: pick the assembler (lwasm vs asm6809 vs EDTASM), commit a `docs/` folder with arcade reference material and a CoCo 3 hardware reference, and ingest both into corresponding `sources/` pages.

---

## [2026-05-05] ingest | Lady Bug arcade — web reference

User asked for a design doc seeded from public web sources. Searched + fetched Wikipedia, Pixelated Arcade tech specs, C64-Wiki (port reference), bitvint.com, and miscellaneous web aggregations. Created [`sources/ladybug-arcade.md`](sources/ladybug-arcade.md) cataloguing what was extracted from each source and what remains uncertain. Created [`game/overview.md`](game/overview.md) — full design doc covering: playfield (240×192 arcade → CoCo 3 horizontal with HUD relocated to side panels), 20 turnstile gates, border-circuit enemy-release timer, 8 enemy types + skull hazards, scoring table (dot 10 / blue 100 / yellow 300 / red 800 / vegetables 1000–9500), heart ×2/×3/×5 multiplier, EXTRA/SPECIAL letter cycle, full 18-vegetable cycle. Ten open questions logged for user/MAME-source resolution. Two source documents could not be fetched (arcade-museum manual PDF returned binary data; StrategyWiki blocked the fetcher).

---

## [2026-05-05] decision | Design-doc scope locked for first release

User answered the 10 open questions in [`game/overview.md`](game/overview.md). Locked: HUD split panels (left = score/lives/level; right = EXTRA/SPECIAL/vegetable); hearts and letters are **separate maze entities** with independent colour cycles, where E and A advance whichever of EXTRA/SPECIAL matches their current colour at collection time, every other letter and all hearts only advance/multiply when colour matches the target exactly; `SPECIAL` reward = 10,000 points (no bonus round in v1); 3 lives + one-time 30K bonus life; single fixed maze across all stages; fixed skull count per stage. Explicitly skipped: MAME-source ingest, arcade-manual PDF ingest. Five small items deferred to implementation tuning (cycle timing, E/A tie-break, enemy AI specifics, sound, input fallback). Rewrote `game/overview.md` HUD-relocation, hearts-vs-letters, and stage-flow sections; replaced 10-item Open Questions with a "Decisions locked" block + 5-item Deferred list.
