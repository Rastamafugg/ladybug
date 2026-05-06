# Lady Bug — Arcade Reference (Web Ingest)

Aggregate of public web references consulted on 2026-05-05 to seed [game/overview.md](../game/overview.md). Each entry notes what was extracted and what remains uncertain.

## Sources consulted

- **Wikipedia — Lady Bug (video game)** — confirmed: 8 enemy types (one per level on stages 1–8, four-at-a-time from level 9), 20 green gates, no full isolation possible, border-circuit timer, vegetable in centre after 4th enemy released, ColecoVision-exclusive Vegetable Harvest bonus on SPECIAL. Did not give: scoring numbers, life count, letter colour rules.
- **Pixelated Arcade tech specs** — confirmed display: 240×192 @ 60.11 Hz vertical raster, Z80 @ 4 MHz, 2× SN76489 @ 4 MHz mono, 1–2 players alternating, 1 joystick. No sprite/grid specifics.
- **C64-Wiki Ladybug entry** (1983 C64 port, **not arcade**) — gave: 3 starting lives, heart multiplier ×2/×3/×5, "EXTRA or SPECIAL grants extra life or 10,000 bonus points", same maze every level, 20 revolving doors player-only. Treat as indicative for arcade but verify before locking.
- **Web search aggregations** (multiple) — gave: vegetable cycle and 1000 → 9500 (+500/level) point scale through level 18, then horseradish constant; base scoring 10/100/300/800 for dot/blue/yellow/red.
- **bitvint.com history page** — gave: rotating-gates strategic emphasis, "items earlier yield higher points" claim, skulls as instant-death stationary hazards. Did not detail letter mechanics.
- **Wikipedia + arcade reviews** — Arcade Awards 1983 Certificate of Merit (Most Innovative Coin-Op runner-up) for the turnstile mechanic.

## Sources attempted but unavailable

- **Arcade-Museum manual PDF** (`arcade-museum.com/manuals-videogames/L/Lady_Bug__1981__Universal.pdf`) — fetcher returned binary PDF data, not extractable via WebFetch. Should be downloaded and ingested manually if available.
- **StrategyWiki Lady Bug gameplay page** — 403 on fetch (fetcher blocked).
- **xahlee.info optimal-strategy page** — connection refused.

## Recommended next ingests

1. **Download the Arcade-Museum manual PDF locally**, then ingest the scoring chart and dip-switch settings.
2. **MAME driver** — `src/mame/drivers/ladybug.cpp` and the corresponding video/audio drivers in MAME source. This is the canonical reference for AI behaviour, exact gate count and placement, sound register usage, and dip switches.
3. **ROM disassembly** if one exists publicly — would resolve enemy AI specifics.

## Status

Web-ingest only. All claims should be flagged "verify against MAME / manual" before they constrain implementation.
