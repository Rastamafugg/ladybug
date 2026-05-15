import { store } from "/static/store.js";

const DEFAULT_LEN = 64;

class MemoryView extends HTMLElement {
  constructor() {
    super();
    this.addr = 0x0200;       // start at DP page; useful default
    this.len = DEFAULT_LEN;
    this.bytes = null;        // Uint8Array of last fetched bytes
    this.regionFetched = null;
  }

  connectedCallback() {
    this.innerHTML = `
      <style>
        .mv .ctrl {
          display: flex; gap: 6px; align-items: center;
          font-size: 12px; margin-bottom: 6px;
        }
        .mv .ctrl input {
          background: var(--bg-2); color: var(--fg);
          border: 1px solid var(--bg-3); border-radius: 3px;
          padding: 2px 6px; font-family: var(--mono); font-size: 12px;
          width: 80px;
        }
        .mv .ctrl input.len { width: 50px; }
        .mv .ctrl button {
          background: var(--bg-3); color: var(--fg);
          border: 1px solid #383850; border-radius: 3px;
          padding: 2px 8px; cursor: pointer; font-size: 12px;
        }
        .mv .dump {
          font-family: var(--mono); font-size: 12px; line-height: 1.4;
          background: var(--bg-2); border: 1px solid var(--bg-3);
          border-radius: 3px; padding: 4px; max-height: 24vh; overflow: auto;
        }
        .mv .row { display: grid; grid-template-columns: 50px 1fr 130px; gap: 8px; padding: 0 4px; }
        .mv .row:hover { background: var(--bg-3); }
        .mv .row.region-shade { border-left: 2px solid; }
        .mv .row .a { color: var(--warn); }
        .mv .row .h { color: var(--fg); white-space: pre; }
        .mv .row .r { color: var(--fg-dim); font-size: 11px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
        .mv .region-banner {
          display: flex; gap: 8px; align-items: baseline;
          font-size: 11px; margin: 4px 0 6px;
          color: var(--fg-dim);
        }
        .mv .region-banner .name { color: var(--accent); font-weight: 600; }
      </style>
      <h2 style="margin-top:14px;">Memory</h2>
      <div class="mv">
        <div class="ctrl">
          <span class="dim">addr</span>
          <input id="mv-addr" placeholder="0x0200" value="0x0200" />
          <span class="dim">len</span>
          <input id="mv-len" class="len" value="64" />
          <button id="mv-go">Read</button>
          <button id="mv-pc" title="Jump to current PC">@PC</button>
        </div>
        <div id="mv-banner" class="region-banner"></div>
        <div id="mv-body" class="dump dim">no instance selected</div>
      </div>
    `;
    this.addrInput = this.querySelector("#mv-addr");
    this.lenInput  = this.querySelector("#mv-len");
    this.body      = this.querySelector("#mv-body");
    this.banner    = this.querySelector("#mv-banner");

    this.querySelector("#mv-go").addEventListener("click", () => this.refresh());
    this.querySelector("#mv-pc").addEventListener("click", () => this.jumpToPc());
    this.addrInput.addEventListener("keydown", e => { if (e.key === "Enter") this.refresh(); });
    this.lenInput.addEventListener("keydown",  e => { if (e.key === "Enter") this.refresh(); });

    store.addEventListener("select", () => { this.body.textContent = "no halt event yet"; this.banner.textContent = ""; });
    store.addEventListener("ws:halt", () => this.refresh());
    store.addEventListener("static-docs-loaded", () => this.renderRegionsLater());
  }

  renderRegionsLater() {
    if (this.bytes) this.render();   // re-render if regions arrived late
  }

  async jumpToPc() {
    if (!store.selectedId) return;
    try {
      const r = await fetch(`/api/instances/${store.selectedId}/registers`).then(r => r.json());
      if (r.pc != null) {
        this.addrInput.value = "0x" + r.pc.toString(16).toUpperCase().padStart(4, "0");
        this.refresh();
      }
    } catch {}
  }

