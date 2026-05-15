// Entry point. Imports store first so components see it initialized.
import { store } from "/static/store.js";

import "/static/components/instance-list.js";
import "/static/components/framebuffer-view.js";
import "/static/components/register-view.js";
import "/static/components/source-view.js";
import "/static/components/memory-view.js";
import "/static/components/logs-view.js";
import "/static/components/instruction-annotation.js";
import "/static/components/symbol-context.js";

document.getElementById("btn-build").addEventListener("click", () => store.build());

store.addEventListener("select", () => {
  const inst = store.instances.find((i) => i.id === store.selectedId);
  document.getElementById("status-instance").textContent =
    inst ? `${inst.name} · gdb:${inst.gdb_port} · ${inst.state}` : "— no instance —";
});

store.loadStaticDocs();
store.refreshInstances();
