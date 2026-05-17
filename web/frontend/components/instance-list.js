import { store } from "/static/store.js";

class InstanceList extends HTMLElement {
  connectedCallback() {
    this.render();
    store.addEventListener("instances", () => this.render());
    store.addEventListener("select", () => this.render());
  }

  render() {
    const items = store.instances.map((i) => `
      <button class="row ${i.id === store.selectedId ? "selected" : ""}" data-id="${i.id}">
        <div>${escapeHtml(i.name)}</div>
        <div class="dim mono">:${i.monitor_port} · ${i.state}</div>
      </button>
    `).join("");

    this.innerHTML = `
      <h2>Instances</h2>
      <div id="list">${items || '<div class="dim">none</div>'}</div>
      <div style="margin-top:10px; display:flex; gap:4px;">
        <input id="new-name" placeholder="name" style="flex:1; min-width:0;
               background:var(--bg-2); color:var(--fg);
               border:1px solid var(--bg-3); border-radius:3px; padding:3px 6px;" />
        <button id="new-go" style="background:var(--bg-3); color:var(--fg);
                border:1px solid #383850; border-radius:3px; padding:3px 8px; cursor:pointer;">+</button>
      </div>
      ${store.selectedId ? `<button id="kill" class="row" style="margin-top:10px; color:var(--err);">stop ${escapeHtml(currentName())}</button>` : ""}
    `;

    this.querySelectorAll("button.row[data-id]").forEach((b) => {
      b.addEventListener("click", () => store.select(b.dataset.id));
    });
    this.querySelector("#new-go").addEventListener("click", () => {
      const name = this.querySelector("#new-name").value.trim() || `inst-${Date.now() % 10000}`;
      store.createInstance(name).catch((e) => alert(e.message));
    });
    this.querySelector("#kill")?.addEventListener("click", () => {
      if (confirm("Stop this instance?")) store.deleteInstance(store.selectedId);
    });
  }
}

function currentName() {
  return store.instances.find((i) => i.id === store.selectedId)?.name || "";
}
function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

customElements.define("instance-list", InstanceList);
