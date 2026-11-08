"""Portable build records and supervised jobs. No emulator or game imports."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import time
import uuid

PROFILES = {
    "keyboard-adaptive": {"LADYBUG_PROFILE": "complete", "LADYBUG_INPUT": "keyboard", "LADYBUG_ADAPTIVE": "1"},
    "joystick-adaptive": {"LADYBUG_PROFILE": "complete", "LADYBUG_INPUT": "joystick", "LADYBUG_ADAPTIVE": "1"},
    "keyboard-nonadaptive": {"LADYBUG_PROFILE": "complete", "LADYBUG_INPUT": "keyboard", "LADYBUG_ADAPTIVE": "0"},
}
INPUT_DIRS = ("src", "scripts", "assets", "tiled")
MAP_RE = re.compile(r"^Symbol: (\w+) .* = ([0-9A-Fa-f]+)$", re.M)


class HarnessError(ValueError):
    pass


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1048576), b""):
            h.update(chunk)
    return h.hexdigest()


def save_new(path, value):
    """Native UTF-8/LF output; never serialize data into a shell command."""
    data = (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
    with Path(path).open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def inside(root, name):
    if not isinstance(name, str) or not name or "\\" in name or any(ord(c) < 32 for c in name):
        raise HarnessError("invalid relative path")
    p = PurePosixPath(name)
    if p.is_absolute() or ":" in name or any(x in ("", ".", "..") for x in name.split("/")):
        raise HarnessError("path must be normalized and relative")
    result = (Path(root) / name).resolve()
    try:
        result.relative_to(Path(root).resolve())
    except ValueError:
        raise HarnessError("path escapes bundle")
    return result


def allocate(parent, operation):
    parent = Path(parent).resolve()
    parent.mkdir(parents=True, exist_ok=True)
    path = parent / (time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) + "-" + operation + "-" + uuid.uuid4().hex[:12])
    path.mkdir()  # exclusive allocation, no caller-managed empty folder
    return path


def run_job(run, argv, cwd, seconds, env=None):
    """Detached supervisor persists results even when the caller disappears."""
    if os.name != "posix":
        raise HarnessError("run production commands through WSL")
    if not 0 < seconds <= 86400:
        raise HarnessError("invalid job deadline")
    run = Path(run).resolve()
    spec = {"schema": 1, "argv": [str(x) for x in argv], "cwd": str(Path(cwd).resolve()),
            "seconds": seconds, "env": env or {}}
    save_new(run / "job.json", spec)
    worker = Path(__file__).with_name("supervisor.py")
    with (run / "supervisor.log").open("xb") as log:
        process = subprocess.Popen([sys.executable, "-B", str(worker), str(run / "job.json")],
                                   stdin=subprocess.PIPE, stdout=log, stderr=log, start_new_session=True)
        try:
            process.wait(timeout=seconds + 3)
        except BaseException:
            process.stdin.close()  # EOF is the independent controller-loss signal
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.terminate()
                process.wait(timeout=2)
            raise
        finally:
            process.stdin.close()
    result = run / "result.json"
    if not result.exists():
        save_new(result, {"schema": 1, "classification": "harness_failure", "reason": "supervisor produced no result", "exit_code": process.returncode})
    return load(result)


def source_files(root):
    result = {}
    for directory in INPUT_DIRS:
        for p in sorted((Path(root) / directory).rglob("*")):
            if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc":
                if p.is_symlink():
                    raise HarnessError("source snapshot refuses symlinks: " + str(p))
                result[p.relative_to(root).as_posix()] = digest(p)
    return result


def wiki_files(root):
    return {p.relative_to(root).as_posix(): digest(p)
            for p in sorted((root / "wiki").rglob("*.html"))
            if "evidence" not in p.relative_to(root / "wiki").parts}


def snapshot(root, destination):
    """Copy inputs only, not build trees. Refuse concurrent source changes."""
    root, destination = Path(root).resolve(), Path(destination).resolve()
    before = source_files(root)
    wiki = wiki_files(root)
    destination.mkdir()
    for name in before:
        target = inside(destination, name)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / name, target)
    # Source-documentation gates need the authored wiki, not its evidence payloads.
    for name in wiki:
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / name, target)
    if source_files(destination) != before or source_files(root) != before:
        raise HarnessError("source changed during snapshot; no build dispatched")
    if wiki_files(root) != wiki or wiki_files(destination) != wiki:
        raise HarnessError("wiki changed during snapshot; no build dispatched")
    return dict(before, **wiki)


def describe(bundle, profile, revision, source_hashes, job, environment, origin=None):
    bundle = Path(bundle)
    artifacts = {}
    for p in sorted((bundle / "source" / "build").rglob("*")):
        if p.is_file() and "__pycache__" not in p.parts:
            name = p.relative_to(bundle).as_posix()
            record = {"sha256": digest(p), "bytes": p.stat().st_size}
            if p.suffix == ".map":
                record["symbols"] = {n: int(v, 16) for n, v in MAP_RE.findall(p.read_text(encoding="utf-8"))}
            artifacts[name] = record
    # Source hashes retain the exact archived input identity. New checkers have
    # their own result identity and never claim the archived ROM was rebuilt.
    result = {"schema": 1, "profile": profile, "settings": PROFILES[profile], "revision": revision,
              "source_inputs": source_hashes, "artifacts": artifacts, "build_result": job,
              "environment": environment, "rom": "source/build/ladybug.rom"}
    if origin is not None:
        result["source_origin"] = origin
    save_new(bundle / "build.json", result)
    return result


def open_build(description, selected=None):
    path = Path(description).resolve()
    record = load(path)
    if record.get("schema") != 1 or record.get("profile") not in PROFILES:
        raise HarnessError("unsupported build description")
    if record.get("settings") != PROFILES[record["profile"]]:
        raise HarnessError("profile/settings mismatch")
    if record.get("rom") not in record.get("artifacts", {}):
        raise HarnessError("build has no recorded ROM")
    names = list(record["artifacts"]) if selected is None else selected
    for name in names:
        if name not in record["artifacts"]:
            raise HarnessError("unrecorded artifact: " + name)
        item = record["artifacts"][name]
        p = inside(path.parent, name)
        if not p.is_file() or p.stat().st_size != item["bytes"] or digest(p) != item["sha256"]:
            raise HarnessError("artifact changed or missing: " + name)
        if p.suffix == ".map" and item.get("symbols") != {n: int(v, 16) for n, v in MAP_RE.findall(p.read_text(encoding="utf-8"))}:
            raise HarnessError("symbol description differs from its map: " + name)
    return path, record


def capacity(record, limits):
    checks = []
    for filename, maximum in limits.items():
        if type(maximum) is not int or maximum < 0:
            raise HarnessError("invalid capacity policy")
        key = "source/build/" + filename
        if key not in record["artifacts"]:
            raise HarnessError("capacity artifact missing: " + filename)
        size = record["artifacts"][key]["bytes"]
        checks.append({"artifact": filename, "bytes": size, "maximum": maximum,
                       "margin": maximum - size, "passed": size <= maximum})
    return checks
