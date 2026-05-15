import { store } from "/static/store.js";

class SymbolContext extends HTMLElement {
  constructor() {
    super();
    this.lastAddr = null;
  }

  connectedCallback() {
    this.innerHTML = `
      <style>
        .sc { font-size: 12px; line-height: 1.4; }
        .sc .head { display: flex; gap: 8px; align-items: baseline; }
        .sc .sym { color: var(--accent); font-family: var(--mono); font-weight: 600; }
        .sc .off { color: var(--fg-dim); font-family: var(--mono); }
        .sc .addr { color: var(--warn); font-family: var(--mono); font-size: 11px; }
        .sc .summary { color: var(--fg); margin-top: 4px; }
        .sc .wiki-link {
          display: inline-block; margin-top: 6px;
          color: var(--accent); text-decoration: none; font-size: 11px;
        }
        .sc .wiki-link:hover { text-decoration: underline; }
        .sc .nope { color: var(--fg-dim); font-style: italic; }
      </style>
      <h2 style="margin-top:14px;">Symbol context</h2>
      <div id="sc-body" class="sc dim">no halt event yet</div>
    `;
    this.body = this.querySelector("#sc-body");

    store.addEventListener("select", () => {
      this.lastAddr = null;
      this.body.className = "sc dim";
      this.body.textContent = "no halt event yet";
    });
    store.addEventListener("ws:halt", (e) => {
      const pc = e.detail?.payload?.pc;
      if (typeof pc === "number") this.refresh(pc);
    });
  }

  async refresh(addr) {
    if (addr === this.lastAddr) return;
    this.lastAddr = addr;
    try {
      const r = await fetch(`/api/symbols/lookup?addr=${addr}`);
      if (!r.ok) {
        this.body.className = "sc";
        this.body.innerHTML = `<span class="nope">no symbol near $${hex(addr, 4)}</span>`;
        return;
      }
      const d = await r.json();
      if (this.lastAddr !== addr) return;
      const offTxt = d.offset === 0 ? "" : ` <span class="off">+${d.offset}</span>`;
      const wikiTxt = d.wiki
        ? `<a class="wiki-link" target="_blank" href="https://github.com/Rastamafugg/ladybug/blob/main/wiki/${d.wiki}">wiki: ${d.wiki} →</a>`
        : "";
      const summaryTxt = d.summary
        ? `<div class="summary">${escapeHtml(d.summary)}</div>`
        : `<div class="summary nope">no wiki annotation for this symbol — add to web/data/symbols.json.</div>`;
      this.body.className = "sc";
      this.body.innerHTML = `
        <div class="head">
          <span class="sym">${escapeHtml(d.name)}</span>
          ${offTxt}
          <span class="addr">$${hex(d.addr, 4)} (PC at $${hex(addr, 4)})</span>
        </div>
        ${summaryTxt}
        ${wikiTxt}
      `;
    } catch (e) {
      this.body.className = "sc err";
      this.body.textContent = `lookup error: ${e.message}`;
    }
  }
}

function hex(v, w) {
  return v.toString(16).toUpperCase().padStart(w, "0");
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

customElements.define("symbol-context", SymbolContext);
