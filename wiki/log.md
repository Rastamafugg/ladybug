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
