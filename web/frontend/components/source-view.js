import { store } from "/static/store.js";

class SourceView extends HTMLElement {
  constructor() {
    super();
    this.lines = [];
    // addr -> { id: string, enabled: bool }
    this.bpByAddr = new Map();
    this.currentPc = null;
  }

  connectedCallback() {
    this.innerHTML = `
      <h2>Source</h2>
      <div id="src-status" class="dim">no listing loaded</div>
      <div id="src-body" class="mono" style="
        font-size:12px; line-height:1.35; white-space:pre;
        max-height:55vh; overflow:auto;
        background:var(--bg-2); border:1px solid var(--bg-3);
        border-radius:3px; padding:4px 0;">
      </div>
      <style>
        .src-row { display:grid; grid-template-columns: 18px 44px 1fr; gap:6px; padding:0 6px; cursor: default; }
        .src-row.executable { cursor: pointer; }
        .src-row.executable:hover { background: var(--bg-3); }
        .src-row.pc { background: rgba(255,107,138,0.18); }
        .src-row .gut { color: var(--fg-dim); text-align:center; user-select:none; }
        .src-row .gut.bp { color: var(--err); }
        .src-row .gut.bp-disabled { color: var(--fg-dim); }
        .src-row .gut.pc { color: var(--accent); }
        .src-row .addr { color: var(--warn); }
        .src-row .text { color: var(--fg); }
      </style>
    `;
    this.body = this.querySelector("#src-body");
    this.status = this.querySelector("#src-status");
    this.loadSource();
    store.addEventListener("ws:halt", (e) => this.onHalt(e.detail));
    store.addEventListener("select", () => { this.currentPc = null; this.render(); });
    store.addEventListener("build", () => this.loadSource());
  }

  async loadSource() {
    try {
      const r = await fetch("/api/source");
      if (!r.ok) { this.status.textContent = await r.text(); return; }
      const data = await r.json();
      this.lines = data.lines;
      this.status.textContent = `${data.path} · ${this.lines.length} lines`;
      this.render();
    } catch (e) {
      this.status.textContent = `source load failed: ${e.message}`;
    }
  }

  onHalt(ev) {
    const pc = ev.payload?.pc;
    if (typeof pc === "number") {
      this.currentPc = pc;
      this.render();
      // scroll to the PC line
      const el = this.querySelector(".src-row.pc");
      if (el) el.scrollIntoView({ block: "center" });
    }
  }

  render() {
    const rows = this.lines.map((l) => {
      const isExec = l.addr != null;
      const isPc = isExec && l.addr === this.currentPc;
      const bp = isExec ? this.bpByAddr.get(l.addr) : undefined;
      let gut = " ", gutClass = "gut";
      if (bp && bp.enabled)        { gut = "●"; gutClass = "gut bp"; }
      else if (bp && !bp.enabled)  { gut = "○"; gutClass = "gut bp-disabled"; }
      else if (isPc)               { gut = "▶"; gutClass = "gut pc"; }
      const addr = isExec ? l.addr.toString(16).padStart(4, "0").toUpperCase() : "";
      return `<div class="src-row${isExec ? " executable" : ""}${isPc ? " pc" : ""}" data-addr="${l.addr ?? ""}">
        <span class="${gutClass}">${gut}</span>
        <span class="addr">${addr}</span>
        <span class="text">${escapeHtml(l.text)}</span>
      </div>`;
    }).join("");
    this.body.innerHTML = rows;
    this.body.querySelectorAll(".src-row.executable").forEach((el) => {
      el.addEventListener("click", () => this.cycleBp(parseInt(el.dataset.addr, 10)));
    });
  }

  // Click cycles:   (none) -> enabled -> disabled -> (none)
  async cycleBp(addr) {
    if (!store.selectedId) return;
    const bp = this.bpByAddr.get(addr);
    // Defensive: if a legacy/corrupt entry has no id, drop it and treat as none.
    if (bp && !bp.id) this.bpByAddr.delete(addr);
    const iid = store.selectedId;
    try {
      if (!bp || !bp.id) {
        const r = await fetch(`/api/instances/${iid}/breakpoints`, {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ addr }),
        });
        if (!r.ok) throw new Error(await r.text());
        const data = await r.json();
        this.bpByAddr.set(addr, { id: data.id, enabled: true });
      } else if (bp.enabled) {
        const r = await fetch(`/api/instances/${iid}/breakpoints/${bp.id}`, {
          method: "PATCH",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ enabled: false }),
        });
        if (!r.ok) throw new Error(await r.text());
        bp.enabled = false;
      } else {
        const r = await fetch(`/api/instances/${iid}/breakpoints/${bp.id}`, { method: "DELETE" });
        if (!r.ok) throw new Error(await r.text());
        this.bpByAddr.delete(addr);
      }
    } catch (e) {
      alert(`bp: ${e.message}`);
    }
    this.render();
  }
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

customElements.define("source-view", SourceView);
