---
name: Patch XRoar 1.10 to make `-load <snap>` work with `-gdb`
description: Feasibility report — root cause is a missing SO_REUSEADDR on the gdb listener, exposed by snapshot-load's machine-free-then-reinit. One-line surgical fix; ~1-2 hour upstream MR.
type: backlog
tags: [tooling, xroar, patch, snapshots]
updated: 2026-05-15
---

# Patch XRoar 1.10 to fix `-load <snap> + -gdb`

## Symptom

Launching XRoar with both `-load <snapshot>` and `-gdb` results in no GDB listener — `target remote :65520` from gdb fails with connection refused. The wiki previously characterised this as "silently drops the gdb listener" ([tooling/xroar.md](../tooling/xroar.md), [backlog/cart-ram-corruption.md](cart-ram-corruption.md)). Reproduction this session shows the failure is **not silent** — XRoar logs:

```
[gdb] WARNING: bind 127.0.0.1:65532 failed
```

The bind is attempted and rejected by the kernel. The wiki entry will be corrected.

## Root cause

The snapshot-load path destroys and rebuilds the machine, which means `gdb_interface_new` runs twice — once during the initial `xroar_hard_reset()`, once during the deserialised machine's `coco3_init()`. The first listener is closed correctly, but **the listening socket is never given `SO_REUSEADDR`**, so the kernel holds the port in `TIME_WAIT` for the conventional 60-second cooldown and the second `bind()` fails with `EADDRINUSE`.

### Call trace

1. [src/xroar.c:1357](../../docs/reference/xroar/src/xroar.c) — `xroar_init_finish()` calls `xroar_hard_reset()`.
2. `xroar_hard_reset` → machine part construction → `coco3_init` ([src/coco3.c:672-677](../../docs/reference/xroar/src/coco3.c)).
3. [src/coco3.c:675](../../docs/reference/xroar/src/coco3.c): `gdb_interface_new(...)` → [src/gdb.c:185-260](../../docs/reference/xroar/src/gdb.c) — creates socket, calls `bind()`, calls `listen()`, spawns `handle_tcp_sock` thread. **First listener bound on `127.0.0.1:65520`.**
4. [src/xroar.c:1361-1364](../../docs/reference/xroar/src/xroar.c) — `if (private_cfg.file.snapshot) read_snapshot(...)`.
5. [src/snapshot.c:236-241](../../docs/reference/xroar/src/snapshot.c) — `part_free((struct part *)xroar.machine)` frees the running machine. This dispatches `coco3_free` ([src/coco3.c:694-698](../../docs/reference/xroar/src/coco3.c)), which calls `gdb_interface_free(...)`.
6. [src/gdb.c:262-274](../../docs/reference/xroar/src/gdb.c) — `gdb_interface_free` cancels the socket thread and closes `listenfd`. The kernel marks the TCP endpoint `TIME_WAIT`.
7. [src/snapshot.c:240-241](../../docs/reference/xroar/src/snapshot.c) — `xroar.machine = m; xroar_connect_machine();` — the deserialised machine is wired up. **`coco3_init` runs again** on the new machine, calling `gdb_interface_new` a second time.
8. [src/gdb.c:235-238](../../docs/reference/xroar/src/gdb.c) — `bind()` fails because the kernel still holds the port in `TIME_WAIT`. `LOG_MOD_WARN("gdb", "bind %s:%s failed\n", ...)` fires, the function jumps to `failed:`, returns `NULL`. The new machine has `mcc3->gdb_interface = NULL` — no listener, no debug session possible.

The XRoar startup banner happens to print these warnings interleaved with Gtk-CRITICAL UI noise, which is presumably why the message has gone unnoticed in casual testing.

## Why this happens specifically with `-load`

Without `-load`, `gdb_interface_new` is called exactly once. The port is bound once and stays bound for the life of the process. No `TIME_WAIT` window, no second bind.

With `-load`, the flow above runs `gdb_interface_new → gdb_interface_free → gdb_interface_new` within a few milliseconds. Without `SO_REUSEADDR`, the second bind is doomed to fail.

This is independent of the wiki's previously noted "`-trap` succeeds at writing the snapshot, but XRoar segfaults right after" ([tooling/xroar.md](../tooling/xroar.md)) — that bug is in the snapshot **write** path; this one is in the snapshot **read** path.

## Proposed fix

**One-line, surgical, standard practice.** Add `SO_REUSEADDR` to the listening socket between `socket()` and `bind()` in [src/gdb.c:228-235](../../docs/reference/xroar/src/gdb.c):

```c
    // Create a socket...
    gip->listenfd = socket(gip->info->ai_family, gip->info->ai_socktype, gip->info->ai_protocol);
    if (gip->listenfd < 0) {
        LOG_MOD_WARN("gdb", "socket not created\n");
        goto failed;
    }

+   // Allow rebinding when a previous listener is still in TIME_WAIT
+   // (happens under -load when the snapshot path frees and re-creates
+   // the machine in quick succession).
+   int yes = 1;
+   (void)setsockopt(gip->listenfd, SOL_SOCKET, SO_REUSEADDR, &yes, sizeof(yes));
+
    // bind
    if (bind(gip->listenfd, gip->info->ai_addr, gip->info->ai_addrlen) < 0) {
```

