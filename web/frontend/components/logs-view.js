import { store } from "/static/store.js";

class LogsView extends HTMLElement {
  connectedCallback() {
    this.innerHTML = `
      <h2>Controls</h2>
      <div style="display:flex; gap:4px; flex-wrap:wrap;">
        <button data-act="continue">Continue</button>
        <button data-act="step">Step</button>
        <button data-act="interrupt">Interrupt</button>
        <button data-act="reset">Reset</button>
      </div>
      <h2 style="margin-top:14px;">Log</h2>
      <pre id="log" class="mono" style="white-space:pre-wrap; background:var(--bg-2);
            padding:6px; border-radius:3px; max-height:60vh; overflow:auto;
            font-size:12px; margin:0;"></pre>
    `;
    this.log = this.querySelector("#log");

    this.querySelectorAll("button[data-act]").forEach((b) => {
      b.style.cssText = "background:var(--bg-3); color:var(--fg); border:1px solid #383850; border-radius:3px; padding:3px 8px; cursor:pointer;";
      b.addEventListener("click", () => this.act(b.dataset.act));
    });

    store.addEventListener("ws", (e) => this.append(e.detail));
    store.addEventListener("select", () => { this.log.textContent = ""; });
  }

  append(ev) {
    const line = `[${new Date().toLocaleTimeString()}] ${ev.kind}: ${JSON.stringify(ev.payload)}\n`;
    this.log.textContent += line;
    this.log.scrollTop = this.log.scrollHeight;
  }

  async act(action) {
    if (!store.selectedId) return;
    const r = await fetch(`/api/instances/${store.selectedId}/actions/${action}`, { method: "POST" });
    const result = await r.json();
    this.append({ kind: "action", payload: { action, ...result } });
  }
}
customElements.define("logs-view", LogsView);
