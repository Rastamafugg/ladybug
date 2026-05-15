import { store } from "/static/store.js";

// 6809 CC flag bits, MSB to LSB.
const CC_FLAGS = ["E", "F", "H", "I", "N", "Z", "V", "C"];

class RegisterView extends HTMLElement {
  connectedCallback() {
    this.innerHTML = `
      <style>
        .reg-grid {
          display: grid;
          grid-template-columns: auto auto auto auto;
          gap: 2px 12px;
          font-family: var(--mono);
          font-size: 13px;
        }
        .reg-grid .name { color: var(--fg-dim); text-align: right; cursor: help; }
        .reg-grid .name:hover { color: var(--accent); }
        .reg-grid .val  { color: var(--fg); }
        .reg-grid .val.wide { color: var(--accent); }
        .cc-row { display: flex; gap: 6px; font-family: var(--mono); font-size: 12px; margin-top: 4px; }
        .cc-row .bit { padding: 1px 5px; border-radius: 2px; border: 1px solid var(--bg-3); cursor: help; }
        .cc-row .bit:hover { border-color: var(--accent); }
        .cc-row .bit.set { background: var(--bg-3); color: var(--accent); border-color: #4a4a6a; }
        .cc-row .bit.unset { color: var(--fg-dim); }
      </style>
      <h2>Registers</h2>
      <div id="regs-body"><div class="dim">no data</div></div>
      <h2 style="margin-top:12px;">CC flags</h2>
      <div id="cc-body" class="dim">—</div>
    `;
    this.regsBody = this.querySelector("#regs-body");
    this.ccBody = this.querySelector("#cc-body");
    store.addEventListener("ws:halt", (e) => this.render(e.detail.payload));
    store.addEventListener("select", () => this.render(null));
  }

  render(p) {
    const regs = p?.registers || {};
    const hasRegs = regs && !regs._error && Object.keys(regs).length > 0;

    if (!hasRegs) {
      this.regsBody.innerHTML = `<div class="dim">no data</div>`;
      this.ccBody.innerHTML = `<span class="dim">—</span>`;
    } else {
      const A = regs.a, B = regs.b;
      const D = (A != null && B != null) ? ((A & 0xff) << 8) | (B & 0xff) : null;

      const row = (name, value, width = 2, wide = false) => {
        const doc = regDoc(name);
        const title = doc ? `${doc.summary}${doc.wiki ? "\n→ wiki/" + doc.wiki : ""}` : "";
        return `
          <span class="name" title="${escapeHtml(title)}">${name}</span>
          <span class="val${wide ? " wide" : ""}">${value != null ? hex(value, width) : "—"}</span>
        `;
      };

      this.regsBody.innerHTML = `
        <div class="reg-grid">
          ${row("PC", regs.pc, 4, true)}
          ${row("DP", regs.dp, 2)}
          ${row("S",  regs.s,  4, true)}
          ${row("U",  regs.u,  4, true)}
          ${row("X",  regs.x,  4, true)}
          ${row("Y",  regs.y,  4, true)}
          ${row("D",  D,       4, true)}
          ${row("CC", regs.cc, 2)}
          ${row("A",  A,       2)}
          ${row("B",  B,       2)}
        </div>
      `;

      // CC decoded
      if (regs.cc != null) {
        const cc = regs.cc;
        this.ccBody.innerHTML = `<div class="cc-row">${
          CC_FLAGS.map((f, i) => {
            const bit = 7 - i;
            const set = (cc >> bit) & 1;
            const doc = ccDoc(f);
            const title = doc ? doc.summary : "";
            return `<span class="bit ${set ? "set" : "unset"}" title="${escapeHtml(title)}">${f}</span>`;
          }).join("")
        }</div>`;
      } else {
        this.ccBody.innerHTML = `<span class="dim">—</span>`;
      }
    }

  }
}

function hex(v, w) {
  return v.toString(16).toUpperCase().padStart(w, "0");
}

function regDoc(name) {
  const all = store.registersDoc?.registers || [];
  return all.find(r => r.name === name);
}

function ccDoc(name) {
  const all = store.registersDoc?.cc_bits || [];
  return all.find(b => b.name === name);
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

customElements.define("register-view", RegisterView);
