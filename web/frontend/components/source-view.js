import { store } from "/static/store.js";

class SourceView extends HTMLElement {
  constructor() {
    super();
    this.lines = [];
    // addr -> { id: string }
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
        .src-row.bp .gut { color: var(--err); }
        .src-row.pc .gut { color: var(--accent); }
        .src-row.bp.pc .gut { color: var(--err); }
        .src-row .addr { color: var(--warn); }
        .src-row .text { color: var(--fg); }
      </style>
    `;
    this.body = this.querySelector("#src-body");
    this.status = this.querySelector("#src-status");
    this.loadSource();
    store.addEventListener("ws:halt", (e) => this.onHalt(e.detail));
    store.addEventListener("select", () => {
      this.currentPc = null;
      this.bpByAddr.clear();
      this.loadSource();
    });
    store.addEventListener("build", () => this.loadSource());
  }

  async loadSource() {
    try {
      const iid = store.selectedId;
      const url = iid ? `/api/source/${iid}` : "/api/source";
      const r = await fetch(url);
      if (!r.ok) {
        this.status.textContent = await r.text();
        this.lines = [];
        this.body.innerHTML = "";
        return;
      }
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
      const hasBp = isExec && this.bpByAddr.has(l.addr);
      const gut = isPc ? "▶" : (hasBp ? "●" : " ");
      const rowClasses = ["src-row"];
      if (isExec) rowClasses.push("executable");
      if (hasBp) rowClasses.push("bp");
      if (isPc) rowClasses.push("pc");
      const addr = isExec ? l.addr.toString(16).padStart(4, "0").toUpperCase() : "";
      return `<div class="${rowClasses.join(" ")}" data-addr="${l.addr ?? ""}">
        <span class="gut">${gut}</span>
        <span class="addr">${addr}</span>
        <span class="text">${escapeHtml(l.text)}</span>
      </div>`;
    }).join("");
    this.body.innerHTML = rows;
    this.body.querySelectorAll(".src-row.executable").forEach((el) => {
      el.addEventListener("click", () => this.cycleBp(parseInt(el.dataset.addr, 10)));
    });
  }

  // Click toggles: (none) -> set -> (none). Monitor protocol v0.6 has no
  // per-BP enable/disable, so there's no intermediate disabled state.
  async cycleBp(addr) {
    if (!store.selectedId) return;
    const bp = this.bpByAddr.get(addr);
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
        this.bpByAddr.set(addr, { id: data.id });
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
