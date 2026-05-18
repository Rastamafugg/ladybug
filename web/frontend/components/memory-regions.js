import { store } from "/static/store.js";

// Per-instance user-defined memory regions with v0 hex viewer.
// Regions auto-refresh on ws:halt for the ids currently expanded. CRUD
// hits /api/instances/{id}/regions; values come via the POST /values
// endpoint with the visible_ids set.

class MemoryRegions extends HTMLElement {
  constructor() {
    super();
    this.defs = [];                       // [{id,name,kind,length,...}]
    this.expanded = new Set();            // region ids currently shown
    this.values = new Map();              // id -> {base, bytes_hex, error}
    this.addOpen = false;                 // is the add-form visible
    this.addKind = "fixed";               // dropdown state for the add form
  }

  connectedCallback() {
    this.innerHTML = `
      <style>
        .mr h2 { margin-top: 14px; }
        .mr .toolbar { display:flex; gap:6px; align-items:center; margin-bottom:6px; }
        .mr .add-btn {
          background: var(--bg-3); color: var(--fg);
          border: 1px solid #383850; border-radius: 3px;
          padding: 2px 8px; cursor: pointer; font-size: 12px;
        }
        .mr .empty { color: var(--fg-dim); padding: 6px; font-style: italic; }
        .mr .region {
          border: 1px solid var(--bg-3); border-radius: 3px;
          margin-bottom: 6px; background: var(--bg-2);
        }
        .mr .region-head {
          display: grid;
          grid-template-columns: 16px 1fr 60px auto auto;
          gap: 6px; align-items: center;
          padding: 4px 8px;
          cursor: pointer;
          font-size: 12px;
          user-select: none;
        }
        .mr .region-head:hover { background: var(--bg-3); }
        .mr .arrow { color: var(--fg-dim); }
        .mr .nm { color: var(--fg); font-weight: 600; }
        .mr .expr { color: var(--fg-dim); font-family: var(--mono); font-size: 11px; }
        .mr .kind-badge {
          font-size: 10px; text-transform: uppercase;
          padding: 1px 5px; border-radius: 2px;
          background: var(--bg-3); color: var(--fg-dim);
        }
        .mr .del {
          background: transparent; border: none;
          color: var(--err); cursor: pointer; font-size: 14px;
          padding: 0 4px; line-height: 1;
        }
        .mr .body {
          border-top: 1px solid var(--bg-3);
          padding: 4px;
          font-family: var(--mono); font-size: 11px;
          max-height: 280px; overflow: auto;
        }
        .mr .row { display: grid; grid-template-columns: 50px 1fr 130px; gap: 8px; padding: 0 4px; }
        .mr .row:hover { background: var(--bg-3); }
        .mr .row .a { color: var(--warn); }
        .mr .row .h { color: var(--fg); white-space: pre; }
        .mr .row .r { color: var(--fg-dim); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
        .mr .err { color: var(--err); padding: 4px 8px; font-size: 11px; }
        .mr .add-form {
          border: 1px solid var(--bg-3); border-radius: 3px;
          background: var(--bg-2); padding: 6px 8px;
          margin-bottom: 6px;
          display: grid; grid-template-columns: auto 1fr; gap: 4px 8px;
          align-items: center; font-size: 12px;
        }
        .mr .add-form input, .mr .add-form select {
          background: var(--bg); color: var(--fg);
          border: 1px solid var(--bg-3); border-radius: 2px;
          padding: 2px 4px; font-family: var(--mono); font-size: 11px;
          width: 100%; box-sizing: border-box;
        }
        .mr .add-form .span2 { grid-column: 1 / span 2; display: flex; gap: 4px; justify-content: flex-end; }
      </style>
      <div class="mr">
        <h2>Regions</h2>
        <div class="toolbar">
          <button class="add-btn" id="mr-add">+ Add</button>
          <span class="dim" id="mr-meta"></span>
        </div>
        <div id="mr-add-form-wrap"></div>
        <div id="mr-list"><div class="empty">no instance selected</div></div>
      </div>
    `;
    this.listEl    = this.querySelector("#mr-list");
    this.formWrap  = this.querySelector("#mr-add-form-wrap");
    this.metaEl    = this.querySelector("#mr-meta");
    this.querySelector("#mr-add").addEventListener("click", () => {
      this.addOpen = !this.addOpen;
      this.renderForm();
    });

    store.addEventListener("select", () => {
      this.expanded.clear();
      this.values.clear();
      this.addOpen = false;
      this.loadDefs();
    });
    store.addEventListener("ws:halt", () => this.refreshValues());
    this.loadDefs();
  }

  // ---- data loading ------------------------------------------------

