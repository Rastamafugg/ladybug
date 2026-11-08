"""Execute one read-only, artifact-bound GDB scenario inside a supervised job."""
from __future__ import annotations

import os
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


if __name__ == "__main__":
    raise SystemExit(main())
