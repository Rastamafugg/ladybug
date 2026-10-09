# Ladybug

Ladybug is a 6809 assembly-language port of Universal's 1981 arcade game for the Tandy Color Computer 3. It is developed with OpenAI Codex, an LLM-based coding agent, under my direction. I set the project goals and constraints, provide design guidance, and review Codex's contributions.

## Current status

**Status as of 2026-10-07:** The [1.0.0-beta release](https://github.com/Rastamafugg/ladybug/releases/tag/1.0.0-beta) is published. Development continues. The beta may still show rendering stalls and gameplay slowdown; the project's 27,000-cycle performance targets remain open, and proposed PERF-009/PERF-010 optimizations are not included. Physical CoCo 3 qualification remains incomplete, and gameplay in MAME remains unverified because of the GMC bank-selection compatibility issue.

## Play a prebuilt ROM

The repository keeps one built ROM for each tagged version. The current prebuilt image is [`coco-ladybug-1.0.0-beta.rom`](https://github.com/Rastamafugg/ladybug/blob/1.0.0-beta/roms/coco-ladybug-1.0.0-beta.rom), a 64 KiB image for a four-bank GMC cartridge. Use the XRoar Online instructions below to play this beta in a browser. The desktop XRoar and MAME examples assume you run them from a cloned repository; if you downloaded only the ROM, replace `roms/coco-ladybug-1.0.0-beta.rom` with the path where you saved the ROM.

### XRoar

Install [XRoar](https://www.6809.org.uk/xroar/) and run this command from the repository folder:

```sh
xroar -machine coco3 -machine-cpu 6809 -ram 512 -cart-type gmc -cart-rom roms/coco-ladybug-1.0.0-beta.rom -cart-autorun -tv-input rgb -joy-right ""
```

The game uses keyboard input in this build.

### XRoar Online (browser)

1. Open the [beta ROM file on GitHub](https://github.com/Rastamafugg/ladybug/blob/1.0.0-beta/roms/coco-ladybug-1.0.0-beta.rom) and choose **Download raw file** to save `coco-ladybug-1.0.0-beta.rom` to your device.
2. Open [XRoar Online](https://www.6809.org.uk/xroar/online/).
3. Select **Hardware → Machine → Tandy CoCo 3**.
4. Select **File → Run…** and choose the ROM you saved. This control loads a local file, so download the ROM before selecting it. XRoar automatically selects the Games Master Cartridge for this 64 KiB ROM and tries to start it.
5. When the game menu appears, press **5** or **6** to add a credit, then press **Enter** to start. Use the arrow keys and Enter to navigate menus; configure gameplay controls under **Options**.

### MAME

Install MAME and run this command from the repository folder:

```sh
mame coco3 -ext games_master -cart roms/coco-ladybug-1.0.0-beta.rom -autoboot_delay 1 -autoboot_command "EXEC &HC002\n"
```

**Known limitation:** The project's tested MAME 0.220 run enters the game bootstrap but then shows a corrupted display because the ROM's GMC bank-select address does not match MAME's GMC model. The current ROM is not verified for gameplay in MAME. The project's [MAME runbook](wiki/internal/tooling/build-workflow.html) records the compatibility details. Use XRoar for the current gameplay path.

### CoCo-Pi

CoCo-Pi is a Raspberry Pi distribution with CoCo emulators. Download or copy `coco-ladybug-1.0.0-beta.rom` onto the Pi, for example into its `Downloads` folder. Open a terminal on CoCo-Pi and run:

```sh
xroar -machine coco3 -machine-cpu 6809 -ram 512 -cart-type gmc -cart-rom "$HOME/Downloads/coco-ladybug-1.0.0-beta.rom" -cart-autorun -tv-input rgb -joy-right ""
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