  async loadDefs() {
    if (!store.selectedId) {
      this.defs = [];
      this.renderList();
      this.renderForm();
      return;
    }
    try {
      const r = await fetch(`/api/instances/${store.selectedId}/regions`);
      if (!r.ok) {
        this.defs = [];
        this.listEl.innerHTML = `<div class="err">${escapeHtml(await r.text())}</div>`;
        return;
      }
      this.defs = await r.json();
      this.renderList();
      this.renderForm();
      // If anything is already expanded from before, fetch values.
      if (this.expanded.size) this.refreshValues();
    } catch (e) {
      this.listEl.innerHTML = `<div class="err">load failed: ${escapeHtml(e.message)}</div>`;
    }
  }

  async refreshValues() {
    if (!store.selectedId) return;
    if (!this.expanded.size) return;
    const visible = [...this.expanded];
    try {
      const r = await fetch(`/api/instances/${store.selectedId}/regions/values`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ visible_ids: visible }),
      });
      if (!r.ok) return;
      const arr = await r.json();
      for (const v of arr) this.values.set(v.id, v);
      this.renderList();
    } catch {}
  }

  // ---- CRUD --------------------------------------------------------

  async addRegion(body) {
    if (!store.selectedId) return;
    try {
      const r = await fetch(`/api/instances/${store.selectedId}/regions`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!r.ok) { alert(`add region failed: ${await r.text()}`); return; }
      const def = await r.json();
      this.defs.push(def);
      this.expanded.add(def.id);
      this.addOpen = false;
      this.renderForm();
      this.renderList();
      this.refreshValues();
    } catch (e) {
      alert(`add region: ${e.message}`);
    }
  }

  async deleteRegion(id) {
    if (!store.selectedId) return;
    if (!confirm("Delete this region?")) return;
    try {
      const r = await fetch(`/api/instances/${store.selectedId}/regions/${id}`, { method: "DELETE" });
      if (!r.ok) { alert(`delete failed: ${await r.text()}`); return; }
      this.defs = this.defs.filter((d) => d.id !== id);
      this.expanded.delete(id);
      this.values.delete(id);
      this.renderList();
    } catch (e) {
      alert(`delete: ${e.message}`);
    }
  }

  toggle(id) {
    if (this.expanded.has(id)) {
      this.expanded.delete(id);
      this.values.delete(id);
      this.renderList();
    } else {
      this.expanded.add(id);
      this.renderList();
      this.refreshValues();
    }
  }

  // ---- rendering ---------------------------------------------------

  exprFor(d) {
    if (d.kind === "fixed")   return `$${hex(d.addr ?? 0, 4)}`;
    if (d.kind === "symbol")  return `${d.symbol}${d.offset ? (d.offset >= 0 ? `+${d.offset}` : `${d.offset}`) : ""}`;
    if (d.kind === "pointer") return `@$${hex(d.ptr_addr ?? 0, 4)}`;
    return "?";
  }

  renderList() {
    if (!store.selectedId) {
      this.listEl.innerHTML = `<div class="empty">no instance selected</div>`;
      this.metaEl.textContent = "";
      return;
    }
    if (!this.defs.length) {
      this.listEl.innerHTML = `<div class="empty">no regions defined for this config</div>`;
      this.metaEl.textContent = "";
      return;
    }
    this.metaEl.textContent = `${this.defs.length} region${this.defs.length === 1 ? "" : "s"}`;
    this.listEl.innerHTML = this.defs.map((d) => this.renderRegion(d)).join("");
    this.listEl.querySelectorAll(".region-head").forEach((el) => {
      el.addEventListener("click", (e) => {
        if (e.target.closest(".del")) return;
        this.toggle(el.dataset.id);
      });
    });
    this.listEl.querySelectorAll(".del").forEach((el) => {
      el.addEventListener("click", (e) => {
        e.stopPropagation();
        this.deleteRegion(el.dataset.id);
      });
    });
  }

  renderRegion(d) {
    const open = this.expanded.has(d.id);
    const v = this.values.get(d.id);
    const arrow = open ? "▼" : "▶";
    const expr = this.exprFor(d);
    let body = "";
    if (open) {
      if (!v) {
        body = `<div class="body"><span class="dim">no halt event yet</span></div>`;
      } else if (v.error) {
        body = `<div class="err">${escapeHtml(v.error)}</div>`;
      } else if (v.bytes_hex) {
        body = `<div class="body">${renderHex(v.base, v.bytes_hex)}</div>`;
      } else {
        body = `<div class="err">no data</div>`;
      }
    }
    return `
      <div class="region">
        <div class="region-head" data-id="${escapeHtml(d.id)}">
          <span class="arrow">${arrow}</span>
          <span class="nm">${escapeHtml(d.name)}</span>
          <span class="kind-badge">${d.kind}</span>
          <span class="expr">${escapeHtml(expr)} · ${d.length}</span>
          <button class="del" data-id="${escapeHtml(d.id)}" title="delete">×</button>
        </div>
        ${body}
      </div>
    `;
  }

  renderForm() {
    if (!store.selectedId) { this.formWrap.innerHTML = ""; return; }
    if (!this.addOpen)     { this.formWrap.innerHTML = ""; return; }
    const k = this.addKind;
    this.formWrap.innerHTML = `
      <div class="add-form">
        <label>name</label>
        <input id="mr-f-name" placeholder="e.g. FB top" />

        <label>kind</label>
        <select id="mr-f-kind">
          <option value="fixed"   ${k === "fixed"   ? "selected" : ""}>fixed addr</option>
          <option value="symbol"  ${k === "symbol"  ? "selected" : ""}>symbol + offset</option>
          <option value="pointer" ${k === "pointer" ? "selected" : ""}>follow pointer</option>
        </select>

        ${k === "fixed" ? `
          <label>addr</label>
          <input id="mr-f-addr" placeholder="0x2000" />
        ` : ""}
        ${k === "symbol" ? `
          <label>symbol</label>
          <input id="mr-f-symbol" placeholder="tester_mode_idx" />
          <label>offset</label>
          <input id="mr-f-offset" value="0" />
        ` : ""}
        ${k === "pointer" ? `
          <label>ptr_addr</label>
          <input id="mr-f-ptr" placeholder="0x1FFE" />
        ` : ""}

        <label>length</label>
        <input id="mr-f-length" value="64" />

        <div class="span2">
          <button class="add-btn" id="mr-f-cancel">Cancel</button>
          <button class="add-btn" id="mr-f-submit">Create</button>
        </div>
      </div>
    `;
    this.formWrap.querySelector("#mr-f-kind").addEventListener("change", (e) => {
      this.addKind = e.target.value;
      this.renderForm();
    });
    this.formWrap.querySelector("#mr-f-cancel").addEventListener("click", () => {
      this.addOpen = false; this.renderForm();
    });
    this.formWrap.querySelector("#mr-f-submit").addEventListener("click", () => this.submitForm());
  }

  submitForm() {
    const name = this.formWrap.querySelector("#mr-f-name").value.trim();
    if (!name) { alert("name is required"); return; }
    const length = parseInt(this.formWrap.querySelector("#mr-f-length").value.trim(), 0);
    if (!Number.isFinite(length) || length < 1 || length > 32768) {
      alert("length must be 1..32768"); return;
    }
    const body = { name, length, kind: this.addKind };
    if (this.addKind === "fixed") {
      const addr = parseInt(this.formWrap.querySelector("#mr-f-addr").value.trim(), 0);
      if (!Number.isFinite(addr) || addr < 0 || addr > 0xFFFF) { alert("addr must be 0..0xFFFF"); return; }
      body.addr = addr;
    } else if (this.addKind === "symbol") {
      body.symbol = this.formWrap.querySelector("#mr-f-symbol").value.trim();
      if (!body.symbol) { alert("symbol is required"); return; }
      body.offset = parseInt(this.formWrap.querySelector("#mr-f-offset").value.trim(), 0) || 0;
    } else if (this.addKind === "pointer") {
      const pa = parseInt(this.formWrap.querySelector("#mr-f-ptr").value.trim(), 0);
      if (!Number.isFinite(pa) || pa < 0 || pa > 0xFFFE) { alert("ptr_addr must be 0..0xFFFE"); return; }
      body.ptr_addr = pa;
    }
    this.addRegion(body);
  }
}

