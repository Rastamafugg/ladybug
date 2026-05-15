import { store } from "/static/store.js";

class SourceView extends HTMLElement {
  connectedCallback() {
    this.innerHTML = `
      <h2>Source</h2>
      <div class="dim">.lst-driven source pane with click-to-breakpoint is not yet implemented.</div>
    `;
    // TODO: load build/ladybug.lst via an /api/source endpoint, render with
    // gutter dots for breakpoints, ▶ marker at current PC.
  }
}
customElements.define("source-view", SourceView);