  async refresh() {
    if (!store.selectedId) return;
    const addr = parseInt(this.addrInput.value.trim(), 0);
    const len  = parseInt(this.lenInput.value.trim(), 0);
    if (!Number.isFinite(addr) || !Number.isFinite(len) || len < 1 || len > 4096) {
      this.body.textContent = "bad addr or len";
      return;
    }
    this.addr = addr & 0xFFFF;
    this.len = len;
    try {
      const r = await fetch(`/api/instances/${store.selectedId}/memory?addr=${this.addr}&length=${this.len}`);
      if (!r.ok) { this.body.textContent = `read failed: ${await r.text()}`; return; }
      const d = await r.json();
      this.bytes = hexToBytes(d.bytes_hex);
      this.render();
    } catch (e) {
      this.body.textContent = `error: ${e.message}`;
    }
  }

  render() {
    const region = store.regionFor(this.addr);
    if (region) {
      this.banner.innerHTML = `
        <span class="name">${escapeHtml(region.name)}</span>
        <span>${escapeHtml(region.summary || "")}</span>
      `;
    } else {
      this.banner.innerHTML = `<span class="dim">no documented region for $${hex(this.addr, 4)}</span>`;
    }

    const rows = [];
    for (let off = 0; off < this.bytes.length; off += 16) {
      const rowAddr = (this.addr + off) & 0xFFFF;
      const slice = this.bytes.slice(off, off + 16);
      const rowRegion = store.regionFor(rowAddr);
      const shade = rowRegion ? `region-shade` : "";
      const shadeColor = rowRegion ? regionColor(rowRegion.kind) : "transparent";

      const hexCells = [];
      const asciiChars = [];
      for (let i = 0; i < 16; i++) {
        if (i < slice.length) {
          const b = slice[i];
          hexCells.push(hex(b, 2));
          asciiChars.push((b >= 0x20 && b < 0x7F) ? String.fromCharCode(b) : ".");
        } else {
          hexCells.push("  "); asciiChars.push(" ");
        }
        if (i === 7) hexCells.push(" ");
      }
      const hexStr = hexCells.join(" ");
      const asciiStr = asciiChars.join("");

      const title = rowRegion ? `${rowRegion.name}: ${rowRegion.summary || ""}` : "";

      rows.push(`
        <div class="row ${shade}" style="border-color:${shadeColor};" title="${escapeHtml(title)}">
          <span class="a">${hex(rowAddr, 4)}</span>
          <span class="h">${hexStr}</span>
          <span class="r">${escapeHtml(asciiStr)}</span>
        </div>
      `);
    }
    this.body.className = "dump";
    this.body.innerHTML = rows.join("");
  }
}

function hexToBytes(s) {
  const out = new Uint8Array(s.length / 2);
  for (let i = 0; i < out.length; i++) out[i] = parseInt(s.substr(i * 2, 2), 16);
  return out;
}

function hex(v, w) {
  return v.toString(16).toUpperCase().padStart(w, "0");
}

function regionColor(kind) {
  const map = {
    "ram-dp":      "#e8c060",
    "ram-stack":   "#e87070",
    "ram-fb":      "#6bd0a0",
    "ram-scratch": "#6bd0a050",
    "ram-game":    "#6bd0a080",
    "ram-iv":      "#ff6b8a",
    "ram":         "#88aabb",
    "cart-code":   "#aa88ff",
    "io-pia":      "#ffaa44",
    "io-gime":     "#ff66aa",
    "io-mmu":      "#ff66aa",
    "io-palette":  "#cc66ff",
    "io-sam":      "#aaaaff",
    "io-reserved": "#666688",
    "io":          "#666688",
    "rom-vec":     "#bb88ff",
  };
  return map[kind] || "var(--fg-dim)";
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

customElements.define("memory-view", MemoryView);
