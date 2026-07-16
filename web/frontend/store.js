// Shared application state + WebSocket plumbing.
// In its own module so component files can import it without creating a
// circular dependency through app.js.

class Store extends EventTarget {
  constructor() {
    super();
    this.instances = [];
    this.selectedId = null;
    // Live run state of the selected instance ("running", "halted", …),
    // tracked from ws:state events. null until the first state event.
    this.runState = null;
    this.ws = null;
    // Static documentation, fetched once on startup.
    this.regions = [];
    this.registersDoc = null;
  }

  async loadStaticDocs() {
    try {
      const [r1, r2] = await Promise.all([
        fetch("/api/regions").then(r => r.json()),
        fetch("/api/registers-doc").then(r => r.json()),
      ]);
      this.regions = r1;
      this.registersDoc = r2;
      this.dispatchEvent(new CustomEvent("static-docs-loaded"));
    } catch (e) {
      console.warn("static docs failed to load", e);
    }
  }

  regionFor(addr) {
    for (const r of this.regions) {
      const lo = parseInt(r.lo, 16);
      const hi = parseInt(r.hi, 16);
      if (addr >= lo && addr <= hi) return r;
    }
    return null;
  }

  async refreshInstances() {
    const r = await fetch("/api/instances");
    this.instances = await r.json();
    this.dispatchEvent(new CustomEvent("instances", { detail: this.instances }));
  }

  async createInstance(name, romPath) {
    const body = { name };
    if (romPath) body.rom_path = romPath;
    const r = await fetch("/api/instances", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!r.ok) throw new Error(await r.text());
    await this.refreshInstances();
  }

  async listRoms() {
    try {
      const r = await fetch("/api/roms");
      if (!r.ok) return [];
      return await r.json();
    } catch {
      return [];
    }
  }

  async deleteInstance(id) {
    await fetch(`/api/instances/${id}`, { method: "DELETE" });
    if (this.selectedId === id) this.select(null);
    await this.refreshInstances();
  }

  select(id) {
    this.selectedId = id;
    this.runState = null;
    if (this.ws) { this.ws.close(); this.ws = null; }
    if (id) {
      const proto = location.protocol === "https:" ? "wss" : "ws";
      this.ws = new WebSocket(`${proto}://${location.host}/ws/instances/${id}`);
      let synced = false;
      this.ws.onmessage = (e) => {
        const ev = JSON.parse(e.data);
        if (ev.kind === "state") {
          this.runState = ev.payload?.state ?? null;
          // The server sends the current state as the first WS event.
          // Only pull a register snapshot for an already-halted instance;
          // synthesizing a halt for a running one painted stale panes.
          if (!synced) {
            synced = true;
            if (this.runState === "halted") this.fetchHaltSnapshot(id);
          }
        }
        this.dispatchEvent(new CustomEvent(`ws:${ev.kind}`, { detail: ev }));
        this.dispatchEvent(new CustomEvent("ws", { detail: ev }));
      };
    }
    this.dispatchEvent(new CustomEvent("select", { detail: id }));
  }

  // Pull current registers via REST so a freshly-selected (already-halted)
  // instance fills its panes without waiting for the next halt event.
  async fetchHaltSnapshot(id) {
    try {
      const r = await fetch(`/api/instances/${id}/registers`);
      if (!r.ok) return;
      const regs = await r.json();
      this.dispatchEvent(new CustomEvent("ws:halt", {
        detail: { kind: "halt", instance_id: id, payload: { pc: regs.pc, registers: regs } },
      }));
    } catch {}
  }

  async build() {
    const el = document.getElementById("status-build");
    if (el) { el.textContent = "building…"; el.className = ""; }
    const r = await fetch("/api/build", { method: "POST" });
    const result = await r.json();
    if (el) {
      if (result.ok) { el.textContent = `build ✓ ${result.rom_size}B`; el.className = "ok"; }
      else { el.textContent = "build failed"; el.className = "err"; }
    }
    this.dispatchEvent(new CustomEvent("build", { detail: result }));
  }
}

export const store = new Store();
window.store = store;
