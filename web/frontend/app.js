// Entry point. Imports store first so components see it initialized.
import { store } from "/static/store.js";

import "/static/components/instance-list.js";
import "/static/components/framebuffer-view.js";
import "/static/components/screen-mode-view.js";
import "/static/components/palette-view.js";
import "/static/components/register-view.js";
import "/static/components/source-view.js";
import "/static/components/memory-view.js";
import "/static/components/memory-regions.js";
import "/static/components/logs-view.js";
import "/static/components/instruction-annotation.js";
import "/static/components/symbol-context.js";

document.getElementById("btn-build").addEventListener("click", () => store.build());

// Live status line: re-render on selection AND on every ws:state event so
// the running/halted indicator tracks the emulator in real time.
function renderInstanceStatus() {
  const el = document.getElementById("status-instance");
  const inst = store.instances.find((i) => i.id === store.selectedId);
  if (!inst) { el.textContent = "— no instance —"; return; }
  const state = store.runState ?? inst.state;
  const badge = state === "running" ? "▶ running"
              : state === "halted" ? "⏸ halted"
              : state;
  const safeName = String(inst.name).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
  el.innerHTML = `${safeName} · mon:${inst.monitor_port} · ` +
    `<span style="color:${state === "running" ? "var(--ok)" : state === "halted" ? "var(--warn)" : "var(--fg-dim)"}; font-weight:bold;">${badge}</span>`;
}
store.addEventListener("select", renderInstanceStatus);
store.addEventListener("instances", renderInstanceStatus);
store.addEventListener("ws:state", renderInstanceStatus);

store.loadStaticDocs();
store.refreshInstances();
