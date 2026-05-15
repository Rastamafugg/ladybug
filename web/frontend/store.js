// Shared application state + WebSocket plumbing.
// In its own module so component files can import it without creating a
// circular dependency through app.js.

class Store extends EventTarget {
  constructor() {
    super();
    this.instances = [];
    this.selectedId = null;
    this.ws = null;
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
