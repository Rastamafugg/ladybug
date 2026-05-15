import { store } from "/static/store.js";

class PaletteView extends HTMLElement {
  constructor() {
    super();
    this.mode = "rgb_monitor";   // or "composite"
    this.data = null;
  }

  connectedCallback() {
    this.innerHTML = `
      <style>
        .pv { margin-top: 14px; }
        .pv .ctrl {
          display: flex; gap: 6px; align-items: center;
          font-size: 11px; margin-bottom: 6px;
        }
        .pv .ctrl button {
          background: var(--bg-3); color: var(--fg);
          border: 1px solid #383850; border-radius: 3px;
          padding: 2px 8px; cursor: pointer; font-size: 11px;
        }
        .pv .ctrl button.active {
          background: var(--accent); color: #14141c; border-color: var(--accent);
        }
        .pv .grid {
          display: grid; grid-template-columns: repeat(4, 1fr);
          gap: 4px;
        }
        .pv .swatch {
          aspect-ratio: 2 / 1;
          border: 1px solid var(--bg-3); border-radius: 3px;
          display: flex; align-items: flex-end; justify-content: space-between;
          padding: 2px 4px; font-family: var(--mono); font-size: 10px;
          cursor: default;
        }
        .pv .swatch .idx { color: rgba(255,255,255,0.85); text-shadow: 0 0 2px #000; }
        .pv .swatch .raw { color: rgba(255,255,255,0.85); text-shadow: 0 0 2px #000; }
        .pv .empty { color: var(--fg-dim); font-size: 11px; padding: 4px; }
      </style>
      <h2 style="margin-top:14px;">Palette</h2>
      <div class="pv">
        <div class="ctrl">
          <button id="pv-rgb" class="active">RGB monitor</button>
          <button id="pv-comp">Composite</button>
          <span class="dim" id="pv-status"></span>
        </div>
        <div id="pv-body" class="empty">no instance selected</div>
      </div>
    `;
    this.body = this.querySelector("#pv-body");
    this.status = this.querySelector("#pv-status");
    this.btnRgb = this.querySelector("#pv-rgb");
    this.btnComp = this.querySelector("#pv-comp");

    this.btnRgb.addEventListener("click", () => this.setMode("rgb_monitor"));
    this.btnComp.addEventListener("click", () => this.setMode("composite"));

    store.addEventListener("select", () => { this.data = null; this.status.textContent = ""; this.render(); });
    store.addEventListener("ws:halt", () => this.refresh());
  }

  setMode(m) {
    this.mode = m;
    this.btnRgb.classList.toggle("active", m === "rgb_monitor");
    this.btnComp.classList.toggle("active", m === "composite");
    this.render();
  }

  async refresh() {
    if (!store.selectedId) return;
    try {
      const r = await fetch(`/api/instances/${store.selectedId}/palette`);
      if (!r.ok) {
        const detail = await r.text();
        this.status.textContent = `read failed (${r.status}): ${detail}`;
        console.warn("palette read failed", r.status, detail);
        return;
      }
      this.data = await r.json();
      this.status.textContent = "";
      this.render();
    } catch (e) {
      this.status.textContent = `error: ${e.message}`;
    }
  }

  render() {
    if (!this.data) {
      this.body.className = "empty";
      this.body.textContent = store.selectedId ? "no halt event yet" : "no instance selected";
      return;
    }
    const colors = this.data[this.mode];
    const raw = this.data.raw;
    const cells = colors.map((rgb, i) => {
      const [r, g, b] = rgb;
      const rawByte = raw[i].toString(16).toUpperCase().padStart(2, "0");
      const otherSpace = this.mode === "rgb_monitor" ? this.data.composite : this.data.rgb_monitor;
      const [or, og, ob] = otherSpace[i];
      const otherName = this.mode === "rgb_monitor" ? "composite" : "RGB";
      const tip = `idx ${i}  $${rawByte}\n${this.mode}: rgb(${r},${g},${b})\n${otherName}: rgb(${or},${og},${ob})`;
      return `
        <div class="swatch" style="background: rgb(${r},${g},${b});" title="${tip}">
          <span class="idx">${i}</span>
          <span class="raw">$${rawByte}</span>
        </div>
      `;
    });
    this.body.className = "grid";
    this.body.innerHTML = cells.join("");
  }
}

customElements.define("palette-view", PaletteView);
