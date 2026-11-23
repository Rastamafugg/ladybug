"""Execute one read-only, artifact-bound GDB scenario inside a supervised job."""
from __future__ import annotations

import os
import json
import hashlib
import re
import select
from pathlib import Path
import socket
import subprocess
import sys
import time

if __package__:
    from .core import HarnessError, digest, inside, load, open_build, save_new
else:
    from core import HarnessError, digest, inside, load, open_build, save_new


def plan(description, scenario):
    initial = load(description)
    marker = scenario["marker"]
    path, build = open_build(description, [initial["rom"], marker["image"], marker["map"]])
    if scenario.get("schema") != 1 or not scenario.get("name") or not scenario.get("purpose"):
        raise HarnessError("scenario needs schema, name and purpose")
    if not 0 < scenario.get("max_seconds", 0) <= 60:
        raise HarnessError("initial observation must be at most 60 seconds")
    image = inside(path.parent, marker["image"])
    if marker["image"] not in build["artifacts"] or marker["map"] not in build["artifacts"]:
        raise HarnessError("scenario image/map are not recorded artifacts")
    symbols = build["artifacts"][marker["map"]]["symbols"]
    address = symbols.get(marker["symbol"])
    count = marker.get("byte_count", 8)
    origin = marker["image_origin"]
    if type(count) is not int or not 1 <= count <= 32 or address is None or not 0 <= address < 65536:
        raise HarnessError("missing or invalid scenario anchor")
    offset = address - origin
    data = image.read_bytes()
    if offset < 0 or offset + count > len(data) or address + count > 65536:
        raise HarnessError("anchor is outside its bound artifact")
    pages = marker["expected_pages"]
    for key, value in pages.items():
        if key not in [str(i) for i in range(8)] or type(value) is not int or not 0 <= value <= 63:
            raise HarnessError("invalid expected physical page")
    reads = scenario.get("reads", [])
    if len(reads) > 16:
        raise HarnessError("too many read ranges")
    names = set()
    for item in reads:
        if not isinstance(item.get("name"), str) or not item["name"].isascii() or not item["name"].replace("_", "").isalnum() or item["name"] in names or item["name"] == "anchor":
            raise HarnessError("invalid or duplicate read name")
        names.add(item["name"])
    for item in [{"address": address, "length": count}] + reads:
        start, length = item["address"], item["length"]
        if type(start) is not int or type(length) is not int or not 0 <= start < 65536 or not 1 <= length <= 30720 or start + length > 65536:
            raise HarnessError("invalid read range")
        if any(str(window) not in pages for window in range(start // 8192, (start + length - 1) // 8192 + 1)):
            raise HarnessError("every observed window needs an expected physical page")
    return path, build, address, data[offset:offset + count]


def commands(address, expected, scenario, port, output):
    lines = ["set pagination off", "set confirm off", "set architecture m6809", "set remote supported-packets-packet off",
             f"target remote 127.0.0.1:{port}", f"thbreak *0x{address:04x}", "continue",
             f"if $pc != 0x{address:04x}", "quit 4", "end"]
    for window, page in sorted(scenario["marker"]["expected_pages"].items()):
        lines += [f"if ((*(unsigned char*)0x{0xFFA0 + int(window):04x}) & 63) != {page}", "quit 4", "end"]
    for offset, byte in enumerate(expected):
        lines += [f"if *(unsigned char*)0x{address + offset:04x} != {byte}", "quit 4", "end"]
    lines += ['printf "HARNESS_ANCHOR_VERIFIED\\n"',
              f"dump binary memory anchor.bin 0x{address:x} 0x{address + len(expected):x}"]
    for item in scenario.get("reads", []):
        start = item["address"]
        lines.append(f"dump binary memory {item['name']}.bin 0x{start:x} 0x{start + item['length']:x}")
    return "\n".join(lines + ["detach", "quit 0", ""])


def listener_owned(pid, port):
    """Inspect the listener, never make a probe connection to the GDB stub."""
    sockets = set()
    for fd in Path(f"/proc/{pid}/fd").iterdir():
        try:
            target = os.readlink(fd)
        except OSError:
            continue
        if target.startswith("socket:["):
            sockets.add(target[8:-1])
    for row in Path("/proc/net/tcp").read_text().splitlines()[1:]:
        columns = row.split()
        if int(columns[1].split(":")[1], 16) == port and columns[3] == "0A" and columns[9] in sockets:
            return True
    return False


def main():
    request = load(sys.argv[1])
    output = Path(request["output"])
    xroar = None
    delegated_sidecar = False
    result = {"schema": 1, "classification": "harness_failure", "game_acceptance": "not_claimed"}
    start = time.monotonic()
    try:
        scenario = load(request["scenario"])
        if scenario.get("mode") == "attract-manual-down":
            delegated_sidecar = True
            return run_menu(request, scenario, output, start)
        if scenario.get("mode") == "attract-actor-ab":
            delegated_sidecar = True
            return run_actor(request, scenario, output, start)
        path, build, address, expected = plan(request["description"], scenario)
        if build["build_result"]["classification"] != "passed":
            raise HarnessError("legacy build did not pass")
        environment = load(request["environment"])
        if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
            raise HarnessError("no visible WSL display; no XRoar launched")
        tools = environment["tools"]
        for name in ("debugger", "emulator"):
            if digest(tools[name]["path"]) != tools[name]["sha256"]:
                raise HarnessError("tool changed since doctor: " + name)
        deadline = start + scenario["max_seconds"] - 1
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        argv = [tools["emulator"]["path"], "-machine", "coco3", "-machine-cpu", "6809", "-ram", "512",
                "-cart-type", "gmc", "-cart-rom", str(inside(path.parent, build["rom"])),
                "-cart-autorun", "-tv-input", "rgb", "-joy-right", "", "-joy-left", "",
                "-gdb", "-gdb-ip", "127.0.0.1", "-gdb-port", str(port)]
        save_new(output / "scenario.json", scenario)
        save_new(output / "emulator-command.json", argv)
        with (output / "xroar.log").open("xb") as log:
            xroar = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=log, stderr=log)
            while not listener_owned(xroar.pid, port):
                if xroar.poll() is not None or time.monotonic() >= deadline:
                    raise HarnessError("owned XRoar listener did not become ready")
                time.sleep(0.02)
            script = output / "observe.gdb"
            script.write_bytes(commands(address, expected, scenario, port, output).encode("utf-8"))
            with (output / "gdb.log").open("xb") as gdb_log:
                completed = subprocess.run([tools["debugger"]["path"], "-nx", "-q", "-batch", "-x", str(script)], cwd=output,
                                           stdin=subprocess.DEVNULL, stdout=gdb_log, stderr=gdb_log,
                                           timeout=max(0.01, deadline - time.monotonic()))
            anchor = output / "anchor.bin"
            if completed.returncode or not anchor.is_file() or anchor.read_bytes() != expected:
                raise HarnessError("GDB did not prove the bound PC, physical pages and code bytes; inspect gdb.log")
            observed = {}
            for item in scenario.get("reads", []):
                data = (output / (item["name"] + ".bin")).read_bytes()
                if len(data) != item["length"]:
                    raise HarnessError("short observed range: " + item["name"])
                observed[item["name"]] = {"address": item["address"], "hex": data.hex()}
            result.update(classification="observed", scenario=scenario["name"], marker=address, reads=observed,
                          description_sha256=digest(path), scenario_sha256=digest(request["scenario"]))
    except subprocess.TimeoutExpired:
        result.update(classification="timeout", reason="observation deadline")
    except Exception as error:
        result.update(classification="harness_failure", reason=str(error))
    finally:
        if xroar is not None:
            if xroar.poll() is None:
                xroar.kill()
            try:
                xroar.wait(timeout=0.5)
            except subprocess.TimeoutExpired:
                result.update(classification="cleanup_failure", reason="XRoar did not exit after KILL")
            result["emulator_exited"] = xroar.poll() is not None
        result["elapsed_seconds"] = round(time.monotonic() - start, 4)
        if not delegated_sidecar:
            save_new(output / "observation.json", result)
    return 0 if result["classification"] == "observed" else 1


# TOOL-019: native GDB/MI transport. The legacy one-stop path above is retained.
def mi_memory(reply, length):
    chunks = re.findall(r'contents="([0-9a-fA-F]*)"', reply)
    if len(chunks) != 1:
        raise HarnessError("malformed_memory_reply")
    data = bytes.fromhex(chunks[0])
    if len(data) != length:
        raise HarnessError("short_read")
    return data


def mi_pc(stopped):
    match = re.search(r'frame=\{addr="(0x[0-9a-fA-F]+)"', stopped)
    if not match:
        raise HarnessError("missing_stopped_pc")
    return int(match.group(1), 16)


class MI:
    """One owned debugger; every reply/stop shares the observation deadline."""
    def __init__(self, executable, deadline, log, cwd, redact_memory=False):
        self.process = subprocess.Popen([executable, "-nx", "-q", "--interpreter=mi2"],
                                        cwd=cwd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=log, bufsize=0)
        self.deadline, self.log = deadline, log
        self.redact_memory = redact_memory
        self.buffer, self.token, self.stops = b"", 0, []

    def line(self):
        while b"\n" not in self.buffer:
            left = self.deadline - time.monotonic()
            if left <= 0 or not select.select([self.process.stdout], [], [], max(0, left))[0]:
                raise TimeoutError("debugger_deadline")
            data = os.read(self.process.stdout.fileno(), 8192)
            if not data:
                raise HarnessError("debugger_eof")
            self.buffer += data
        line, self.buffer = self.buffer.split(b"\n", 1)
        logged = line
        if self.redact_memory:
            logged = re.sub(rb'contents="([0-9a-fA-F]*)"',
                            lambda match: b'contents="<%d bytes>"' % (len(match.group(1)) // 2), logged)
        self.log.write(logged + b"\n"); self.log.flush()
        return line.decode("utf-8", errors="replace").strip()

    def command(self, command):
        self.token += 1
        prefix = str(self.token)
        self.process.stdin.write((prefix + command + "\n").encode("utf-8"))
        while True:
            line = self.line()
            if line.startswith("*stopped"):
                self.stops.append(line)
            if line.startswith(prefix + "^"):
                if line.startswith(prefix + "^error"):
                    raise HarnessError("debugger_command_failed: " + line)
                return line

    def resume(self):
        self.stops.clear()  # discard the initial remote-attach stop
        self.command("-exec-continue")
        while not self.stops:
            line = self.line()
            if line.startswith("*stopped"):
                self.stops.append(line)
        return mi_pc(self.stops.pop(0))

    def close(self):
        if self.process.poll() is None:
            self.process.terminate()
        try:
            self.process.wait(timeout=.3)
        except subprocess.TimeoutExpired:
            self.process.kill(); self.process.wait(timeout=.3)


def menu_plan(description, scenario):
    if digest(description) != scenario["accepted_description_sha256"]:
        raise HarnessError("accepted_description_mismatch")
    path, build, address, expected = plan(description, scenario)
    if build["artifacts"][build["rom"]]["sha256"] != scenario["accepted_rom_sha256"]:
        raise HarnessError("accepted_rom_mismatch")
    marker = scenario["input_marker"]
    path, build = open_build(path, [build["rom"], marker["image"], marker["map"]])
    number = build["artifacts"][marker["map"]]["symbols"].get(marker["symbol"])
    image = inside(path.parent, marker["image"]).read_bytes()
    offset = number - marker["image_origin"] if number is not None else -1
    if offset < 0 or offset + 8 > len(image):
        raise HarnessError("invalid_input_anchor")
    for item in scenario["startup_sources"]:
        if digest(inside(path.parent, item["path"])) != item["sha256"]:
            raise HarnessError("startup_inference_not_bound")
    publication = scenario["publication"]
    data = inside(path.parent, scenario["marker"]["image"]).read_bytes()
    at = publication["address"] - scenario["marker"]["image_origin"]
    if not 0 <= at or at + publication["length"] > len(data):
        raise HarnessError("invalid_publication_span")
    context = dict(post_pc=address, post_bytes=expected, input_pc=number,
                   input_bytes=image[offset:offset+8], publication_address=publication["address"],
                   publication_bytes=data[at:at+publication["length"]])
    return path, build, context


def menu_pixels(label, masks, colour):
    result = []
    for row in range(8):
        values = []
        for char in label["text"]:
            mask = bytes.fromhex(masks[char])[row]
            for pair in range(4):
                values.append((colour if mask & (128 >> (pair*2)) else 0)*16 +
                              (colour if mask & (64 >> (pair*2)) else 0))
        result.append(bytes(values))
    return result


class MenuCapture:
    """Acquire and interpret the bounded one-press experiment, not arbitrary traces."""
    def __init__(self, debugger, scenario, context, visual_report="pending"):
        self.debugger, self.scenario, self.context = debugger, scenario, context
        self.visual_report = visual_report
        self.samples, self.last_seq = [], None
        self.baseline, self.presses, self.changed, self.released = False, 0, False, False
        self.owners, self.terminal = {0: 0, 1: 0}, None
        self.deferred_fault = None

    def read(self, address, length):
        if any(address <= bad < address+length for bad in (0xff91, 0xff9d)):
            raise HarnessError("write_only_read_forbidden")
        return mi_memory(self.debugger.command("-data-read-memory-bytes 0x%x %d" % (address, length)), length)

    def result(self, classification, outcome, reason=None, complete=False):
        return dict(classification=classification, menu_outcome=outcome, reason=reason,
                    coverage_complete=complete, presses=self.presses,
                    assessed_owner_publications=self.owners.copy(), game_acceptance="not_claimed",
                    inference="Executive set from bound startup; display selection from bound publication code and commit/owner state; no FF91/FF9D readback.")

    def stop(self, pc):
        ctx = self.context
        if pc not in (ctx["input_pc"], ctx["post_pc"]):
            raise HarnessError("unexpected_stopped_pc")
        is_input = pc == ctx["input_pc"]
        if self.read(pc, 8) != ctx["input_bytes" if is_input else "post_bytes"]:
            raise HarnessError("marker_code_mismatch")
        pages = self.read(0xffa0, 6)
        if pages[0] & 63 != 0x38 or (is_input and pages[5] & 63 != 0x24):
            raise HarnessError("marker_page_mismatch")
        frames = int.from_bytes(self.read(2, 2), "big")
        fb = self.read(0x8f, 5)
        mode, screen = self.read(0xa5, 2)
        event = self.read(0xd0, 1)[0]
        previous, selection, dirty = self.read(0xdf, 3)
        front, back, pending = fb[:3]
        seq = int.from_bytes(fb[3:], "big")
        sample = dict(kind="input" if is_input else "publication", pc=pc, frames=frames,
                      front=front, back=back, pending=pending, sequence=seq,
                      mode=mode, screen=screen, event=event, previous=previous,
                      selection=selection, dirty=dirty, raw_pars=pages.hex())
        self.samples.append(sample)
        if mode != 2 or screen != 0:
            if self.presses:
                self.terminal = self.result("observed", "screen_transition", "attract_left")
            return
        if is_input:
            self.presses += 1
            if not self.baseline:
                self.terminal = self.result("incomplete", "invalid_fixture", "input_before_baseline")
            elif self.presses != 1:
                self.terminal = self.result("incomplete", "invalid_fixture", "repeated_input")
            # Idle publications before the press are not required samples.
            # Reseed at the input boundary; subsequent publications must be consecutive.
            self.last_seq = seq
            return
        if self.read(ctx["publication_address"], len(ctx["publication_bytes"])) != ctx["publication_bytes"]:
            raise HarnessError("publication_code_mismatch")
        if front not in (0, 1) or back != 1-front or pending:
            raise HarnessError("invalid_publication_state")
        if self.last_seq is None:
            self.last_seq = seq; sample["role"] = "seed"; return
        delta = (seq-self.last_seq) & 65535
        if delta == 0:
            sample["role"] = "no_commit"; return
        self.last_seq = seq
        if delta != 1:
            self.terminal = self.result("incomplete", "unresolved", "commit_counter_gap"); return
        if not self.presses and self.baseline:
            return
        if self.presses and previous & 2 == 0:
            self.released = True
        if self.released and self.deferred_fault:
            self.terminal = self.result("product_failure", *self.deferred_fault); return
        if self.presses and selection != 1:
            if self.changed:
                if self.released:
                    self.terminal = self.result("product_failure", "state_input_path_failure", "selection_reversion")
                else:
                    self.deferred_fault = ("state_input_path_failure", "selection_reversion")
            return  # an IRQ can precede the first selection increment
        if self.presses:
            self.changed = True
        elif selection != 0 or dirty:
            return
        if dirty & (front+1):
            sample["role"] = "repaint_pending"; return
        required = [0x30, 0x31, 0x32, 0x33] if front == 0 else [0x2c, 0x2d, 0x2e, 0x2f]
        if [v & 63 for v in pages[1:5]] != required:
            raise HarnessError("front_page_mismatch")
        sample["pixels"] = {}
        for name, label in self.scenario["labels"].items():
            colour = 10 if (name == "start_game") == (selection == 0) else 7
            wanted = menu_pixels(label, self.scenario["glyph_masks"], colour)
            rows = [self.read(label["address"]+row*160, len(wanted[row])) for row in range(8)]
            sample["pixels"][name] = [r.hex() for r in rows]
            if rows != wanted:
                if self.presses:
                    if self.released:
                        self.terminal = self.result("product_failure", "display_failure", "stale_published_highlight")
                    else:
                        self.deferred_fault = ("display_failure", "stale_published_highlight")
                    return
                raise HarnessError("baseline_pixels_mismatch")
        if not self.presses:
            self.baseline = True; sample["role"] = "baseline"
        else:
            self.owners[front] += 1
            if min(self.owners.values()) >= 2:
                self.terminal = self.finish()

    def finish(self):
        if self.terminal:
            return self.terminal
        if not self.presses:
            return self.result("incomplete", "unresolved", "input_not_observed")
        if not self.released:
            return self.result("incomplete", "invalid_fixture", "release_not_observed")
        if min(self.owners.values()) < 2:
            return self.result("incomplete", "unresolved", "owner_followup_missing")
        outcome = {"no_flicker": "not_reproduced_in_this_press", "flicker": "symptom_reproduced_cause_unresolved"}.get(self.visual_report, "awaiting_user_report")
        return self.result("observed", outcome, complete=True)


def run_menu(request, scenario, output, start):
    xroar, debugger = None, None
    capture, result = None, {"classification": "harness_failure", "game_acceptance": "not_claimed"}
    deadline = start + min(40, scenario["max_seconds"]) - 1
    try:
        path, build, ctx = menu_plan(request["description"], scenario)
        if build["build_result"]["classification"] != "passed":
            raise HarnessError("build_not_passed")
        tools = load(request["environment"])["tools"]
        for name in ("debugger", "emulator"):
            if digest(tools[name]["path"]) != tools[name]["sha256"]:
                raise HarnessError("tool_changed: " + name)
        if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
            raise HarnessError("no_visible_display")
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0)); port = sock.getsockname()[1]
        argv = [tools["emulator"]["path"], "-machine", "coco3", "-machine-cpu", "6809", "-ram", "512", "-cart-type", "gmc", "-cart-rom", str(inside(path.parent, build["rom"])), "-cart-autorun", "-tv-input", "rgb", "-joy-right", "", "-joy-left", "", "-gdb", "-gdb-ip", "127.0.0.1", "-gdb-port", str(port)]
        save_new(output/"emulator-command.json", argv)
        with (output/"xroar.log").open("xb") as log, (output/"gdb.log").open("xb") as gdb_log:
            xroar = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=log, stderr=log)
            while not listener_owned(xroar.pid, port):
                if xroar.poll() is not None or time.monotonic() >= deadline:
                    raise HarnessError("owned_listener_missing")
                time.sleep(.02)
            debugger = MI(tools["debugger"]["path"], deadline, gdb_log, output)
            debugger.command("-gdb-set architecture m6809")
            debugger.command('-interpreter-exec console "set remote supported-packets-packet off"')
            debugger.command("-target-select remote 127.0.0.1:%d" % port)
            down = debugger.command("-break-insert -h *0x%x" % ctx["input_pc"])
            post = debugger.command("-break-insert -h *0x%x" % ctx["post_pc"])
            ids = [re.search(r'number="(\d+)"', value).group(1) for value in (down, post)]
            capture = MenuCapture(debugger, scenario, ctx)
            publication_disabled = False
            while time.monotonic() < deadline:
                pc = debugger.resume()
                capture.stop(pc)
                if capture.terminal:
                    break
                if capture.baseline and not capture.presses and not publication_disabled:
                    debugger.command("-break-disable " + ids[1]); publication_disabled = True
                    save_new(output/"input-ready.json", {"message": "Attract baseline ready; press and release Down once.", "time_seconds":time.monotonic()-start})
                if capture.presses and publication_disabled:
                    debugger.command("-break-enable " + ids[1]); publication_disabled = False
            result = capture.finish()
    except TimeoutError:
        result = capture.finish() if capture else dict(classification="incomplete", reason="baseline_not_observed")
    except Exception as error:
        result = dict(classification="harness_failure", reason=str(error), game_acceptance="not_claimed")
    finally:
        for child in (debugger,):
            if child:
                try: child.close()
                except Exception: result.update(classification="cleanup_failure", debugger_exited=False)
        if xroar:
            if xroar.poll() is None: xroar.kill()
            try: xroar.wait(timeout=.3)
            except subprocess.TimeoutExpired: result.update(classification="cleanup_failure")
            result["emulator_exited"] = xroar.poll() is not None
        if capture: result["samples"] = capture.samples
        result.update(elapsed_seconds=round(time.monotonic()-start,4), source_description=str(request["description"]), scenario_sha256=digest(request["scenario"]))
        save_new(output/"observation.json", result)
    return 0 if result["classification"] == "observed" else 1


