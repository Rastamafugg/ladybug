import { store } from "/static/store.js";

// Default screen-memory window. The GIME vertical-offset regs ($FF9D/$FF9E)
// are write-only, so we cannot auto-resolve where the framebuffer actually
// lives. $E000 is a reasonable virtual default — the framebuffer is intended
// to occupy the top of the virtual map. The user can re-point it.
const DEFAULT_FB_ADDR = 0xE000;
const DEFAULT_FB_LEN = 256;

class FramebufferView extends HTMLElement {
  constructor() {
    super();
    this.hexOpen = true;
    this.hexAddr = DEFAULT_FB_ADDR;
    this.hexLen = DEFAULT_FB_LEN;
  }

  connectedCallback() {
    this.innerHTML = `
      <style>
        .fb-wrap { display: flex; gap: 8px; align-items: flex-start; }
        .fb-main { flex: 1 1 auto; min-width: 0; }
        .fb-side {
          flex: 0 0 auto; width: 280px;
          border: 1px solid var(--bg-3); border-radius: 3px;
          background: var(--bg-2);
        }
        .fb-side.collapsed { width: auto; }
        .fb-side summary {
          cursor: pointer; padding: 4px 6px;
          font-size: 11px; text-transform: uppercase;
          letter-spacing: 0.06em; color: var(--fg-dim);
          user-select: none;
        }
        .fb-side[open] summary { border-bottom: 1px solid var(--bg-3); }
        .fb-side .ctrl {
          display: flex; gap: 4px; align-items: center;
          font-size: 11px; padding: 4px 6px;
        }
        .fb-side .ctrl input {
          background: var(--bg); color: var(--fg);
          border: 1px solid var(--bg-3); border-radius: 2px;
          padding: 1px 4px; font-family: var(--mono); font-size: 11px;
          width: 70px;
        }
        .fb-side .ctrl input.len { width: 50px; }
        .fb-side .ctrl button {
          background: var(--bg-3); color: var(--fg);
          border: 1px solid #383850; border-radius: 2px;
          padding: 1px 6px; cursor: pointer; font-size: 11px;
        }
        .fb-side .dump {
          font-family: var(--mono); font-size: 11px; line-height: 1.35;
          padding: 4px 6px; max-height: 280px; overflow: auto;
          color: var(--fg);
        }
        .fb-side .dump .a { color: var(--warn); }
        .fb-side .dump .empty { color: var(--fg-dim); }
      </style>
      <h2>Framebuffer</h2>
      <div class="fb-wrap">
        <div class="fb-main">
          <img id="fb" alt="framebuffer"
               style="width:100%; image-rendering:pixelated; background:#000;
                      border:1px solid var(--bg-3); border-radius:3px;" />
          <div class="dim mono" id="fb-meta" style="margin-top:4px;">—</div>
        </div>
        <details class="fb-side" id="fb-side" open>
          <summary>Screen memory</summary>
          <div class="ctrl">
            <span class="dim">addr</span>
            <input id="fb-addr" value="0xE000" />
            <span class="dim">len</span>
            <input id="fb-len" class="len" value="256" />
            <button id="fb-go">Read</button>
          </div>
          <div id="fb-dump" class="dump empty">—</div>
        </details>
      </div>
    `;
    this.img = this.querySelector("#fb");
    this.meta = this.querySelector("#fb-meta");
    this.side = this.querySelector("#fb-side");
    this.addrInput = this.querySelector("#fb-addr");
    this.lenInput = this.querySelector("#fb-len");
    this.dump = this.querySelector("#fb-dump");

    this.querySelector("#fb-go").addEventListener("click", () => this.refreshHex());
    this.addrInput.addEventListener("keydown", e => { if (e.key === "Enter") this.refreshHex(); });
    this.lenInput.addEventListener("keydown",  e => { if (e.key === "Enter") this.refreshHex(); });

    store.addEventListener("select", () => { this.refreshImg(); this.dump.className = "dump empty"; this.dump.textContent = "no halt event yet"; });
    store.addEventListener("ws:halt", () => { this.refreshImg(); this.refreshHex(); });
    this.refreshImg();
  }

  refreshImg() {
    if (!store.selectedId) {
      this.img.removeAttribute("src");
      this.meta.textContent = "no instance selected";
      return;
    }
    const t = Date.now();
    this.img.src = `/api/instances/${store.selectedId}/framebuffer.png?t=${t}`;
    this.meta.textContent = `last refresh ${new Date(t).toLocaleTimeString()}`;
  }

  async refreshHex() {
    if (!store.selectedId) return;
    const addr = parseInt(this.addrInput.value.trim(), 0);
    const len  = parseInt(this.lenInput.value.trim(), 0);
    if (!Number.isFinite(addr) || !Number.isFinite(len) || len < 1 || len > 4096) {
      this.dump.className = "dump empty";
      this.dump.textContent = "bad addr or len";
      return;
    }
    try {
      const r = await fetch(`/api/instances/${store.selectedId}/memory?addr=${addr}&length=${len}`);
      if (!r.ok) {
        this.dump.className = "dump empty";
        this.dump.textContent = `read failed (${r.status})`;
        return;
      }
      const d = await r.json();
      this.renderHex(addr, hexToBytes(d.bytes_hex));
    } catch (e) {
      this.dump.className = "dump empty";
      this.dump.textContent = `error: ${e.message}`;
    }
  }

  renderHex(addr, bytes) {
    const rows = [];
    for (let off = 0; off < bytes.length; off += 16) {
      const rowAddr = (addr + off) & 0xFFFF;
      const slice = bytes.slice(off, off + 16);
      const cells = [];
      for (let i = 0; i < 16; i++) {
        cells.push(i < slice.length ? hex(slice[i], 2) : "  ");
        if (i === 7) cells.push(" ");
      }
      rows.push(`<div><span class="a">${hex(rowAddr, 4)}</span> ${cells.join(" ")}</div>`);
    }
    this.dump.className = "dump";
    this.dump.innerHTML = rows.join("");
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

customElements.define("framebuffer-view", FramebufferView);
