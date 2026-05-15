// Shared application state + WebSocket plumbing.
// In its own module so component files can import it without creating a
// circular dependency through app.js.

class Store extends EventTarget {
  constructor() {
    super();
    this.instances = [];
    this.selectedId = null;
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

  async createInstance(name) {
    const r = await fetch("/api/instances", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ name }),
    });
    if (!r.ok) throw new Error(await r.text());
    await this.refreshInstances();
  }

  async deleteInstance(id) {
    await fetch(`/api/instances/${id}`, { method: "DELETE" });
    if (this.selectedId === id) this.select(null);
    await this.refreshInstances();
  }

  select(id) {
    this.selectedId = id;
    if (this.ws) { this.ws.close(); this.ws = null; }
    if (id) {
      const proto = location.protocol === "https:" ? "wss" : "ws";
      this.ws = new WebSocket(`${proto}://${location.host}/ws/instances/${id}`);
      this.ws.onmessage = (e) => {
        const ev = JSON.parse(e.data);
        this.dispatchEvent(new CustomEvent(`ws:${ev.kind}`, { detail: ev }));
        this.dispatchEvent(new CustomEvent("ws", { detail: ev }));
      };
    }
    this.dispatchEvent(new CustomEvent("select", { detail: id }));
    if (id) this.fetchHaltSnapshot(id);
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
