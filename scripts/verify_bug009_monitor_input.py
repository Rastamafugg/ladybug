#!/usr/bin/env python3
"""Exercise BUG-009 input and framebuffer-owner scenarios through XRoar monitor."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import signal
import socket
import subprocess
import time
from pathlib import Path


PFT = 0x1900
LOAD_DONE = 0x1A4F
PUBLISH = 0x0DD4
POST_SCAN = 0x1903
PRES_EVENT = 0x00A9
PRES_SCREEN = 0x00A6
PRES_PREV = 0x00B2
FB_FRONT = 0x008F
FB_BACK = 0x0090
FB_PENDING = 0x0091
FB_START = 0x2000
FB_END = 0x9800
ATTRACT_FB_SHA256 = "54c4aa78520e1726c41912a2ed4913d9be06c3b64b4ad279f52f201ad6f7c4f6"


class MonitorError(RuntimeError):
    pass


class MonitorClient:
    def __init__(self, sock: socket.socket):
        self.sock = sock
        self.file = sock.makefile("rwb")
        self.next_id = 1
        self.events: list[dict] = []

    def _read(self, deadline: float) -> dict:
        remaining = max(0.1, deadline - time.monotonic())
        self.sock.settimeout(remaining)
        raw = self.file.readline()
        if not raw:
            raise MonitorError("monitor connection closed")
        return json.loads(raw)

    def call(self, method: str, params: dict | None = None, timeout: float = 20.0) -> dict:
        ident = self.next_id
        self.next_id += 1
        request = {"jsonrpc": "2.0", "id": ident, "method": method}
        if params is not None:
            request["params"] = params
        self.file.write((json.dumps(request) + "\n").encode())
        self.file.flush()
        deadline = time.monotonic() + timeout
        while True:
            message = self._read(deadline)
            if message.get("id") == ident:
                if "error" in message:
                    raise MonitorError(str(message["error"]))
                return message.get("result", {})
            self.events.append(message)

    def run_to_breakpoint(self, timeout: float = 20.0) -> dict:
        ident = self.next_id
        self.next_id += 1
        self.file.write((json.dumps({"jsonrpc": "2.0", "id": ident, "method": "run"}) + "\n").encode())
        self.file.flush()
        deadline = time.monotonic() + timeout
        run_ack = False
        while True:
            message = self._read(deadline)
            if message.get("id") == ident:
                if "error" in message:
                    raise MonitorError(str(message["error"]))
                run_ack = True
                continue
            if message.get("method") == "bp":
                if not run_ack:
                    raise MonitorError("breakpoint notification preceded run acknowledgement")
                return message.get("params", {})
            self.events.append(message)

    def close(self) -> None:
        try:
            self.file.close()
        finally:
            self.sock.close()


def launch(binary: Path, rom: Path, port: int) -> tuple[subprocess.Popen[object], MonitorClient]:
    process = subprocess.Popen(
        [
            str(binary), "-ui", "null", "-ao", "null", "-machine", "coco3", "-ram", "512",
            "-cart-type", "gmc", "-cart-rom", str(rom), "-cart-autorun",
            "-monitor", f"127.0.0.1:{port}", "-monitor-halt-on-start",
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        start_new_session=(os.name != "nt"),
    )
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        try:
            sock = socket.create_connection(("127.0.0.1", port), timeout=0.5)
            client = MonitorClient(sock)
            hello = json.loads(client.file.readline())
            if hello.get("method") != "hello":
                raise MonitorError(f"unexpected hello: {hello}")
            client.call("events.subscribe", {"kinds": ["bp"]})
            return process, client
        except (OSError, MonitorError):
            time.sleep(0.05)
    stop(process)
    raise MonitorError("monitor listener did not accept a client within 5s")


def stop(process: subprocess.Popen[object]) -> None:
    if process.poll() is not None:
        return
    if os.name != "nt":
        try:
            os.killpg(process.pid, signal.SIGKILL)
            return
        except ProcessLookupError:
            return
    process.kill()


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def setup(client: MonitorClient, addresses: list[int]) -> list[int]:
    ids = []
    for addr in addresses:
        ids.append(client.call("set_breakpoint", {"addr": addr, "kind": "exec"})["id"])
    return ids


def clear(client: MonitorClient, ids: list[int]) -> None:
    for ident in ids:
        client.call("clear_breakpoint", {"id": ident})


def read_byte(client: MonitorClient, addr: int) -> int:
    return bytes.fromhex(client.call("read_memory", {"addr": addr, "length": 1})["data"])[0]


def read_bytes(client: MonitorClient, addr: int, length: int) -> bytes:
    return bytes.fromhex(client.call("read_memory", {"addr": addr, "length": length})["data"])


def cold_attract(client: MonitorClient, owner: tuple[int, int] | None = None) -> str:
    ids = setup(client, [PFT, LOAD_DONE, PUBLISH])
    hit = client.run_to_breakpoint()
    if hit.get("pc") != PFT:
        raise MonitorError(f"cold entry PC mismatch: {hit}")
    clear(client, [ids[0]])
    if owner is not None:
        client.call("write_memory", {"addr": FB_FRONT, "data": f"{owner[0]:02x}"})
        client.call("write_memory", {"addr": FB_BACK, "data": f"{owner[1]:02x}"})
    loaded = client.run_to_breakpoint()
    if loaded.get("pc") != LOAD_DONE:
        raise MonitorError(f"cold load-done PC mismatch: {loaded}")
    requested = read_byte(client, PRES_SCREEN)
    if requested != 0:
        raise MonitorError(f"cold requested map is not attract: {requested:02x}")
    prev = read_bytes(client, PRES_PREV, 3)
    event = read_byte(client, PRES_EVENT)
    if event != 0:
        raise MonitorError(f"cold pre-credit event={event:02x}")
    clear(client, [ids[1]])
    published = client.run_to_breakpoint()
    if published.get("pc") != PUBLISH:
        raise MonitorError(f"cold publish PC mismatch: {published}")
    frame = read_bytes(client, FB_START, FB_END - FB_START)
    frame_hash = hashlib.sha256(frame).hexdigest()
    if frame_hash != ATTRACT_FB_SHA256:
        raise MonitorError(f"attract framebuffer hash mismatch: {frame_hash}")
    owner_state = (read_byte(client, FB_FRONT), read_byte(client, FB_BACK), read_byte(client, FB_PENDING))
    clear(client, [ids[2]])
    print(f"BUG009_MONITOR_COLD requested={requested:02x} prev={prev.hex()} event=00 framebuffer={frame_hash} owner={owner_state}")
    return frame_hash


def run_scenario(binary: Path, rom: Path, scenario: str) -> None:
    process, client = launch(binary, rom, free_port())
    try:
        if scenario == "cold":
            cold_attract(client)
        elif scenario.startswith("owner"):
            order = (0, 1) if scenario == "owner-a" else (1, 0)
            frame_hash = cold_attract(client, order)
            print(f"BUG009_MONITOR_OWNER scenario={scenario} framebuffer={frame_hash}")
        elif scenario in ("edge5", "edge6"):
            cold_attract(client)
            ids = setup(client, [LOAD_DONE])
            key = 5 if scenario == "edge5" else 6
            client.call("inject_key", {"key": key, "action": "press"})
            hit = client.run_to_breakpoint()
            regs = client.call("read_registers")
            requested = read_byte(client, PRES_SCREEN)
            if hit.get("pc") != LOAD_DONE or requested != 3:
                raise MonitorError(f"{scenario} did not request high score: hit={hit} requested={requested:02x}")
            client.call("inject_key", {"key": key, "action": "release"})
            clear(client, ids)
            print(f"BUG009_MONITOR_{scenario.upper()} requested=03 edge=1")
        elif scenario == "held-release":
            ids = setup(client, [PFT, LOAD_DONE])
            client.call("inject_key", {"key": 5, "action": "press"})
            hit = client.run_to_breakpoint()
            if hit.get("pc") != PFT:
                raise MonitorError(f"held-key entry mismatch: {hit}")
            clear(client, [ids[0]])
            first = client.run_to_breakpoint()
            if first.get("pc") != LOAD_DONE:
                raise MonitorError(f"held-key cold load-done missing: {first}")
            prev = read_bytes(client, PRES_PREV, 3)
            client.call("inject_key", {"key": 5, "action": "release"})
            clear(client, [ids[1]])
            post_scan = setup(client, [POST_SCAN, LOAD_DONE])
            idle = client.run_to_breakpoint()
            event = read_byte(client, PRES_EVENT)
            if idle.get("pc") != POST_SCAN or event != 0:
                raise MonitorError(f"held release generated event={event:02x}: {idle}")
            clear(client, [post_scan[0]])
            client.call("inject_key", {"key": 5, "action": "press"})
            fresh = client.run_to_breakpoint()
            requested = read_byte(client, PRES_SCREEN)
            if fresh.get("pc") != LOAD_DONE or requested != 3:
                raise MonitorError(f"new press did not request high score: {fresh} requested={requested:02x}")
            print(f"BUG009_MONITOR_HELD prev={prev.hex()} release_event=00 new_press_map=03")
        else:
            raise MonitorError(f"unknown scenario {scenario}")
    finally:
        client.close()
        stop(process)
        process.wait(timeout=2)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--xroar", type=Path, default=Path("docs/reference/xroar/src/xroar"))
    parser.add_argument("--rom", type=Path, default=Path("build/ladybug.rom"))
    args = parser.parse_args()
    for scenario in ("cold", "edge5", "edge6", "held-release", "owner-a", "owner-b"):
        run_scenario(args.xroar, args.rom, scenario)
    print("BUG009_MONITOR_INPUT_PASS edges=5,6 held_release=1 owner_orders=0/1,1/0")


if __name__ == "__main__":
    main()