def actor_plan(description, scenario):
    if digest(description) != scenario["accepted_description_sha256"]:
        raise HarnessError("accepted_description_mismatch")
    if (scenario.get("max_seconds") != 40 or scenario.get("max_callbacks") != 512 or
            scenario.get("max_publication_samples") != 3 or scenario.get("actor_count") != 8):
        raise HarnessError("actor_probe_bounds_or_coverage_changed")
    path, build, post_pc, post_bytes = plan(description, scenario)
    if build.get("profile") != "keyboard-adaptive":
        raise HarnessError("actor_probe_requires_keyboard_adaptive")
    if build["artifacts"][build["rom"]]["sha256"] != scenario["accepted_rom_sha256"]:
        raise HarnessError("accepted_rom_mismatch")
    required = [
        scenario["phase_marker"]["image"], scenario["phase_marker"]["map"],
        scenario["actor_manifest"],
    ]
    path, build = open_build(path, [build["rom"], scenario["marker"]["image"],
                                    scenario["marker"]["map"]] + required)
    manifest_name = scenario["actor_manifest"]
    manifest_path = inside(path.parent, manifest_name)
    if digest(manifest_path) != scenario["accepted_manifest_sha256"]:
        raise HarnessError("accepted_actor_manifest_mismatch")
    manifest = load(manifest_path)
    reference_name = scenario["arcade_reference"]
    reference_path = inside(Path(__file__).resolve().parents[2], reference_name)
    reference_sha = scenario["accepted_arcade_reference_sha256"]
    if (build.get("source_inputs", {}).get(reference_name) != reference_sha or
            digest(reference_path) != reference_sha):
        raise HarnessError("accepted_arcade_reference_mismatch")
    reference = load(reference_path)
    reference_sequences = [item.get("source_sprite_codes_by_phase")
                           for item in reference.get("actors", {}).values()]
    if (not reference_sequences or
            any(not isinstance(sequence, list) or len(sequence) != 4 or
                any(type(code) is not int or not 0 <= code <= 255 for code in sequence)
                for sequence in reference_sequences) or
            any(sequence[3] != sequence[1] for sequence in reference_sequences)):
        raise HarnessError("arcade_reference_phase_alias_mismatch")
    surfaces = manifest.get("attract_actor_surfaces", {})
    actors = surfaces.get("actors", [])
    phase_hashes = surfaces.get("phase_crop_sha256", [])
    if len(actors) != scenario.get("actor_count") or len(actors) != 8:
        raise HarnessError("actor_manifest_must_bind_all_eight_actors")
    if (surfaces.get("actor_bytes") != 128 or len(phase_hashes) != 3 or
            any(len(row) != len(actors) for row in phase_hashes) or
            any(not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value)
                for row in phase_hashes for value in row)):
        raise HarnessError("actor_phase_oracle_shape_mismatch")
    cells, destinations, source_sequences = set(), set(), set()
    height, stride, row_bytes = scenario["crop_height"], scenario["framebuffer_stride"], scenario["crop_row_bytes"]
    if (height, stride, row_bytes) != (16, 160, 8):
        raise HarnessError("unsupported_actor_crop_geometry")
    for actor in actors:
        address = actor.get("destination")
        cell = actor.get("cell")
        codes = actor.get("source_codes")
        if (not isinstance(cell, list) or len(cell) != 2 or
                any(type(value) is not int or value < 0 for value in cell) or
                not isinstance(codes, list) or len(codes) != 3 or
                any(type(value) is not int or not 0 <= value <= 255 for value in codes)):
            raise HarnessError("invalid_actor_identity")
        if type(address) is not int or address < 0x2000 or address + (height - 1) * stride + row_bytes > 0x9800:
            raise HarnessError("actor_crop_outside_visible_framebuffer")
        if tuple(cell) in cells or address in destinations or tuple(codes) in source_sequences:
            raise HarnessError("actor_manifest_records_are_not_distinct")
        cells.add(tuple(cell)); destinations.add(address); source_sequences.add(tuple(codes))
    reference_matches = [actor["cell"] for actor in actors
                         if tuple(actor["source_codes"]) in {tuple(row[:3]) for row in reference_sequences}]
    if not reference_matches:
        raise HarnessError("arcade_reference_has_no_bound_actor_sequences")
    pages = scenario["front_owner_pages"]
    if pages != {"0": [0x30, 0x31, 0x32, 0x33], "1": [0x2C, 0x2D, 0x2E, 0x2F]}:
        raise HarnessError("unexpected_front_owner_page_map")
    phase_marker = scenario["phase_marker"]
    phase_symbols = build["artifacts"][phase_marker["map"]].get("symbols", {})
    phase_pc = phase_symbols.get(phase_marker["symbol"])
    helper = inside(path.parent, phase_marker["image"]).read_bytes()
    phase_offset = phase_pc - phase_marker["image_origin"] if phase_pc is not None else -1
    phase_count = phase_marker["byte_count"]
    if (phase_offset < 0 or phase_count <= 0 or phase_offset + phase_count > len(helper) or
            phase_pc + phase_count > 65536):
        raise HarnessError("invalid_actor_phase_marker")
    return path, build, {
        "post_pc": post_pc,
        "post_bytes": post_bytes,
        "post_marker": scenario["marker"],
        "phase_pc": phase_pc,
        "phase_bytes": helper[phase_offset:phase_offset + phase_count],
        "phase_marker": phase_marker,
        "actors": actors,
        "phase_hashes": phase_hashes,
        "arcade_reference_matches": reference_matches,
        "expected_pages": scenario["front_owner_pages"],
        "crop_height": height,
        "framebuffer_stride": stride,
        "crop_row_bytes": row_bytes,
        "max_callbacks": scenario["max_callbacks"],
        "max_publication_samples": scenario["max_publication_samples"],
    }


