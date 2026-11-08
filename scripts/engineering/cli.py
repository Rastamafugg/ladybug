"""Build, validate, launch and observe without per-attempt command wrappers."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys

from .audit import inventory
from .core import (HarnessError, PROFILES, INPUT_DIRS, allocate, digest, inside,
                   load, open_build, run_job, save_new)


ROOT = Path(__file__).resolve().parents[2]
POLICY = Path(__file__).with_name("policy.json")


def checker_identity():
    return {p.name: digest(p) for p in sorted(Path(__file__).parent.glob("*.py"))}


def tool_environment(path, required=None, debugger_required=False):
    record = load(path)
    if record.get("schema") != 1:
        raise HarnessError("run doctor first; unsupported environment record")
    if debugger_required and not record.get("debugger_6809"):
        raise HarnessError("debugger architecture has not been qualified")
    if debugger_required and not record.get("debugger_dump_output"):
        raise HarnessError("run doctor --scope runtime to qualify the debugger's native file writer")
    for name in (required if required is not None else record["tools"]):
        if name not in record["tools"]:
            raise HarnessError("environment does not qualify required tool: " + name)
        tool = record["tools"][name]
        if digest(tool["path"]) != tool["sha256"]:
            raise HarnessError("tool changed since doctor: " + name)
    return record


def doctor(args):
    if sys.platform != "linux":
        raise HarnessError("run doctor and production jobs in WSL")
    run = allocate(args.runs, "doctor")
    args.active_run = run
    tools = {}
    names = {"all": ("assembler", "debugger", "emulator", "bash"), "build": ("assembler", "bash"), "runtime": ("debugger", "emulator")}[getattr(args, "scope", "all")]
    for name in names:
        requested = getattr(args, name)
        resolved = shutil.which(requested)
        if not resolved:
            raise HarnessError("tool unavailable: " + requested)
        executable = str(Path(resolved).resolve())
        job = run / name
        job.mkdir()
        result = run_job(job, [executable, "--version"], args.root, 5)
        if result["classification"] != "passed":
            raise HarnessError("tool version failed; see " + str(job))
        tools[name] = {"path": executable, "sha256": digest(executable),
                       "version": (job / "output.log").read_text(errors="replace")[:4096].strip()}
    if "debugger" in tools:
        job = run / "debugger-architecture"
        job.mkdir()
        result = run_job(job, [tools["debugger"]["path"], "-nx", "-q", "-batch", "-ex", "set architecture m6809", "-ex", "show architecture", "-ex", "dump binary value doctor-dump.bin (unsigned char)0x5a"], job, 5)
        if result["classification"] != "passed" or "m6809" not in (job / "output.log").read_text(errors="replace").lower():
            raise HarnessError("debugger cannot select m6809; see " + str(job))
        if not (job / "doctor-dump.bin").is_file() or (job / "doctor-dump.bin").read_bytes() != b"Z":
            raise HarnessError("debugger native file writer failed; see " + str(job))
    save_new(run / "environment.json", {"schema": 1, "tools": tools, "debugger_6809": "debugger" in tools,
              "debugger_dump_output": "debugger" in tools,
              "python": {"path": sys.executable, "version": sys.version},
              "runtime_qualified": False, "limitation": "version and architecture only; no XRoar connection or watchpoint qualification"})
    return {"classification": "passed", "environment": str(run / "environment.json")}


def build(args):
    if os.name != "posix":
        raise HarnessError("run builds through WSL")
    if not 0 < args.timeout <= 600:
        raise HarnessError("build deadline must be greater than zero and at most 600 seconds")
    try:
        relative = args.runs.relative_to(args.root)
    except ValueError:
        raise HarnessError("build run root must be inside the project for legacy git revision discovery")
    if not relative.parts or relative.parts[0] in INPUT_DIRS + ("wiki",):
        raise HarnessError("run outputs cannot be placed inside authored input directories")
    environment = tool_environment(args.environment, ("assembler", "bash"))
    run = allocate(args.runs, args.profile)
    args.active_run = run
    # The child source root retains the legacy conventional build/ directory;
    # each build has an independent source root, so profiles share no outputs.
    try:
        run.relative_to(args.root)
    except ValueError:
        raise HarnessError("build run root must be inside the project for legacy git revision discovery")
    revision = subprocess.check_output(["git", "-C", str(args.root), "rev-parse", "HEAD"], text=True, timeout=5).strip()
    inputs = getattr(args, "inputs", None) or args.root
    inputs = inputs.resolve()
    save_new(run / "request.json", {"operation": "build", "root": str(args.root), "run": str(run),
             "inputs": str(inputs), "profile": args.profile, "revision": revision, "environment": environment})
    job = run / "construction"
    job.mkdir()
    outcome = run_job(job, [sys.executable, "-B", str(Path(__file__).with_name("task.py")), str(run / "request.json")], args.root, args.timeout)
    summary = load(run / "summary.json") if (run / "summary.json").exists() else {"rom_produced": None, "description": None, "release_accepted": False}
    return dict(summary, classification=outcome["classification"], supervisor=outcome, run=str(run))


def validate(args):
    if not 0 < args.timeout <= 60:
        raise HarnessError("validation deadline must be greater than zero and at most 60 seconds")
    run = allocate(args.runs, "validate")
    args.active_run = run
    save_new(run / "request.json", {"operation": "validate", "run": str(run), "description": str(args.description.resolve()), "policy": str(args.policy.resolve())})
    outcome = run_job(run, [sys.executable, "-B", str(Path(__file__).with_name("task.py")), str(run / "request.json")], args.root, args.timeout)
    result = load(run / "validation.json") if (run / "validation.json").exists() else {"classification": "incomplete", "reason": "validation did not finish"}
    if outcome["classification"] not in ("passed", "command_failed"):
        result["classification"] = outcome["classification"]
    elif outcome["classification"] == "command_failed" and result["classification"] == "passed":
        result.update(classification="harness_failure", reason="validator wrote success but its process failed")
    return dict(result, supervisor=outcome, result=str(run / "validation.json"))


def launch(args):
    initial = load(args.description)
    path, record = open_build(args.description, [initial["rom"]])
    environment = tool_environment(args.environment, ("emulator",))
    if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        raise HarnessError("no visible WSL display; no XRoar launched")
    if record["build_result"]["classification"] != "passed":
        raise HarnessError("legacy build did not pass; inspect its separate results")
    run = allocate(args.runs, "manual-launch")
    args.active_run = run
    argv = [environment["tools"]["emulator"]["path"], "-machine", "coco3", "-machine-cpu", "6809", "-ram", "512",
            "-ram-init", "random", "-cart-type", "gmc", "-cart-rom", str(inside(path.parent, record["rom"])),
            "-cart-autorun", "-tv-input", "rgb", "-joy-right", "kjoy0" if record["settings"]["LADYBUG_INPUT"] == "joystick" else "", "-joy-left", ""]
    save_new(run / "launch.json", {"description_sha256": digest(path), "argv": argv, "manual_acceptance": "pending", "session_deadline": None})
    print("Manual RGB session; acceptance pending. Close XRoar when finished.", flush=True)
    os.execv(argv[0], argv)  # no agent timer or detached process bookkeeping


def observe(args):
    environment = tool_environment(args.environment, ("debugger", "emulator"), debugger_required=True)
    scenario = load(args.scenario)
    if not 0 < scenario.get("max_seconds", 0) <= 60:
        raise HarnessError("initial observation must be at most 60 seconds")
    path = args.description.resolve()
    run = allocate(args.runs, "observe")
    args.active_run = run
    # Freeze the actual scenario before dispatch. Later edits cannot change it.
    save_new(run / "request-scenario.json", scenario)
    save_new(run / "environment.json", environment)
    request = {"description": str(path), "scenario": str(run / "request-scenario.json"),
               "environment": str(run / "environment.json"), "output": str(run)}
    save_new(run / "request.json", request)
    outcome = run_job(run, [sys.executable, "-B", str(Path(__file__).with_name("runtime.py")), str(run / "request.json")], run, scenario["max_seconds"])
    observation = load(run / "observation.json") if (run / "observation.json").exists() else {"classification": "incomplete", "reason": "supervisor stopped before final observation"}
    classification = observation["classification"]
    if outcome["classification"] != "passed" and classification == "observed":
        classification = "harness_failure"
    if outcome["classification"] not in ("passed", "command_failed"):
        classification = outcome["classification"]
    return {"classification": classification, "supervisor": outcome, "observation": observation, "run": str(run)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--runs", type=Path, help="new runs allocated beneath this directory")
    sub = parser.add_subparsers(dest="operation", required=True)
    p = sub.add_parser("doctor", help="record tool versions and qualify the debugger architecture without a target")
    p.add_argument("--assembler", default="lwasm")
    p.add_argument("--debugger", default="m6809-gdb")
    p.add_argument("--emulator", default="xroar")
    p.add_argument("--bash", default="bash")
    p.add_argument("--scope", choices=("all", "build", "runtime"), default="all")
    p = sub.add_parser("build")
    p.add_argument("--profile", choices=PROFILES, required=True)
    p.add_argument("--environment", type=Path, required=True)
    p.add_argument("--timeout", type=float, default=600)
    p.add_argument("--inputs", type=Path, help="authored source tree to snapshot; defaults to --root; never writes into it")
    p = sub.add_parser("validate")
    p.add_argument("--description", type=Path, required=True)
    p.add_argument("--policy", type=Path, default=POLICY)
    p.add_argument("--timeout", type=float, default=60)
    for operation in ("launch", "observe"):
        p = sub.add_parser(operation)
        p.add_argument("--description", type=Path, required=True)
        p.add_argument("--environment", type=Path, required=True)
        if operation == "observe":
            p.add_argument("--scenario", type=Path, required=True)
    p = sub.add_parser("audit", help="inventory purposes and coupling; does not run or retire tests")
    p.add_argument("--output", type=Path, help="create a new purpose inventory JSON file")
    args = parser.parse_args(argv)
    args.root = args.root.resolve()
    args.runs = (args.runs or args.root / "repro" / "engineering").resolve()
    try:
        if args.operation == "audit":
            result = inventory(args.root)
            if args.output:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                save_new(args.output, result)
                result = {"classification": "passed", "verifiers": len(result["verifiers"]), "inventory": str(args.output.resolve())}
        else:
            result = globals()[args.operation](args)
        if getattr(args, "active_run", None):
            save_new(args.active_run / "operation-result.json", result)
        import json
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("classification", "passed") in ("passed", "observed") else 1
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        import json
        result = {"classification": "harness_failure", "reason": str(error)}
        if getattr(args, "active_run", None):
            save_new(args.active_run / "operation-result.json", result)
        print(json.dumps(result, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