That's it. `SO_REUSEADDR` on a listening TCP socket is universally safe (it does *not* allow two processes to bind the same port; it only relaxes the `TIME_WAIT` restriction). Linux/macOS/BSD/Windows all support it identically for this use case.

## Why not the "cleaner" fix?

A more architecturally pleasing fix would be to **defer** `gdb_interface_new` from `coco3_init` until after the snapshot load completes — so the listener is only created once, against the final machine. That would require:

- Moving the `gdb_interface_new` call out of `coco3_init` (and the matching free out of `coco3_free`), into a higher layer (probably `xroar_init_finish` after the `read_snapshot` branch).
- The same refactor in [src/dragon/dragon.c:600](../../docs/reference/xroar/src/dragon/dragon.c) and [src/mc10.c:519](../../docs/reference/xroar/src/mc10.c) (and any other machine).
- Care around the listener-thread's references to the machine part — currently those are wired during init.

Touching ~6 files, plumbing the gdb interface as a process-lifetime singleton rather than a machine-lifetime one. ~1 day of work, real risk of regressing the non-`-load` path, and the resulting code is meaningfully more complex.

**The `SO_REUSEADDR` fix is the right call.** It addresses the actual failure mode (a kernel-level resource transient), is one line, has no plausible regression surface, and reads as obviously-correct to anyone familiar with TCP listeners. The architectural smell of "two listeners during snapshot load" is real but does not need to be untangled to ship the fix.

## Upstream-ability

**High.** The fix is:

- Minimal (a single `setsockopt` call).
- Universally idiomatic for TCP listeners.
- Demonstrably resolves an observable, reproducible bug.
- Not platform-specific.
- Doesn't change any externally observable behaviour except "the listener actually binds."

A pull request to https://www.6809.org.uk/xroar/ (or wherever Ciaran Anscomb takes contributions — the project doesn't appear to host on GitHub) would be a strong candidate. Even if upstream is slow to merge, the patch is small enough to carry as a local diff against tagged releases.

## Cost estimate

| Phase | Effort |
|-|-|
| Apply patch + local build of XRoar | ~30-60 min (assuming standard autotools toolchain; haven't verified XRoar's build dependencies) |
| Verify fix against the failing repro (this session's exact command) | ~15 min |
| Verify no regression of the non-`-load` path | ~15 min |
| Verify the post-load gdb session actually works end-to-end against the existing `web/` backend | ~30 min |
| Optional: produce upstream patch + cover letter | ~30 min |
| **Total** | **~2-3 hours wall-clock** |

## Decision the user should make

Three meaningful options, in increasing commitment order:

1. **Don't patch.** Live with snapshot-load being a non-debug path. Use snapshots for fast iteration only via the existing `-trap` → save → re-launch fresh flow recorded in [tooling/xroar.md](../tooling/xroar.md). Snapshot-resume in `web/` becomes "view-only" instance kind (no gdb attach).
2. **Apply locally, defer upstream.** Maintain a small local patch over the system XRoar. Unblocks the snapshot-resume-with-debug feature in `web/` immediately; doesn't help anyone else.
3. **Patch + upstream.** Same local effect as (2) plus the upstream MR. Slightly more work for community benefit.

The fix is small enough that (3) is roughly the same effort as (2) once you've verified the fix locally.

## Caveats

- **`-load` and `-trap` may interact in other ways.** The patch only addresses the bind failure. If, after the fix, `-load` snapshots still don't reach the cart-autorun handshake or trip other XRoar quirks (the `-trap` segfault is separate but related), additional work may be needed. The fix here is necessary but may not be sufficient for every snapshot-resume scenario.
- **Snapshot ROM-mismatch.** A snapshot taken against one build of `ladybug.rom` won't restore meaningfully against another. That's a `web/` concern (hash-the-ROM-into-manifest), not an XRoar concern.
- **Build environment.** We haven't tested an XRoar build locally. The standard autotools dance (`autoreconf -fi && ./configure && make`) is implied by the existing `~/coco-tools/xroar` install path but should be confirmed before promising the cost above.

## Sources

- [src/gdb.c:185-274](../../docs/reference/xroar/src/gdb.c) — gdb listener lifecycle
- [src/coco3.c:672-698](../../docs/reference/xroar/src/coco3.c) — machine-side hooks
- [src/snapshot.c:99-244](../../docs/reference/xroar/src/snapshot.c) — read_snapshot and machine swap
- [src/xroar.c:1350-1418](../../docs/reference/xroar/src/xroar.c) — init_finish ordering
- [tooling/xroar.md](../tooling/xroar.md) — prior wiki note (to be corrected — failure is logged, not silent)
- [backlog/retro-dev-web-app.md](retro-dev-web-app.md) — downstream user of this fix
- [backlog/mcp-xroar-server.md](mcp-xroar-server.md) — related larger XRoar-patching effort