def actor_phase_from_timer(timer):
    if timer < 6:
        return 0
    return ((timer - 6) >> 3) & 3


def actor_frame_from_phase(phase):
    return (0, 1, 2, 1)[phase] if phase in range(4) else -1


class ActorCapture:
    """One no-input phase-change observation; pixels are read only from FRONT."""
    def __init__(self, debugger, scenario, context):
        self.debugger, self.scenario, self.context = debugger, scenario, context
        self.samples, self.last_commit = [], None
        self.phase_change = None
        self.owners = set()
        self.terminal = None
        self.callbacks = 0
        self.finished_result = None

    def read(self, address, length):
        if any(address <= bad < address + length for bad in (0xFF91, 0xFF9D)):
            raise HarnessError("write_only_read_forbidden")
        reply = self.debugger.command("-data-read-memory-bytes 0x%x %d" % (address, length))
        return mi_memory(reply, length)

    def state(self):
        timer = int.from_bytes(self.read(0x00B0, 2), "big")
        fb = self.read(0x008F, 5)
        mode, screen = self.read(0x00A5, 2)
        return {
            "timer": timer,
            "timer_phase": actor_phase_from_timer(timer),
            "actor_phase": self.read(0x00D3, 1)[0],
            "hold_state": self.read(0x00D4, 1)[0],
            "mode": mode,
            "screen": screen,
            "front": fb[0],
            "back": fb[1],
            "pending": fb[2],
            "commit": int.from_bytes(fb[3:5], "big"),
        }

    def marker_pages(self, pc, marker, expected):
        if pc != expected["address"]:
            raise HarnessError("unexpected_marker_pc")
        actual = self.read(pc, len(expected["bytes"]))
        if actual != expected["bytes"]:
            raise HarnessError("live_marker_code_mismatch")
        pages = self.read(0xFFA0, 5)
        if (pages[0] & 63) != marker["expected_pages"]["0"]:
            raise HarnessError("marker_page_mismatch")
        return pages, actual

    def actor_crops(self):
        crops = []
        height = self.context["crop_height"]
        stride = self.context["framebuffer_stride"]
        row_bytes = self.context["crop_row_bytes"]
        for index, actor in enumerate(self.context["actors"]):
            pixels = b"".join(self.read(actor["destination"] + row * stride, row_bytes)
                               for row in range(height))
            digest_value = hashlib.sha256(pixels).hexdigest()
            matches = [phase for phase, row in enumerate(self.context["phase_hashes"])
                       if row[index] == digest_value]
            crops.append({
                "cell": actor["cell"],
                "source_codes": actor["source_codes"],
                "sha256": digest_value,
                "matching_phases": matches,
                "_pixels_hex": pixels.hex(),
            })
        return crops

    def stop(self, pc):
        self.callbacks += 1
        if self.callbacks > self.context["max_callbacks"]:
            self.terminal = {"classification": "incomplete", "reason": "callback_cap", "coverage_complete": False}
            return
        if pc == self.context["phase_pc"]:
            pages, marker_bytes = self.marker_pages(pc, self.context["phase_marker"], {
                "address": self.context["phase_pc"], "bytes": self.context["phase_bytes"]})
            state = self.state()
            if (state["mode"] == 2 and state["screen"] == 0 and
                    state["hold_state"] == 0 and state["pending"] == 0 and
                    state["actor_phase"] == 0 and state["timer_phase"] == 1):
                self.phase_change = {"timer": state["timer"], "from_phase": 0,
                                     "to_phase": 1, "front": state["front"],
                                     "back": state["back"], "par0": pages[0] & 63,
                                     "marker_bytes_hex": marker_bytes.hex()}
            return
        if pc != self.context["post_pc"]:
            raise HarnessError("unexpected_stopped_pc")
        pages, marker_bytes = self.marker_pages(pc, self.context["post_marker"], {
            "address": self.context["post_pc"], "bytes": self.context["post_bytes"]})
        state = self.state()
        if self.last_commit is None:
            self.last_commit = state["commit"]
            return
        delta = (state["commit"] - self.last_commit) & 65535
        if delta == 0:
            return
        self.last_commit = state["commit"]
        if delta != 1:
            self.terminal = {"classification": "incomplete", "reason": "commit_sequence_gap", "coverage_complete": False}
            return
        if state["mode"] != 2 or state["screen"] != 0 or state["hold_state"] != 0:
            if self.phase_change:
                self.terminal = {"classification": "incomplete", "reason": "left_natural_attract", "coverage_complete": False}
            return
        if state["pending"] != 0 or state["front"] not in (0, 1) or state["back"] != 1 - state["front"]:
            raise HarnessError("invalid_publication_state")
        wanted = self.context["expected_pages"].get(str(state["front"]))
        if wanted is None or [page & 63 for page in pages[1:5]] != wanted:
            raise HarnessError("front_page_mismatch")
        if not self.phase_change:
            return
        crops = self.actor_crops()
        sample = dict(timer=state["timer"], timer_phase=state["timer_phase"],
                      actor_phase=state["actor_phase"], front=state["front"], back=state["back"],
                      pending=state["pending"], commit=state["commit"],
                      marker_bytes_hex=marker_bytes.hex(), raw_pars=pages.hex(), actors=crops)
        sample["timer_phase_match"] = state["timer_phase"] == state["actor_phase"]
        self.samples.append(sample)
        self.owners.add(state["front"])
        if self.owners == {0, 1}:
            self.terminal = self.finish()
        elif len(self.samples) >= self.context["max_publication_samples"]:
            self.terminal = {"classification": "incomplete", "reason": "second_owner_missing", "coverage_complete": False}

    def finish(self):
        if self.finished_result is not None:
            return self.finished_result
        if self.terminal and self.terminal.get("classification") != "observed":
            self.finished_result = self.terminal
            return self.finished_result
        if not self.phase_change:
            self.finished_result = {"classification": "incomplete", "reason": "phase_transition_missing", "coverage_complete": False}
            return self.finished_result
        if self.owners != {0, 1}:
            self.finished_result = {"classification": "incomplete", "reason": "second_owner_missing", "coverage_complete": False}
            return self.finished_result
        timer_mismatch = any(not sample["timer_phase_match"] for sample in self.samples)
        stale, unknown, anomalous_crops = [], [], []
        for sample in self.samples:
            expected = actor_frame_from_phase(sample["actor_phase"])
            for index, crop in enumerate(sample["actors"]):
                if expected not in crop["matching_phases"]:
                    anomalous_crops.append((sample, index, crop))
                    if crop["matching_phases"]:
                        stale.append({"front": sample["front"], "actor_index": index,
                                      "observed_phases": crop["matching_phases"], "expected_phase": expected})
                    else:
                        unknown.append({"front": sample["front"], "actor_index": index,
                                        "sha256": crop["sha256"], "expected_phase": expected})
        diagnosis = ("timer_phase_discontinuity" if timer_mismatch else
                     "stale_actor_pixels" if stale else
                     "unrecognized_actor_pixels" if unknown else
                     "no_stale_pixels_observed")
        retain = []
        if anomalous_crops:
            sample, index, crop = anomalous_crops[0]
            retain.append(crop)
            counterpart = next((candidate["actors"][index] for candidate in self.samples
                                if candidate["front"] != sample["front"]), None)
            if counterpart is not None:
                retain.append(counterpart)
        if not retain:
            retain = [next(crop for sample in self.samples if sample["front"] == owner
                           for crop in sample["actors"] if crop["cell"] == self.context["actors"][0]["cell"])
                      for owner in (0, 1)]
        retained_ids = {id(crop) for crop in retain}
        for sample in self.samples:
            for crop in sample["actors"]:
                pixels = crop.pop("_pixels_hex")
                if id(crop) in retained_ids:
                    crop["pixels_hex"] = pixels
        self.finished_result = {"classification": "observed", "diagnosis": diagnosis,
                                "coverage_complete": True, "game_acceptance": "not_claimed",
                                "stale_actors": stale, "unrecognized_actors": unknown,
                                "phase_change": self.phase_change,
                                "retained_actor_crops": len(retain)}
        return self.finished_result


