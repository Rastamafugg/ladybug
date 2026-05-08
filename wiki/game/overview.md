# Lady Bug — Game Design Document

Design specification for the CoCo 3 native-hardware port of the 1981 Universal arcade game *Lady Bug*. Goal: arcade fidelity wherever the platform allows; documented adaptations where it doesn't.

## High-level

A maze-chase game in the *Pac-Man* lineage with two distinguishing mechanics: **rotating turnstile gates** that the player (but not enemies) can shift to redirect chasers, and **collectible letters** that spell `EXTRA` (extra life) and `SPECIAL` (bonus / extra credit). The player is a ladybug; enemies are a rotating cast of insects.

The arcade ran on a Z80 @ 4 MHz with two TI SN76489 sound chips at **240×192 @ 60.11 Hz vertical-orientation** raster.

## Aspect-ratio adaptation (CoCo 3)

**Arcade:** 240 wide × 192 tall (vertical monitor). Maze is a single non-scrolling screen; HUD/score graphics sit above and below the playfield.

**CoCo 3 target:** horizontal display (e.g. 320×192 hi-res). The playfield itself is square-ish and fits as-is, but the HUD bands the arcade puts above/below the maze are **rotated to side panels**:

- **Left panel:** score, lives remaining, current level number.
- **Right panel:** the partially-spelled `EXTRA` and `SPECIAL` words (showing which letters have been collected and the current colour required for the next slot of each), and the current-level vegetable indicator.

## Playfield

- **Single non-scrolling screen** per stage.
- Maze is a fixed grid of corridors with a **central nest** where enemies spawn.
- **20 green turnstile gates** placed at corridor junctions. The ladybug walking through one rotates it 90°; this can open or seal off paths. Enemies cannot turn gates and must use whatever orientation the player has left them in.
  - Constraint: the maze design guarantees that no gate configuration can fully isolate any region of the maze (the player cannot lock enemies out permanently).
- **Border circuit timer:** a marker travels around the maze perimeter. Each completed lap releases one enemy from the nest, up to a maximum of (typically) four simultaneous enemies. Border-circuit speed increases on stages 2 and 5.

## Entities

### Player (ladybug)
- **3 lives at start.**
- **Bonus life at 30,000 points** (one-time award).
- Constant movement speed across all levels (only enemies get faster).
- 4-direction joystick control (no diagonal).
- Touching an enemy costs one life; the enemy returns to the nest.
- Touching a skull is instant death.

### Enemies (insects)
- Eight distinct insect types. Levels 1–8 each introduce a new type (one type per level on those stages).
- From level 9 onward each stage features four different insect types simultaneously.
- AI: chase the ladybug through corridors; cannot shift gates, so player can manipulate routes against them.
- Killable by luring into a skull (the same hazard that kills the player kills enemies).
- Frozen for several seconds when the player eats a vegetable; still lethal on contact during the freeze.
- Speed increases per level; player speed does not.

### Skulls
- Randomly placed each stage, stationary.
- Lethal to both ladybug and enemies on contact.

## Collectibles & scoring

| Item | Base value | Notes |
| --- | --- | --- |
| Flower (dot) | 10 | Filling the maze; collecting all of them clears the stage. |
| Blue letter / heart | 100 | Multiplier-eligible (×2/×3/×5 per accumulated heart count). |
| Yellow letter / heart | 300 | Multiplier-eligible. |
| Red letter / heart | 800 | Multiplier-eligible. |
| Vegetable (centre) | 1000 → 9500 | Level-1 cucumber 1000; +500/level; caps at 9500 (level 18 horseradish, then constant). |

### Hearts and letters — separate entities, global colour cycle

Hearts and letters are **distinct items** placed at distinct positions in the maze.

**Global colour cycle.** All on-stage letters and all on-stage hearts share a **single colour state** that changes simultaneously and instantaneously across every item. At any given moment every coloured item on the playfield is the same colour. The colour cycles through blue / yellow / red on a timer (cycle period TBD during tuning).

Three targets compete for collected items: the `EXTRA` word, the `SPECIAL` word, and the heart multiplier. **Each target is assigned a distinct one of the three colours** (the specific colour-to-target mapping is a tuning parameter — TBD during implementation; e.g. blue → EXTRA, yellow → SPECIAL, red → multiplier). Because the global cycle has every item displaying the same colour at any moment, and each target is bound to a different colour, **no tie can occur**: at any instant at most one target is "active."

**Letters** (word-spelling items: E, X, T, R, A, S, P, C, I, L — E and A appear in both words)
- Each unique letter spawns at one fixed maze position; its colour follows the global cycle.
- A letter advances a word only when collected while the current global colour equals that word's assigned colour.
- E and A: collected at the EXTRA-colour → advance EXTRA; collected at the SPECIAL-colour → advance SPECIAL; collected at the multiplier-colour → no word progress.
- Letters specific to one word (X/T/R, S/P/C/I/L) collected at any colour other than their word's colour → no progress.
- Off-target collection still scores the colour's base value (100/300/800).

