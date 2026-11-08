"""Offline harness qualification. Fake tools only; never starts the game."""
from __future__ import annotations

import argparse
from contextlib import redirect_stdout, redirect_stderr
import io
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.dont_write_bytecode = True
from engineering import core, cli, runtime
from engineering.audit import inventory


class Base(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="ladybug engineering ")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def bundle(self, size=1280):
        bundle = self.root / "bundle"
        build = bundle / "source" / "build"
        build.mkdir(parents=True)
        (build / "ladybug.rom").write_bytes(bytes(65536))
        (build / "module.bin").write_bytes(bytes([0x96, 0xA4, 0x81, 0xA5, 0x27, 8, 0x86, 0x3D]) + bytes(size - 8))
        (build / "module.map").write_text("Symbol: entry (module.bin) = 1900\n", encoding="utf-8")
        core.describe(bundle, "keyboard-adaptive", "fixture-revision", {}, {"classification": "passed"}, {})
        return bundle / "build.json"

    def scenario(self):
        return {"schema": 1, "name": "fixture", "purpose": "known fixture anchor", "max_seconds": 4,
                "marker": {"image": "source/build/module.bin", "map": "source/build/module.map", "symbol": "entry",
                           "image_origin": 6400, "expected_pages": {"0": 56}, "byte_count": 8},
                "reads": [{"name": "selection", "address": 224, "length": 1}]}