def actor_final_result(capture, deadline_expired):
    if capture.terminal:
        return capture.finish()
    if deadline_expired:
        return {"classification": "timeout", "reason": "observer_deadline", "coverage_complete": False}
    return capture.finish()


def run_actor(request, scenario, output, start):
    xroar, debugger = None, None
    capture = None
    result = {"classification": "harness_failure", "game_acceptance": "not_claimed"}
    deadline = start + min(40, scenario["max_seconds"]) - 1
    try:
        path, build, context = actor_plan(request["description"], scenario)
        if build["build_result"]["classification"] != "passed":
            raise HarnessError("build_not_passed")
        if digest(request["environment"]) != scenario["accepted_environment_sha256"]:
            raise HarnessError("accepted_environment_mismatch")
        tools = load(request["environment"])["tools"]
        for name in ("debugger", "emulator"):
            if digest(tools[name]["path"]) != tools[name]["sha256"]:
                raise HarnessError("tool_changed: " + name)
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0)); port = sock.getsockname()[1]
        argv = [tools["emulator"]["path"], "-ui", "null", "-ao", "null", "-machine", "coco3",
                "-machine-cpu", "6809", "-ram", "512", "-ram-init", "random", "-cart-type", "gmc",
                "-cart-rom", str(inside(path.parent, build["rom"])), "-cart-autorun", "-tv-input", "rgb",
                "-joy-right", "", "-joy-left", "", "-gdb", "-gdb-ip", "127.0.0.1", "-gdb-port", str(port)]
        save_new(output / "scenario.json", scenario)
        save_new(output / "emulator-command.json", argv)
        with (output / "xroar.log").open("xb") as log, (output / "gdb.log").open("xb") as gdb_log:
            xroar = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=log, stderr=log)
            while not listener_owned(xroar.pid, port):
                if xroar.poll() is not None or time.monotonic() >= deadline:
                    raise HarnessError("owned_listener_missing")
                time.sleep(.02)
            debugger = MI(tools["debugger"]["path"], deadline, gdb_log, output, redact_memory=True)
            debugger.command("-gdb-set architecture m6809")
            debugger.command('-interpreter-exec console "set remote supported-packets-packet off"')
            debugger.command("-target-select remote 127.0.0.1:%d" % port)
            phase_bp = debugger.command("-break-insert -h *0x%x" % context["phase_pc"])
            post_bp = debugger.command("-break-insert -h *0x%x" % context["post_pc"])
            for response in (phase_bp, post_bp):
                if not re.search(r'number="\d+"', response):
                    raise HarnessError("breakpoint_install_failed")
            capture = ActorCapture(debugger, scenario, context)
            while time.monotonic() < deadline and not capture.terminal:
                if capture.callbacks >= context["max_callbacks"]:
                    capture.terminal = {"classification": "incomplete", "reason": "callback_cap", "coverage_complete": False}
                    break
                capture.stop(debugger.resume())
            result = actor_final_result(capture, time.monotonic() >= deadline)
    except TimeoutError:
        result = actor_final_result(capture, True) if capture else {"classification": "timeout", "reason": "observer_deadline", "coverage_complete": False}
    except Exception as error:
        result = {"classification": "harness_failure", "reason": str(error), "coverage_complete": False}
    finally:
        if debugger:
            try:
                debugger.close()
            except Exception:
                result.update(classification="cleanup_failure", debugger_exited=False)
        if xroar:
            if xroar.poll() is None:
                xroar.kill()
            try:
                xroar.wait(timeout=.3)
            except subprocess.TimeoutExpired:
                result.update(classification="cleanup_failure")
            result["emulator_exited"] = xroar.poll() is not None
        if capture:
            result["samples"] = capture.samples
            result["phase_change"] = capture.phase_change
            result["callbacks"] = capture.callbacks
        result.update(elapsed_seconds=round(time.monotonic() - start, 4),
                      source_description=str(request["description"]),
                      scenario_sha256=digest(request["scenario"]))
        save_new(output / "observation.json", result)
    return 0 if result.get("classification") == "observed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