**Hearts** (multiplier items)
- A heart only counts toward the multiplier when collected at the multiplier-colour. Counted hearts accumulate in-stage:
  - 1st → ×2 multiplier on subsequent dots/letters.
  - 2nd → ×3.
  - 3rd → ×5.
- Off-colour hearts score the base colour value but do not progress the multiplier.
- Multiplier does **not** apply to the centre vegetable.
- Multiplier resets at stage clear.

### Word completion rewards

- **`EXTRA`** (5 letters E-X-T-R-A) → +1 life.
- **`SPECIAL`** (7 letters S-P-E-C-I-A-L) → **10,000 points**. (No bonus round in v1; see deferred items below.)

### Vegetable
- Appears in the central nest area once the fourth enemy has been released.
- Eating it: bonus points (table above) + freezes all enemies for several seconds.
- Vegetable cycle (one per level, fixed sequence through level 18 then horseradish forever):
  1. Cucumber (1000)
  2. Eggplant (1500)
  3. Carrot (2000)
  4. Radish (2500)
  5. Parsley (3000)
  6. Tomato (3500)
  7. Pumpkin (4000)
  8. Bamboo shoot (4500)
  9. Japanese radish (5000)
  10. Mushroom (5500)
  11. Potato (6000)
  12. Onion (6500)
  13. Chinese cabbage (7000)
  14. Turnip (7500)
  15. Red pepper (8000)
  16. Celery (8500)
  17. Sweet potato (9000)
  18. Horseradish (9500)
  19+. Horseradish (9500)

## Stage flow

1. Maze drawn (single fixed layout, identical every stage), dots/letters/hearts placed at their fixed positions, **fixed number of skulls** placed at randomized positions.
2. Border timer starts; ladybug spawned in starting position; nest holds all enemies for this stage.
3. Each border circuit releases one enemy (max 4). After the 4th release, vegetable spawns in nest.
4. Player eats all dots → stage clears → next stage. Hearts/letters not required for clear.
5. Death (enemy contact or skull) → respawn at start; if no lives remain, game over.

The maze is **a single fixed layout used for every stage**. Per-stage variation comes from: enemy types/count/speed, which vegetable appears, and the randomized skull positions.

## Audio
Arcade has two SN76489 chips. CoCo 3 has a single 6-bit DAC. Significant adaptation needed — sound design is its own page (TBD).

## Input
- Joystick (4-direction). Arcade uses a single 4-way stick.
- Optional keyboard fallback (arrow keys) — to confirm with user.

## Decisions locked (2026-05-05)

- HUD: split panels — left = score / lives / level; right = `EXTRA` + `SPECIAL` progress + current vegetable.
- Hearts and letters are separate maze entities. **Global colour cycle**: all coloured items share one colour state that flips simultaneously and instantaneously. Each of the three targets (EXTRA word, SPECIAL word, heart multiplier) is assigned a distinct colour; an item advances its target only when collected at the matching colour. E and A advance whichever of EXTRA/SPECIAL has the colour active at collection. No ties are possible because every item is the same colour at any instant and the three targets have distinct colours.
- `SPECIAL` reward: 10,000 points. No bonus round in v1.
- 3 starting lives, one-time bonus life at 30,000 points.
- Single fixed maze layout used for every stage.
- Fixed skull count per stage (exact number TBD during maze design — likely 4–6, randomized positions).
- No "Vegetable Harvest" bonus round in the first release.

## Deferred (not blocking initial implementation)

1. **Colour-cycle timing** — exact period of the global blue/yellow/red cycle, and whether stage-clear or death resets it. Resolve once a maze prototype exists and we can tune visually.
2. **Colour-to-target mapping** — which of blue/yellow/red is assigned to EXTRA, SPECIAL, and the heart multiplier. Match arcade if the canonical mapping turns up; otherwise pick during implementation.
3. **Enemy AI** — start with simple shortest-path chase + small randomness; refine if it doesn't feel right.
4. **Sound design** — DAC waveform tables, jingles for stage clear / extra life / SPECIAL completion / death. Address during the audio module.
5. **Input fallback** — joystick is primary; keyboard arrow-key fallback to confirm during input module.

## Sources
- [Wikipedia: Lady Bug (video game)](../sources/ladybug-arcade.md)
- StrategyWiki gameplay/walkthrough pages (partially fetched; full ingest pending)
- Pixelated Arcade tech specs page
- C64-Wiki Ladybug entry (for the 1983 home port — useful but **not authoritative** for arcade-specific rules)
- bitvint.com Lady Bug history page
- Indie Gamer Chick 2023 review

## Status

Initial draft 2026-05-05 from web ingestion. User-decided block locked the same day across HUD layout, hearts/letters mechanics, SPECIAL reward, lives/bonus, maze invariance, and skull count. Five small items deferred to implementation tuning ([Deferred](#deferred-not-blocking-initial-implementation)). MAME-source and arcade-manual ingests were explicitly skipped per user direction; flag for re-evaluation if a deferred item needs canonical resolution.