class Fixture(Base):
    def test_json_unicode_lf_and_no_overwrite(self):
        path = self.root / "result.json"
        core.save_new(path, {"text": "café — 東京\nnext"})
        before = path.read_bytes()
        self.assertNotIn(b"\r", before)
        self.assertTrue(before.endswith(b"\n"))
        self.assertEqual(core.load(path)["text"], "café — 東京\nnext")
        with self.assertRaises(FileExistsError):
            core.save_new(path, {})
        self.assertEqual(before, path.read_bytes())

    def test_relative_paths_reject_escape(self):
        for name in ("../other", "/tmp/out", "C:/out", "a\\b", "a//b", "a/./b", "a\n"):
            with self.subTest(name=name), self.assertRaises(core.HarnessError):
                core.inside(self.root, name)

    def test_run_allocation_is_exclusive(self):
        self.assertNotEqual(core.allocate(self.root, "observe"), core.allocate(self.root, "observe"))

    def test_snapshot_copies_inputs_not_old_outputs(self):
        for directory in core.INPUT_DIRS:
            (self.root / directory).mkdir()
            (self.root / directory / "fixture.txt").write_bytes(b"input\r\n")
        (self.root / "build").mkdir()
        (self.root / "build" / "old.rom").write_bytes(b"old")
        target = self.root / "snapshot"
        hashes = core.snapshot(self.root, target)
        self.assertEqual(hashes, core.source_files(target))
        self.assertFalse((target / "build").exists())

    def test_snapshot_detects_source_changed_during_copy(self):
        (self.root / "src").mkdir()
        source = self.root / "src" / "fixture.s"
        source.write_bytes(b"first")
        copy = shutil.copyfile
        def changing(a, b):
            result = copy(a, b)
            source.write_bytes(b"second")
            return result
        with mock.patch.object(core.shutil, "copyfile", side_effect=changing), self.assertRaises(core.HarnessError):
            core.snapshot(self.root, self.root / "snapshot")

    def test_bundle_can_move_and_validate(self):
        path = self.bundle()
        shutil.move(path.parent, self.root / "moved bundle")
        _, record = core.open_build(self.root / "moved bundle" / "build.json")
        self.assertEqual(record["revision"], "fixture-revision")

    def test_changed_artifact_is_rejected(self):
        path = self.bundle()
        (path.parent / "source/build/module.bin").write_bytes(b"changed")
        with self.assertRaises(core.HarnessError):
            core.open_build(path)

    def test_map_symbol_record_cannot_drift(self):
        path = self.bundle()
        record = core.load(path)
        record["artifacts"]["source/build/module.map"]["symbols"]["entry"] += 1
        path.write_text(json.dumps(record))
        with self.assertRaises(core.HarnessError):
            core.open_build(path)

    def test_capacity_exact_boundary_and_one_byte_overflow(self):
        for size, expected in ((1280, True), (1281, False)):
            record = {"artifacts": {"source/build/module.bin": {"bytes": size}}}
            checks = core.capacity(record, {"module.bin": 1280})
            self.assertEqual(checks[0]["passed"], expected)
            self.assertEqual(checks[0]["margin"], 1280 - size)

    def test_new_checker_or_worktree_edit_does_not_rebuild_archived_rom(self):
        path = self.bundle()
        (self.root / "new-verifier.py").write_text("# new checker\n")
        _, record = core.open_build(path)
        self.assertTrue(core.capacity(record, {"module.bin": 1280})[0]["passed"])

    def test_plan_derives_anchor_from_current_map_and_bytes(self):
        path = self.bundle()
        _, _, address, expected = runtime.plan(path, self.scenario())
        self.assertEqual(address, 0x1900)
        self.assertEqual(expected.hex(), "96a481a52708863d")

    def test_plan_requires_mapping_for_every_read(self):
        path = self.bundle()
        scenario = self.scenario()
        scenario["reads"][0]["address"] = 0xA000
        with self.assertRaises(core.HarnessError):
            runtime.plan(path, scenario)

    def test_plan_rejects_unbounded_or_invalid_anchor(self):
        path = self.bundle()
        scenario = self.scenario()
        scenario["max_seconds"] = 61
        with self.assertRaises(core.HarnessError):
            runtime.plan(path, scenario)
        scenario = self.scenario()
        scenario["marker"]["symbol"] = "missing"
        with self.assertRaises(core.HarnessError):
            runtime.plan(path, scenario)

    def test_gdb_plan_has_no_guest_write_and_checks_bytes_before_reads(self):
        text = runtime.commands(0x1900, b"\x96\xa4", self.scenario(), 12345, self.root)
        self.assertNotIn("set $", text)
        self.assertNotIn("set {", text)
        self.assertLess(text.index("set architecture m6809"), text.index("target remote"))
        self.assertLess(text.index("0xffa0"), text.index("0x1900 != 150"))
        self.assertLess(text.index("HARNESS_ANCHOR_VERIFIED"), text.index("selection.bin"))
        self.assertIn("dump binary memory anchor.bin ", text)
        self.assertNotIn(str(self.root), text)

    def test_audit_retains_purpose_and_flags_without_retiring_gate(self):
        (self.root / "scripts").mkdir()
        (self.root / "scripts/verify_fixture.py").write_text('"""Protect the fixture."""\nrequired_source = []\n')
        row = inventory(self.root)["verifiers"][0]
        self.assertEqual(row["purpose"], "Protect the fixture.")
        self.assertIn("lexical-source-contract", row["review_flags"])
        self.assertIn("no gate retired", row["migration"])

    def test_profile_description_cannot_mislabel_input(self):
        path = self.bundle()
        record = core.load(path)
        record["settings"] = dict(record["settings"], LADYBUG_INPUT="joystick")
        path.write_text(json.dumps(record))
        with self.assertRaises(core.HarnessError):
            core.open_build(path)

    def test_selected_artifacts_do_not_require_unrelated_listing(self):
        path = self.bundle()
        record = core.load(path)
        record["artifacts"]["source/build/unrelated.lst"] = {"sha256": "0" * 64, "bytes": 0}
        path.write_text(json.dumps(record))
        core.open_build(path, [record["rom"]])
        with self.assertRaises(core.HarnessError):
            core.open_build(path)

    def test_build_environment_does_not_require_runtime_tools(self):
        path = self.root / "environment.json"
        executable = str(Path(sys.executable).resolve())
        tool = {"path": executable, "sha256": core.digest(executable)}
        core.save_new(path, {"schema": 1, "debugger_6809": False, "tools": {"assembler": tool, "bash": tool}})
        cli.tool_environment(path, ("assembler", "bash"))
        with self.assertRaises(core.HarnessError):
            cli.tool_environment(path, ("debugger", "emulator"), debugger_required=True)


