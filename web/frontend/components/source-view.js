import { store } from "/static/store.js";

class SourceView extends HTMLElement {
  constructor() {
    super();
    this.lines = [];
    // addr -> breakpoint id[]; duplicates are legal in the monitor.
    this.bpByAddr = new Map();
    this.currentPc = null;
    this.bpBusy = false;
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
    this.syncBps();
    store.addEventListener("ws:halt", (e) => {
      this.onHalt(e.detail);
      this.syncBps(); // cheap; re-truths dots after reset/instance restart
    });
    store.addEventListener("ws:state", (e) => {
      // While running there is no current PC — drop the stale arrow.
      if (e.detail.payload?.state === "running" && this.currentPc !== null) {
        this.currentPc = null;
        this.render();
      }
    });
    store.addEventListener("select", () => {
      this.currentPc = null;
      this.loadSource();
      this.syncBps();
    });
    store.addEventListener("build", () => { this.loadSource(); this.syncBps(); });
  }

  // The emulator is the single source of truth for breakpoints: instances
  // restart (reset clears all BPs), selections change, duplicates are
  // legal. Re-pull the list rather than trusting our own click history.
  async syncBps() {
    const iid = store.selectedId;
    if (!iid) {
      if (this.bpByAddr.size) { this.bpByAddr.clear(); this.render(); }
      return;
    }
    try {
      const r = await fetch(`/api/instances/${iid}/breakpoints`);
      if (!r.ok) return;
      const list = await r.json();
      if (store.selectedId !== iid) return; // selection moved on mid-fetch
      const next = new Map();
      for (const b of list) {
        const ids = next.get(b.addr) ?? [];
        ids.push(String(b.id));
        next.set(b.addr, ids);
      }
      for (const ids of next.values()) ids.sort();
      const changed = next.size !== this.bpByAddr.size ||
        [...next].some(([a, ids]) => {
          const old = this.bpByAddr.get(a) ?? [];
          return ids.length !== old.length || ids.some((id, i) => id !== old[i]);
        });
      this.bpByAddr = next;
      if (changed) this.render();
    } catch {}
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
      const hasAddr = l.addr != null;
      // Data lines (fcb/fdb/...) keep their address for navigation but an
      // exec breakpoint there would never fire — don't offer the click.
      const isExec = hasAddr && l.exec;
      const isPc = isExec && l.addr === this.currentPc;
      const hasBp = isExec && this.bpByAddr.has(l.addr);
      const gut = isPc ? "▶" : (hasBp ? "●" : " ");
      const rowClasses = ["src-row"];
      if (isExec) rowClasses.push("executable");
      if (hasBp) rowClasses.push("bp");
      if (isPc) rowClasses.push("pc");
      const addr = hasAddr ? l.addr.toString(16).padStart(4, "0").toUpperCase() : "";
      return `<div class="${rowClasses.join(" ")}" data-addr="${l.addr ?? ""}">
        <span class="gut">${gut}</span>
        <span class="addr">${addr}</span>
        <span class="text">${escapeHtml(l.text)}</span>
      </div>`;
    }).join("");
    // Rebuilding innerHTML resets scrollTop; preserve it so re-renders
    // that aren't followed by a deliberate scrollIntoView (bp toggles,
    // run-state changes) don't yank the pane back to the top.
    const scrollTop = this.body.scrollTop;
    this.body.innerHTML = rows;
    this.body.scrollTop = scrollTop;
    this.body.querySelectorAll(".src-row.executable").forEach((el) => {
      el.addEventListener("click", () => this.cycleBp(parseInt(el.dataset.addr, 10)));
    });
  }

  // Click toggles: (none) -> set -> (none). Monitor protocol v0.6 has no
  // per-BP enable/disable, so there's no intermediate disabled state.
  async cycleBp(addr) {
    if (!store.selectedId) return;
    if (this.bpBusy) return; // one mutation at a time; double-clicks made duplicate BPs
    this.bpBusy = true;
    const bpIds = this.bpByAddr.get(addr) ?? [];
    const iid = store.selectedId;
    try {
      if (!bpIds.length) {
        const r = await fetch(`/api/instances/${iid}/breakpoints`, {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ addr }),
        });
        if (!r.ok) throw new Error(await r.text());
        const data = await r.json();
        this.bpByAddr.set(addr, [String(data.id)]);
      } else {
        // Clear every monitor breakpoint at this address. Older UI builds
        // could create duplicates, and hiding the dot after deleting only
        // one left an invisible breakpoint active in the emulator.
        for (const id of bpIds) {
          const r = await fetch(`/api/instances/${iid}/breakpoints/${id}`, { method: "DELETE" });
          if (!r.ok) throw new Error(await r.text());
        }
        this.bpByAddr.delete(addr);
      }
      this.render();
      await this.syncBps();
    } catch (e) {
      alert(`bp: ${e.message}`);
      // Local map may be stale (e.g. id from before an instance restart) —
      // recover by resyncing from the emulator instead of leaving a dot
      // that can never be cleared.
      await this.syncBps();
    } finally {
      this.bpBusy = false;
    }
  }
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

customElements.define("source-view", SourceView);