// ---- helpers ------------------------------------------------------

function hex(v, w) {
  return (v >>> 0).toString(16).toUpperCase().padStart(w, "0");
}

function renderHex(base, bytesHex) {
  // Build a hex-dump matching memory-view's layout (50 / 1fr / 130 grid).
  const bytes = new Uint8Array(bytesHex.length / 2);
  for (let i = 0; i < bytes.length; i++) bytes[i] = parseInt(bytesHex.substr(i * 2, 2), 16);
  const rows = [];
  for (let off = 0; off < bytes.length; off += 16) {
    const rowAddr = (base + off) & 0xFFFF;
    const slice = bytes.slice(off, off + 16);
    const hexCells = [];
    const asciiChars = [];
    for (let i = 0; i < 16; i++) {
      if (i < slice.length) {
        const b = slice[i];
        hexCells.push(hex(b, 2));
        asciiChars.push((b >= 0x20 && b < 0x7F) ? String.fromCharCode(b) : ".");
      } else {
        hexCells.push("  "); asciiChars.push(" ");
      }
      if (i === 7) hexCells.push(" ");
    }
    rows.push(`
      <div class="row">
        <span class="a">${hex(rowAddr, 4)}</span>
        <span class="h">${hexCells.join(" ")}</span>
        <span class="r">${escapeHtml(asciiChars.join(""))}</span>
      </div>
    `);
  }
  return rows.join("");
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

customElements.define("memory-regions", MemoryRegions);
