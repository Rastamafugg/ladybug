---
name: pixel-art
description: Generate and manipulate genuine pixel art through explicit native-resolution pixel data. Use for tiny game sprites, tiles, icons, sprite sheets, palette swaps, pixel-level edits, and frame animations, especially 8x8 and 16x16 assets. Use when exact dimensions, shared palettes, hard pixel edges, or reproducible source matter. Exclude ordinary illustrations, pixel-style concept art, and vector editing.
---

# Pixel Art

## Choose the implementation

Construct final art directly on its native pixel grid with Python and Pillow or an existing project-native pixel pipeline. Treat every output pixel as a deliberate cell. Prefer character grids for tiny sprites and coordinate operations for geometric assets or edits.

Use Aseprite for optional layers, manual finishing, animation review, and sprite-sheet export. Offer Pixelorama as an alternative. Do not require either editor to generate PNGs. Use supported scripting or CLI features only after checking the installed version or available documentation.

Do not use an image-generation model for final pixel assets in this workflow. Use one only for concept references when requested. Do not make a large image and shrink, quantize, or filter it into the final asset unless the user explicitly requests conversion.

## Establish the asset contract

Reuse constraints from the request and existing project. Inspect supplied art before modifying it. Resolve file identities and use the environment's appropriate file workflow.

Specify canvas dimensions, palette, transparency, subject, viewpoint, pose, frame count, and output layout. Preserve an existing style and technical contract. Ask only when a missing constraint materially affects compatibility; otherwise state a reasonable assumption and proceed.

For an unconstrained demonstration, use 16x16 RGBA PNGs, eight shared opaque colours plus transparency, and a single standing pose. Treat these as defaults, not hardware limits. Do not impose a particular game's palette or hardware specification without evidence.

Keep a common canvas, baseline, anchor convention, viewpoint, outline treatment, and lighting across related assets. Store palette values once and reuse them for the entire set.

## Generate at native resolution

1. Design the silhouette before internal details. At 8x8, prioritize recognizable shape and pose. At 16x16, add selective face, clothing, and equipment cues.
2. Assign one character to each palette entry and a separate character to transparency. Write exactly one row per image row and one character per pixel. Use an explicit mapping rather than implicit character ordering.
3. Validate the grid and map it directly to pixels. Avoid anti-aliasing, blur, gradients, automatic smoothing, and unintended intermediate colours. Use fully transparent or fully opaque pixels unless partial alpha is explicitly required.
4. Inspect the rendered asset at native size and at an integer enlargement. Use nearest-neighbour enlargement. Correct unclear silhouettes, accidental isolated pixels, inconsistent outlines, and misleading details.
5. Produce purposeful variations when requested. Change the design or pose while retaining the shared contract. Do not substitute simple recolours for distinct character designs unless requested.

Use this minimal rendering pattern inside a reproducible generation script. Replace the example palette and rows with the actual asset data; do not include placeholder assets in delivery.

```python
from PIL import Image

palette = {
    '.': (0, 0, 0, 0),
    'O': (32, 37, 53, 255),
    'L': (114, 195, 173, 255),
}

def render(rows, palette, size):
    width, height = size
    if len(rows) != height or any(len(row) != width for row in rows):
        raise ValueError('Grid dimensions do not match the asset contract')
    if not set(''.join(rows)) <= palette.keys():
        raise ValueError('Grid references an undefined palette entry')
    if any(len(c) != 4 or any(not isinstance(v, int) or not 0 <= v <= 255
                             for v in c) for c in palette.values()):
        raise ValueError('Palette values must be RGBA byte tuples')
    if any(c[3] not in (0, 255) for c in palette.values()):
        raise ValueError('Partial alpha is outside this asset contract')
    image = Image.new('RGBA', size)
    image.putdata([palette[key] for row in rows for key in row])
    return image
```

Allow partial alpha only by deliberately revising the contract and validation. Keep preview font dependencies out of the core generation path; use an available font or Pillow's default font for labels.

## Manipulate existing pixel art

- Preserve the original file and work on a new output unless an update is requested. Preserve layers and animation metadata when editing native editor files; do not silently flatten them.
- Inspect dimensions, mode, frame count, visible colours, alpha, padding, and sprite-sheet boundaries before editing. Separate the actual asset from any enlarged preview or checkerboard baked into a reference.
- Apply requested edits using pixel coordinates, masks, or source-grid changes. For local edits, compare before and after pixels and verify that changes stay inside the intended region.
- Implement palette swaps with exact RGBA lookups. Apply mappings simultaneously so chained replacements cannot alter already-replaced colours. Preserve alpha unless the requested operation changes it.
- Use integer translations, exact flips, and quarter-turn rotations for lossless transformations. Account for changed dimensions on rectangular rotations. Re-pixel arbitrary rotations or scale changes deliberately; explain the change in pixel structure.
- Keep nearest-neighbour resizes separate from native assets. Do not crop transparent margins or alter canvas size without checking the anchor and layout contract.
- For conversion of ordinary images, describe quantization or downsampling as conversion and inspect the result manually. Do not call it deliberately authored native pixel art.

## Animate and assemble sheets

Approve or establish a readable base sprite before expanding to a full animation. Proceed directly when the requested animation is already clear; do not add a mandatory approval gate.

Maintain canvas size, ground contact, equipment proportions, palette, and anchor across frames. Change poses intentionally; avoid accidental drift, clipping, and inconsistent outlines. Inspect both individual frames and playback. Distinguish deliberate motion from registration errors.

Export a declared frame order, frame durations, dimensions, padding, spacing, and anchor coordinates. State the anchor coordinate convention. Use a transparent sheet with no padding by default only when the engine has no specified layout. Include JSON frame metadata for nontrivial layouts. Supply a GIF or other playback preview when useful; keep PNG frames or sheets authoritative.

## Verify the exported bytes

Reopen exported PNGs and check the actual files, not just the in-memory source:

- Verify exact dimensions, frame count, and sheet layout against the contract.
- Verify every visible RGBA value belongs to the shared palette. Count opaque colours separately from transparency; canonicalize invisible RGB values if necessary.
- Verify alpha is binary unless partial alpha was requested. Never count a preview background as an asset colour.
- Verify frame extraction from a sheet reproduces the individual frames exactly.
- For lossless edits, verify unchanged pixels outside the intended region and expected anchor preservation.
- Inspect native-size readability and an integer nearest-neighbour preview. Make no visual-quality claims based on numeric checks alone.

Report checks actually performed. Do not claim indexed colour merely because an RGBA PNG uses a restricted palette. Export indexed PNG only when requested or required and verify its palette and transparency after conversion.

## Deliver

Provide native PNG assets and their reproducible source grids or script. Include a shared palette in JSON or an editor-compatible format, and sheet metadata when applicable. Clearly label enlarged comparisons and playback previews as previews. Keep preview borders, labels, grids, and checkerboards out of native assets.

Save deliverables through the environment's required artifact workflow; keep repository-backed game assets in their project when applicable. Package a ZIP only when requested or useful for a set of related assets. State actual sizes, shared palette count, included outputs, and any missing animation or editor-native data. Offer one concrete next edit or animation step.
