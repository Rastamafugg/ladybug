import { store } from "/static/store.js";

class FramebufferView extends HTMLElement {
  connectedCallback() {
    this.innerHTML = `
      <h2>Framebuffer</h2>
      <img id="fb" alt="framebuffer"
           style="width:100%; image-rendering:pixelated; background:#000;
                  border:1px solid var(--bg-3); border-radius:3px;" />
      <div class="dim mono" id="fb-meta" style="margin-top:4px;">—</div>
    `;
    this.img = this.querySelector("#fb");
    this.meta = this.querySelector("#fb-meta");
    store.addEventListener("select", () => this.refresh());
    store.addEventListener("ws:halt", () => this.refresh());
    this.refresh();
  }

  refresh() {
    if (!store.selectedId) {
      this.img.removeAttribute("src");
      this.meta.textContent = "no instance selected";
      return;
    }
    const t = Date.now();
    this.img.src = `/api/instances/${store.selectedId}/framebuffer.png?t=${t}`;
    this.meta.textContent = `last refresh ${new Date(t).toLocaleTimeString()}`;
  }
}

customElements.define("framebuffer-view", FramebufferView);
