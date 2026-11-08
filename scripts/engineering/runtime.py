"""Execute one read-only, artifact-bound GDB scenario inside a supervised job."""
from __future__ import annotations

import os
import json
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
    result = {"schema": 1, "classification": "harness_failure", "game_acceptance": "not_claimed"}
    start = time.monotonic()
    try:
        scenario = load(request["scenario"])
        if scenario.get("mode") == "attract-manual-down":
            return run_menu(request, scenario, output, start)
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
    def __init__(self, executable, deadline, log, cwd):
        self.process = subprocess.Popen([executable, "-nx", "-q", "--interpreter=mi2"],
                                        cwd=cwd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=log, bufsize=0)
        self.deadline, self.log = deadline, log
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
        self.log.write(line + b"\n"); self.log.flush()
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
        if pages[0] & 63 != 0x38 or (is_input and pages[5] & 63 != 0x23):
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


if __name__ == "__main__":
    raise SystemExit(main())
