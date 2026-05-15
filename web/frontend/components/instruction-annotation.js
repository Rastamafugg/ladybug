import { store } from "/static/store.js";

class InstructionAnnotation extends HTMLElement {
  constructor() {
    super();
    this.lastAddr = null;
  }

  connectedCallback() {
    this.innerHTML = `
      <style>
        .ia { font-size: 12px; line-height: 1.4; }
        .ia .head {
          display: flex; align-items: baseline; gap: 10px;
          margin-bottom: 4px;
        }
        .ia .addr { color: var(--warn); font-family: var(--mono); }
        .ia .bytes { color: var(--fg-dim); font-family: var(--mono); }
        .ia .disasm { color: var(--accent); font-family: var(--mono); font-weight: 600; font-size: 13px; }
        .ia .summary { color: var(--fg); margin: 4px 0 6px; }
        .ia .row { display: grid; grid-template-columns: 60px 1fr; gap: 6px; margin: 2px 0; }
        .ia .row .label { color: var(--fg-dim); text-align: right; }
        .ia .row .value { color: var(--fg); font-family: var(--mono); }
        .ia .row .value.effect { color: var(--ok); }
        .ia .cc-row { display: flex; flex-wrap: wrap; gap: 4px; }
        .ia .cc-chip {
          padding: 0px 4px; border-radius: 2px;
          background: var(--bg-2); border: 1px solid var(--bg-3);
          font-family: var(--mono); font-size: 11px;
          color: var(--fg-dim);
        }
        .ia .cc-chip.active { color: var(--accent); border-color: #4a4a6a; }
        .ia .notes { margin-top: 6px; }
        .ia .note { color: var(--warn); font-size: 11px; padding: 2px 0; }
        .ia .note.warn-emoji { color: var(--err); }
        .ia .wiki-link {
          display: inline-block; margin-top: 6px;
          color: var(--accent); text-decoration: none; font-size: 11px;
        }
        .ia .wiki-link:hover { text-decoration: underline; }
        .ia.unknown .disasm { color: var(--err); }
      </style>
      <h2>Instruction</h2>
      <div id="ia-body" class="ia dim">no instance selected</div>
    `;
    this.body = this.querySelector("#ia-body");

    store.addEventListener("select", () => this.clear());
    store.addEventListener("ws:halt", (e) => {
      const pc = e.detail?.payload?.pc;
      if (typeof pc === "number") this.refresh(pc);
    });
  }

  clear() {
    this.lastAddr = null;
    this.body.className = "ia dim";
    this.body.textContent = "no instance selected";
  }

  async refresh(addr) {
    if (!store.selectedId) return;
    if (addr === this.lastAddr) return;
    this.lastAddr = addr;
    this.body.className = "ia dim";
    this.body.textContent = `decoding $${hex(addr, 4)}…`;
    try {
      const r = await fetch(`/api/decode/${store.selectedId}?addr=${addr}&len=4`);
      if (!r.ok) {
        this.body.className = "ia err";
        this.body.textContent = `decode failed: ${await r.text()}`;
        return;
      }
      const d = await r.json();
      // Ignore stale results if PC moved on while we were waiting.
      if (d.addr !== this.lastAddr) return;
      this.render(d);
    } catch (e) {
      this.body.className = "ia err";
      this.body.textContent = `decode error: ${e.message}`;
    }
  }

  render(d) {
    const cls = d.unknown ? "ia unknown" : "ia";
    const cycles = renderCycles(d.cycles);
    const ccRow = renderCC(d.cc);
    const notes = (d.notes || []).map(n => {
      const isWarn = n.startsWith("⚠");
      return `<div class="note ${isWarn ? "warn-emoji" : ""}">${escapeHtml(n)}</div>`;
    }).join("");
    const wikiLink = d.wiki
      ? `<a class="wiki-link" target="_blank" href="https://github.com/Rastamafugg/ladybug/blob/main/wiki/${d.wiki}">wiki: ${d.wiki} →</a>`
      : "";

    const operandJson = renderOperand(d.operand);

    this.body.className = cls;
    this.body.innerHTML = `
      <div class="head">
        <span class="addr">$${hex(d.addr, 4)}</span>
        <span class="bytes">${escapeHtml(d.bytes || "")}</span>
        <span class="disasm">${escapeHtml(d.disasm || "??")}</span>
      </div>
      <div class="summary">${escapeHtml(d.summary || "")}</div>
      ${d.effect ? `<div class="row"><span class="label">effect</span><span class="value effect">${escapeHtml(d.effect)}</span></div>` : ""}
      ${cycles  ? `<div class="row"><span class="label">cycles</span><span class="value">${cycles}</span></div>` : ""}
      ${ccRow   ? `<div class="row"><span class="label">CC</span><span class="value cc-row">${ccRow}</span></div>` : ""}
      ${operandJson ? `<div class="row"><span class="label">operand</span><span class="value">${operandJson}</span></div>` : ""}
      ${notes  ? `<div class="notes">${notes}</div>` : ""}
      ${wikiLink}
    `;
  }
}

function renderCycles(c) {
  if (c == null) return "";
  if (typeof c === "number") return String(c);
  if (typeof c === "object" && c.min != null) {
    const range = c.min === c.max ? String(c.min) : `${c.min}-${c.max}`;
    return `${range} <span class="dim">— ${escapeHtml(c.note || "")}</span>`;
  }
  return escapeHtml(String(c));
}

function renderCC(cc) {
  if (!cc || typeof cc !== "object") return "";
  const entries = Object.entries(cc).filter(([k]) => k !== "comment");
  if (entries.length === 0) return "";
  return entries.map(([bit, eff]) => {
    const active = eff && eff !== "-" && eff !== "0";
    return `<span class="cc-chip ${active ? "active" : ""}" title="${escapeHtml(String(eff))}">${escapeHtml(bit)}</span>`;
  }).join("");
}

function renderOperand(op) {
  if (!op || Object.keys(op).length === 0) return "";
  // Pretty-print useful fields; hide internal bookkeeping.
  const keep = ["imm8", "imm16", "ea", "ea_via", "target", "offset", "form", "register", "postbyte", "src", "dst", "regs"];
  const parts = [];
  for (const k of keep) {
    if (op[k] == null) continue;
    let v = op[k];
    if (typeof v === "number") {
      if (k === "imm8") v = "$" + hex(v, 2);
      else if (k === "imm16" || k === "ea" || k === "ea_via" || k === "target") v = "$" + hex(v, 4);
      else if (k === "offset") v = (v >= 0 ? "+" : "") + v;
      else if (k === "postbyte") v = "$" + hex(v, 2);
    } else if (Array.isArray(v)) {
      v = v.join(",");
    }
    parts.push(`${k}=${escapeHtml(String(v))}`);
  }
  return parts.join("  ");
}

function hex(v, w) {
  return v.toString(16).toUpperCase().padStart(w, "0");
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

customElements.define("instruction-annotation", InstructionAnnotation);