@unittest.skipUnless(os.name == "posix", "process-group qualification requires WSL/Linux")
class ProcessTests(Base):
    def job(self, code, seconds=2):
        run = core.allocate(self.root, "test")
        result = core.run_job(run, [sys.executable, "-B", "-c", code], self.root, seconds)
        return run, result

    def test_success_and_nonzero_exit_are_distinct(self):
        _, good = self.job("print('known marker')")
        _, bad = self.job("raise SystemExit(7)")
        self.assertEqual(good["classification"], "passed")
        self.assertEqual(bad["classification"], "command_failed")
        self.assertEqual(bad["exit_code"], 7)

    def test_missing_executable_is_a_recorded_harness_failure(self):
        run = core.allocate(self.root, "missing")
        result = core.run_job(run, ["/no/such/fixture-executable"], self.root, 2)
        self.assertEqual(result["classification"], "harness_failure")
        self.assertTrue((run / "result.json").is_file())

    def test_whole_job_timeout_cleans_process(self):
        _, result = self.job("import time; time.sleep(30)", .4)
        self.assertEqual(result["classification"], "timeout")
        self.assertTrue(result["process_exited"])
        self.assertLess(result["elapsed_seconds"], 1.5)

    def test_successful_parent_cannot_leave_descendant(self):
        run, result = self.job("import subprocess,sys; p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)']); print(p.pid,flush=True)")
        pid = int((run / "output.log").read_text())
        self.assertEqual(result["classification"], "passed")
        self.assert_dead(pid)

    def assert_dead(self, pid):
        deadline = time.monotonic() + 1
        while time.monotonic() < deadline:
            path = Path(f"/proc/{pid}/stat")
            if not path.exists() or path.read_text().split(")")[1].split()[0] == "Z":
                return
            time.sleep(.02)
        self.fail("owned process survived cleanup: " + str(pid))

    def test_controller_death_is_seen_as_eof_and_cleans_child(self):
        run = core.allocate(self.root, "controller-loss")
        core.save_new(run / "job.json", {"argv": [sys.executable, "-c", "import time; time.sleep(30)"], "cwd": str(self.root), "env": {}, "seconds": 20})
        worker = Path(core.__file__).with_name("supervisor.py")
        process = subprocess.Popen([sys.executable, "-B", str(worker), str(run / "job.json")], stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, start_new_session=True)
        time.sleep(.15)
        process.stdin.close()  # same EOF produced by death of the caller
        process.wait(timeout=3)
        process.stderr.close()
        result = core.load(run / "result.json")
        self.assertEqual(result["classification"], "cancelled")
        self.assert_dead(result["pid"])

    def test_fake_profile_builds_use_disjoint_source_and_artifact_roots(self):
        for folder in core.INPUT_DIRS:
            (self.root / folder).mkdir()
        (self.root / "scripts/build.sh").write_text("from pathlib import Path\np=Path('build'); p.mkdir(); (p/'ladybug.rom').write_bytes(bytes(65536))\nprint('source documentation: PASS: fixture')\n")
        executable = str(Path(sys.executable).resolve())
        environment = {"schema": 1, "debugger_6809": True, "tools": {"assembler": {"path": executable, "sha256": core.digest(executable)}, "bash": {"path": executable, "sha256": core.digest(executable)}}}
        core.save_new(self.root / "environment.json", environment)
        descriptions = []
        for profile in ("keyboard-adaptive", "joystick-adaptive"):
            args = argparse.Namespace(root=self.root, runs=self.root / "runs", profile=profile, environment=self.root / "environment.json", timeout=3)
            with mock.patch.object(cli.subprocess, "check_output", return_value="fixture-head\n"):
                result = cli.build(args)
            self.assertEqual(result["classification"], "passed")
            descriptions.append(Path(result["description"]))
        self.assertNotEqual(descriptions[0].parent, descriptions[1].parent)
        core.open_build(descriptions[0])
        self.assertFalse((self.root / "build").exists())

    def test_separate_input_snapshot_does_not_mutate_frozen_source(self):
        inputs = self.root / "frozen"
        for folder in core.INPUT_DIRS:
            (inputs / folder).mkdir(parents=True)
        script = inputs / "scripts/build.sh"
        script.write_text("from pathlib import Path\np=Path('build'); p.mkdir(); (p/'ladybug.rom').write_bytes(bytes(65536))\n")
        before = core.source_files(inputs)
        executable = str(Path(sys.executable).resolve())
        tool = {"path": executable, "sha256": core.digest(executable)}
        core.save_new(self.root / "environment.json", {"schema": 1, "tools": {"assembler": tool, "bash": tool}})
        args = argparse.Namespace(root=self.root, runs=self.root / "runs", inputs=inputs,
                                  profile="keyboard-adaptive", environment=self.root / "environment.json", timeout=3)
        with mock.patch.object(cli.subprocess, "check_output", return_value="fixture-head\n"):
            result = cli.build(args)
        self.assertEqual(result["classification"], "passed")
        self.assertEqual(before, core.source_files(inputs))
        self.assertFalse((inputs / "build").exists())
        self.assertEqual(core.load(result["description"])["source_origin"]["path"], str(inputs))

    def test_validation_reports_product_overflow_separately_from_harness_failure(self):
        path = self.bundle(size=1281)
        policy = self.root / "policy.json"
        core.save_new(policy, {"schema": 1, "limits": {"module.bin": 1280}})
        args = argparse.Namespace(root=self.root, runs=self.root / "runs", description=path, policy=policy, timeout=3)
        result = cli.validate(args)
        self.assertEqual(result["classification"], "product_failure")
        (path.parent / "source/build/module.bin").write_bytes(b"corrupt")
        result = cli.validate(args)
        self.assertEqual(result["classification"], "harness_failure")

    def test_validator_cannot_pass_after_worker_failure(self):
        path = self.bundle()
        policy = self.root / "policy.json"
        core.save_new(policy, {"schema": 1, "limits": {"module.bin": 1280}})
        args = argparse.Namespace(root=self.root, runs=self.root / "runs", description=path, policy=policy, timeout=3)
        def failed_worker(run, *unused):
            core.save_new(run / "validation.json", {"classification": "passed"})
            return {"classification": "command_failed", "exit_code": 1}
        with mock.patch.object(cli, "run_job", side_effect=failed_worker):
            self.assertEqual(cli.validate(args)["classification"], "harness_failure")

    def fake_executable(self, name, body):
        path = self.root / name
        path.write_text("#!" + sys.executable + "\n" + body, encoding="utf-8")
        path.chmod(0o755)
        return path

    def test_manual_launch_uses_rgb_keyboard_mapping_and_no_session_deadline(self):
        path = self.bundle()
        emulator = self.fake_executable("manual-fixture", "import pathlib,sys,json\npathlib.Path(sys.argv[0]+'.args.json').write_text(json.dumps(sys.argv[1:]))\n")
        environment = self.root / "manual-environment.json"
        core.save_new(environment, {"schema": 1, "tools": {"emulator": {"path": str(emulator), "sha256": core.digest(emulator)}}})
        script = "import sys,argparse,pathlib; sys.path.insert(0,sys.argv[1]); from engineering.cli import launch; launch(argparse.Namespace(description=pathlib.Path(sys.argv[2]),environment=pathlib.Path(sys.argv[3]),runs=pathlib.Path(sys.argv[4])))"
        env = dict(os.environ, DISPLAY=":offline-fixture")
        subprocess.run([sys.executable, "-B", "-c", script, str(Path(core.__file__).resolve().parents[1]), str(path), str(environment), str(self.root / "runs")], env=env, stdout=subprocess.DEVNULL, check=True, timeout=3)
        arguments = core.load(str(emulator) + ".args.json")
        self.assertEqual(arguments[arguments.index("-tv-input") + 1], "rgb")
        self.assertEqual(arguments[arguments.index("-joy-right") + 1], "")
        record = core.load(next((self.root / "runs").glob("*/launch.json")))
        self.assertIsNone(record["session_deadline"])
        self.assertEqual(record["manual_acceptance"], "pending")

    def test_doctor_resolves_debugger_executable_and_qualifies_architecture(self):
        tool = self.fake_executable("fake-tool", "import sys,pathlib\nprint('m6809' if 'show architecture' in sys.argv else 'fixture tool 1.0')\nif 'show architecture' in sys.argv: pathlib.Path('doctor-dump.bin').write_bytes(b'Z')\n")
        args = argparse.Namespace(root=self.root, runs=self.root / "runs", assembler=str(tool), debugger=str(tool), emulator=str(tool), bash=str(tool))
        result = cli.doctor(args)
        environment = core.load(result["environment"])
        self.assertTrue(environment["debugger_6809"])
        self.assertFalse(environment["runtime_qualified"])
        tool.write_text("changed")
        with self.assertRaises(core.HarnessError):
            cli.tool_environment(result["environment"])

    def test_fake_observation_success_and_corrupt_anchor(self):
        path = self.bundle()
        scenario_path = self.root / "scenario.json"
        core.save_new(scenario_path, self.scenario())
        emulator = self.fake_executable("fake-emulator", "import socket,sys,time\ns=socket.socket(); s.bind(('127.0.0.1',int(sys.argv[sys.argv.index('-gdb-port')+1]))); s.listen(); time.sleep(30)\n")
        for wrong in (False, True):
            debugger = self.fake_executable("fake-debugger-" + str(wrong),
                "import pathlib,sys,shlex\ntext=pathlib.Path(sys.argv[sys.argv.index('-x')+1]).read_text()\n"
                "for line in text.splitlines():\n if line.startswith('dump binary memory '):\n  words=shlex.split(line); target=pathlib.Path(words[3]); length=int(words[5],16)-int(words[4],16); target.write_bytes((bytes.fromhex('" + ("ffffffffffffffff" if wrong else "96a481a52708863d") + "') if target.name=='anchor.bin' else bytes([1])*length))\n"
                "print('HARNESS_ANCHOR_VERIFIED')\n")
            environment_path = self.root / ("environment-" + str(wrong) + ".json")
            core.save_new(environment_path, {"schema": 1, "debugger_6809": True, "debugger_dump_output": True, "tools": {
                "debugger": {"path": str(debugger), "sha256": core.digest(debugger)},
                "emulator": {"path": str(emulator), "sha256": core.digest(emulator)}}})
            args = argparse.Namespace(root=self.root, runs=self.root / "runs", description=path,
                                      environment=environment_path, scenario=scenario_path)
            with mock.patch.dict(os.environ, {"DISPLAY": ":offline-fixture"}):
                result = cli.observe(args)
            self.assertEqual(result["classification"], "harness_failure" if wrong else "observed")
            self.assertTrue(result["observation"]["emulator_exited"])

    def test_killed_controller_cannot_leave_job_running(self):
        run = core.allocate(self.root, "killed-controller")
        code = "import sys; sys.path.insert(0,sys.argv[1]); from engineering.core import run_job; run_job(sys.argv[2],[sys.executable,'-c','import os,time; print(os.getpid(),flush=True); time.sleep(30)'],sys.argv[2],20)"
        controller = subprocess.Popen([sys.executable, "-B", "-c", code, str(Path(core.__file__).resolve().parents[1]), str(run)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline:
                if (run / "output.log").exists() and (run / "output.log").stat().st_size:
                    break
                time.sleep(.02)
            self.assertTrue((run / "output.log").exists())
            controller.kill()
            controller.wait(timeout=2)
            deadline = time.monotonic() + 3
            while not (run / "result.json").exists() and time.monotonic() < deadline:
                time.sleep(.02)
            result = core.load(run / "result.json")
            self.assertEqual(result["classification"], "cancelled")
            self.assert_dead(result["pid"])
        finally:
            if controller.poll() is None:
                controller.kill()
                controller.wait()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path)
    args = parser.parse_args()
    start = time.monotonic()
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if args.evidence:
        args.evidence.mkdir(parents=True, exist_ok=False)
        core.save_new(args.evidence / "qualification.json", {"schema": 1, "passed": result.wasSuccessful(), "tests": result.testsRun,
                      "skipped": len(result.skipped), "elapsed_seconds": round(time.monotonic() - start, 4),
                      "failures": [str(case) + "\n" + failure for case, failure in result.failures + result.errors],
                      "scope": "offline fixtures/fake tools only; no real game build or emulator", "test_source_sha256": core.digest(__file__), "harness": cli.checker_identity()})
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
