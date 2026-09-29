# Ladybug

Ladybug is a 6809 assembly-language port of Universal's 1981 arcade game for the Tandy Color Computer 3 with 512 KiB of RAM.

## Current status

**Status as of 2026-09-29:** Active development in Phase 9. The RSCH-013 credit, TOP-score, demo-route, and SPECIAL/EXTRA repairs are integrated. [BUG-058](wiki/internal/tickets/bug-058-three-enemy-slowdown.html) tracks the remaining four-enemy timing work; its adaptive prototype is still isolated and has not been integrated into main. The tagged `1.0.0-alpha` ROM predates these repairs. Physical CoCo 3 hardware qualification remains incomplete.

## Play a prebuilt ROM

The repository keeps one built ROM for each tagged version. The current image is [`1.0.0-alpha.rom`](roms/1.0.0-alpha.rom), a 64 KiB image for a four-bank GMC cartridge. Download it from GitHub, then use the instructions for your emulator below. The XRoar and MAME examples assume you run them from a cloned repository; if you downloaded only the ROM, replace `roms/1.0.0-alpha.rom` with the path where you saved it.

### XRoar

Install [XRoar](https://www.6809.org.uk/xroar/) and run this command from the repository folder:

```sh
xroar -machine coco3 -machine-cpu 6809 -ram 512 -cart-type gmc -cart-rom roms/1.0.0-alpha.rom -cart-autorun -tv-input rgb -joy-right ""
```

The game uses keyboard input in this build.

### MAME

Install MAME and run this command from the repository folder:

```sh
mame coco3 -ext games_master -cart roms/1.0.0-alpha.rom -autoboot_delay 1 -autoboot_command "EXEC &HC002\n"
```

**Known limitation:** The project's tested MAME 0.220 run enters the game bootstrap but then shows a corrupted display because the ROM's GMC bank-select address does not match MAME's GMC model. The current ROM is not verified for gameplay in MAME. The project's [MAME runbook](wiki/internal/tooling/build-workflow.html) records the compatibility details. Use XRoar for the current gameplay path.

### CoCo-Pi

CoCo-Pi is a Raspberry Pi distribution with CoCo emulators. Download or copy `1.0.0-alpha.rom` onto the Pi, for example into its `Downloads` folder. Open a terminal on CoCo-Pi and run:

```sh
xroar -machine coco3 -machine-cpu 6809 -ram 512 -cart-type gmc -cart-rom "$HOME/Downloads/1.0.0-alpha.rom" -cart-autorun -tv-input rgb -joy-right ""
```

If you saved the ROM elsewhere, change the path after `-cart-rom`. See the [CoCo-Pi downloads page](https://coco-pi.com/downloads/) and [project updates](https://coco-pi.com/news-updates/) for current image and setup information.

## Build from source (optional)

Clone the repository in a Linux shell. Windows users can use Ubuntu under WSL. Building requires Git, Python 3, and LWTOOLS (`lwasm`). The [build runbook](wiki/internal/tooling/build-workflow.html) has toolchain notes.

```sh
git clone https://github.com/Rastamafugg/ladybug.git
cd ladybug
LADYBUG_PROFILE=complete bash scripts/build.sh build
```

The image is written to `build/ladybug.rom`. To build and launch that image in XRoar, run:

```sh
LADYBUG_PROFILE=complete bash scripts/build.sh run
```

For project background, see the [project wiki](wiki/index.html) and [implementation roadmap](wiki/internal/implementation/roadmap.html).
