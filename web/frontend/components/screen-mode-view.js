// Screen Mode pane.
//
// The GIME video-mode regs ($FF98 VMODE, $FF99 VRES, $FF9D/$FF9E vertical
// offset) are write-only per platform/gime.md, so we cannot read the live
// configuration from hardware. This pane shows the *design target* from
// wiki/implementation/video-mode.md. When the codebase later maintains a
// software shadow of these regs at a known DP location, swap the static
// data here for a fetch.

import { store } from "/static/store.js";

const DESIGN = {
  vmode_hex: "0x80",          // BP=1 GR=1, other bits per video-mode.md TBD
  vres_hex:  "0x1E",          // VRES=00 HRES=111 CRES=10
  width: 320,
  height: 192,
  colors: 16,
  bpp: 4,
  kind: "graphics",           // graphics | text
  row_stride: 160,
  fb_bytes: 30720,
  source: "wiki/implementation/video-mode.md",
};

class ScreenModeView extends HTMLElement {
  connectedCallback() {
    this.innerHTML = `
      <style>
        .sm { font-family: var(--mono); font-size: 12px; }
        .sm .row { display: grid; grid-template-columns: 90px 1fr; gap: 6px; padding: 1px 0; }
        .sm .k { color: var(--fg-dim); }
        .sm .v { color: var(--fg); }
        .sm .v.accent { color: var(--accent); }
        .sm .note { color: var(--fg-dim); font-size: 11px; margin-top: 6px; font-family: system-ui, sans-serif; }
      </style>
      <h2 style="margin-top:14px;">Screen Mode</h2>
      <div class="sm">
        <div class="row"><span class="k">VMODE $FF98</span><span class="v accent">${DESIGN.vmode_hex}</span></div>
        <div class="row"><span class="k">VRES  $FF99</span><span class="v accent">${DESIGN.vres_hex}</span></div>
        <div class="row"><span class="k">kind</span><span class="v">${DESIGN.kind}</span></div>
        <div class="row"><span class="k">resolution</span><span class="v">${DESIGN.width} × ${DESIGN.height}</span></div>
        <div class="row"><span class="k">colors</span><span class="v">${DESIGN.colors} (${DESIGN.bpp} bpp)</span></div>
        <div class="row"><span class="k">row stride</span><span class="v">${DESIGN.row_stride} B</span></div>
        <div class="row"><span class="k">fb size</span><span class="v">${DESIGN.fb_bytes.toLocaleString()} B</span></div>
        <div class="note">Design target — GIME mode regs are write-only, so this is not read from hardware.</div>
      </div>
    `;
  }
}

customElements.define("screen-mode-view", ScreenModeView);
