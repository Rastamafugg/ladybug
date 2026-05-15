import { store } from "/static/store.js";

class MemoryView extends HTMLElement {
  connectedCallback() {
    this.innerHTML = `
      <h2 style="margin-top:14px;">Memory</h2>
      <div class="dim">Hex dump pane not yet implemented.</div>
    `;
    // TODO: address input, length, periodic refresh via /api/instances/{id}/memory
  }
}
customElements.define("memory-view", MemoryView);
