import { store } from "/static/store.js";

class RegisterView extends HTMLElement {
  connectedCallback() {
    this.render(null);
    store.addEventListener("ws:halt", (e) => this.render(e.detail.payload));
    store.addEventListener("select", () => this.render(null));
  }

  render(p) {
    const regs = p?.registers || {};
    const pars = p?.pars || [];
    const pal = p?.palette || [];

    const r = (k, w = 2) => regs[k] != null ? regs[k].toString(16).padStart(w, "0").toUpperCase() : "—";

    this.innerHTML = `
      <h2>Registers</h2>
      <div class="mono">
        A=${r("a")}  B=${r("b")}  X=${r("x", 4)}  Y=${r("y", 4)}<br/>
        U=${r("u", 4)} S=${r("s", 4)} PC=${r("pc", 4)} DP=${r("dp")}<br/>
        CC=${r("cc")}
      </div>
      <h2 style="margin-top:10px;">MMU PARs</h2>
      <div class="mono">${
        pars.length === 16
          ? pars.map((v, i) => `${i.toString(16).toUpperCase()}:${v.toString(16).padStart(2, "0").toUpperCase()}`).join(" ")
          : '<span class="dim">unknown</span>'
      }</div>
      <h2 style="margin-top:10px;">Palette</h2>
      <div style="display:grid; grid-template-columns:repeat(8,1fr); gap:2px;">
        ${pal.length === 16
          ? pal.map((rgb) => `<div style="aspect-ratio:1; background:${rgb}; border:1px solid #0008;"></div>`).join("")
          : '<span class="dim">unknown</span>'}
      </div>
    `;
  }
}

customElements.define("register-view", RegisterView);
