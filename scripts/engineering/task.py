"""Build/validation work lives inside the same bounded process group as its tools."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engineering.core import INPUT_DIRS, PROFILES, HarnessError, capacity, describe, digest, load, open_build, save_new, snapshot


def build(request):
    import candidate_manifest
    root, run = Path(request["root"]), Path(request["run"])
    environment = request["environment"]
    inputs = Path(request.get("inputs", root))
    if not all((inputs / name).is_dir() for name in INPUT_DIRS) or not (inputs / "scripts/build.sh").is_file():
        raise HarnessError("build inputs must contain src, scripts, assets, tiled and scripts/build.sh")
    hashes = snapshot(inputs, run / "source")
    save_new(run / "source-files.json", ["source/" + p for p in hashes])
    candidate_manifest.write_manifest(run, "source.sha256", "source-files.json")
    tools = run / "tools"
    tools.mkdir()
    (tools / "lwasm").symlink_to(environment["tools"]["assembler"]["path"])
    (tools / "python3").symlink_to(sys.executable)
    env = os.environ.copy()
    env.update(PROFILES[request["profile"]])
    env.update(LADYBUG_BUILD_DIR=str(run / "source/build"), PATH=str(tools) + os.pathsep + os.environ.get("PATH", ""))
    with (run / "legacy-build.log").open("xb") as output:
        process = subprocess.run([environment["tools"]["bash"]["path"], "scripts/build.sh", "build"],
                                 cwd=run / "source", env=env, stdin=subprocess.DEVNULL, stdout=output, stderr=output)
    outcome = {"classification": "passed" if process.returncode == 0 else "command_failed", "exit_code": process.returncode}
    record = describe(run, request["profile"], request["revision"], hashes, outcome, environment,
                      origin={"path": str(inputs), "revision_kind": "enclosing execution repository HEAD; source hashes identify actual inputs"})
    log = (run / "legacy-build.log").read_text(errors="replace")
    save_new(run / "summary.json", {"classification": outcome["classification"], "description": str(run / "build.json"),
             "rom_produced": record["rom"] in record["artifacts"],
             "source_documentation": "failed" if "source documentation: FAIL:" in log else "passed" if "source documentation: PASS:" in log else "not_established",
             "release_accepted": False})
    return process.returncode


def validate(request):
    from engineering.cli import checker_identity
    result = {"schema": 1, "classification": "harness_failure", "checker": checker_identity(), "release_accepted": False}
    try:
        path, record = open_build(request["description"])
        policy = load(request["policy"])
        if policy.get("schema") != 1 or not policy.get("limits"):
            raise ValueError("unsupported or empty capacity policy")
        checks = capacity(record, policy["limits"])
        for name, size in policy.get("exact_sizes", {}).items():
            actual = record["artifacts"].get("source/build/" + name, {}).get("bytes")
            checks.append({"artifact": name, "bytes": actual, "exact_bytes": size, "passed": actual == size})
        result.update(description_sha256=digest(path), policy_sha256=digest(request["policy"]), checks=checks,
                      classification="passed" if all(c["passed"] for c in checks) else "product_failure",
                      legacy_build=record["build_result"]["classification"],
                      scope="artifact identity and explicit capacity only; legacy behavior/documentation gates remain separate")
    except (OSError, ValueError, KeyError) as error:
        result["reason"] = str(error)
    save_new(Path(request["run"]) / "validation.json", result)
    return 0 if result["classification"] == "passed" else 1


if __name__ == "__main__":
    request = load(sys.argv[1])
    raise SystemExit(globals()[request["operation"]](request))
