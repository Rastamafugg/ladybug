# Ladybug

Ladybug is a 6809 assembly-language port of Universal's 1981 arcade game for the Tandy Color Computer 3. It is developed with LLM coding agents under my direction. I set the project goals and constraints, provide design guidance, and review all contributions.

## Current status

**Status as of 2026-11-25:** The [1.0.0-rc1 release candidate](https://github.com/Rastamafugg/ladybug/releases/tag/1.0.0-rc1) is ready for testing. It includes the full playable game loop:

- **Arcade gameplay & AI:** 24×24 maze, 20 rotating turnstile gates, global Red/Yellow/Blue bonus cycle, `×2`/`×3`/`×5` hearts, `SPECIAL` and `EXTRA` word completions with non-skippable intermissions (`FEAT-011`), all 18 stage vegetables with arcade PROM palettes (`BUG-131`), 8 arcade enemy families (`BUG-125`), exact arcade 8-pixel player–enemy hitbox (`BUG-132`), lossless right-aligned death/angel animation (`BUG-020`), and 1981 arcade 11×11 BFS enemy pursuit AI paired with arcade perimeter timer acceleration (`FEAT-014`).
- **Options & menus:** Free-start Attract menu (`FEAT-010`), Options menu with right-justified values and tightly-bounded `()` (`FEAT-017`), `DIFFICULTY` (`ARCADE` default / `EASY`), `LIVES` (`01`–`12`), optional repeating `BONUS LIFE` (`OFF` default / `10000`–`50000`, `FEAT-015`), `STARTING LEVEL` (`01`–`255`), configurable `KEYBINDINGS`, Up/Down wrap-around across all menus, ease-in held-key auto-repeat, green Game Over timer border, and Credits v1.0 (`FEAT-016`).
- **Audio & compatibility:** 18-cue GMC SN76489 sound engine using the standard `$FF40`/`$FF41` register convention (`BUG-113`), pre-release Cue 5 enemy warning siren (`BUG-133`), active score entry flash (`BUG-127`), and isolated wall-cleared High Score Name Entry (`BUG-120`).
- **Remaining work before 1.0.0:** Physical CoCo 3 hardware qualification (and a non-GMC CoCoSDC/floppy build for systems without a GMC) remain open.

## Play a prebuilt ROM

The repository keeps one built ROM for each tagged version. The current prebuilt image is [`coco-ladybug-1.0.0-rc1.rom`](https://github.com/Rastamafugg/ladybug/blob/1.0.0-rc1/roms/coco-ladybug-1.0.0-rc1.rom) (64 KiB four-bank GMC cartridge, SHA-256 `8d25a9a276b6608aadd688b3598c021a16b7e948c72ae8520c46119db25e3b58`). Use the XRoar Online instructions below to play in a browser. The desktop XRoar and MAME examples assume you run them from a cloned repository; if you downloaded only the ROM, replace `roms/coco-ladybug-1.0.0-rc1.rom` with the path where you saved the ROM.

### XRoar

Install [XRoar](https://www.6809.org.uk/xroar/) and run this command from the repository folder:

```sh
xroar -machine coco3 -machine-cpu 6809 -ram 512 -cart-type gmc -cart-rom roms/coco-ladybug-1.0.0-rc1.rom -cart-autorun -tv-input rgb -joy-right ""
```

The game uses keyboard input in this build.

### XRoar Online (browser)

1. Open the [rc1 ROM file on GitHub](https://github.com/Rastamafugg/ladybug/blob/1.0.0-rc1/roms/coco-ladybug-1.0.0-rc1.rom) and choose **Download raw file** to save `coco-ladybug-1.0.0-rc1.rom` to your device.
2. Open [XRoar Online](https://www.6809.org.uk/xroar/online/).
3. Select **Hardware → Machine → Tandy CoCo 3**.
4. Select **File → Run…** and choose the ROM you saved. This control loads a local file, so download the ROM before selecting it. XRoar automatically selects the Games Master Cartridge for this 64 KiB ROM and tries to start it.
5. When the Attract menu appears, press **Enter** to start. Use the arrow keys and **Enter** to navigate menus; configure difficulty, lives, bonus life, starting level, and gameplay controls under **Options**.

### MAME

Install MAME and run this command from the repository folder:

```sh
mame coco3 -uimodekey DEL -ext games_master -cart roms/coco-ladybug-1.0.0-rc1.rom -autoboot_delay 1 -autoboot_command 'EXEC &HC002\n'
```

**MAME configuration notes:** MAME 0.220 defaults **Becker Port** to **On**, which intercepts `$FF41` writes before they reach the GMC sound chip, and defaults to Composite video. Press `Delete` (or `Scroll Lock`), press `Tab`, and set:
- **Machine Configuration → Becker Port → Off** (then restart MAME for audio)
- **Video Options → Screen #0 → RGB** (for RGB output)

### CoCo-Pi

CoCo-Pi is a Raspberry Pi distribution with CoCo emulators. Download or copy `coco-ladybug-1.0.0-rc1.rom` onto the Pi, for example into its `Downloads` folder. Open a terminal on CoCo-Pi and run:

```sh
xroar -machine coco3 -machine-cpu 6809 -ram 512 -cart-type gmc -cart-rom "$HOME/Downloads/coco-ladybug-1.0.0-rc1.rom" -cart-autorun -tv-input rgb -joy-right ""
```

If you saved the ROM elsewhere, change the path after `-cart-rom`. See the [CoCo-Pi downloads page](https://coco-pi.com/downloads/) and [project updates](https://coco-pi.com/news-updates/) for current image and setup information.

## Build from source (optional)

Clone the repository in a Linux shell. Windows users can use Ubuntu under WSL. Building requires Git, Python 3, and LWTOOLS (`lwasm`). The [build runbook](wiki/internal/tooling/build-workflow.html) has toolchain notes.

```sh
git clone https://github.com/Rastamafugg/ladybug.git
cd ladybug
LADYBUG_PROFILE=complete LADYBUG_ADAPTIVE=1 bash scripts/build.sh build
```

The image is written to `build/ladybug.rom`. To build and launch that image in XRoar, run:

```sh
LADYBUG_PROFILE=complete LADYBUG_ADAPTIVE=1 bash scripts/build.sh run
```

For project background, see the [project wiki](wiki/index.html) and [implementation roadmap](wiki/internal/implementation/roadmap.html).
