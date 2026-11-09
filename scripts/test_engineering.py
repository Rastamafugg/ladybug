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
from engineering import core, cli, runtime, dispatch_wsl
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


class ActorAB01Q1Fixtures(Base):
    """Synthetic actor pixels qualify the current observer and FRONT gate only."""
    def setUp(self):
        super().setUp()
        self.project = Path(__file__).resolve().parents[1]
        self.scenario_path = self.project / "scripts/engineering/scenarios/attract-actor-ab.json"
        self.scenario = core.load(self.scenario_path)
        self.description = self.project / "repro/feat012-profile-signoff-20261108-02/build-runs/20261108T230414Z-keyboard-adaptive-dfbb2f299657/build.json"
        _, _, self.context = runtime.actor_plan(self.description, self.scenario)
        self.definition = core.load(self.project / "wiki/internal/tickets/evidence/feat012-actor-ab-01-fixtures-20261108.json")
        import hashlib
        self.synthetic_hashes = [[hashlib.sha256(bytes([(phase * 64 + index + 1) & 255]) * 128).hexdigest()
                                  for index in range(8)] for phase in range(3)]

    class FakeMI:
        def __init__(self, context):
            self.context = context
            self.current = None
            self.requests = []

        def set_frame(self, frame):
            self.current = frame

        def command(self, command):
            if not command.startswith("-data-read-memory-bytes "):
                raise AssertionError("actor observer issued a non-read command")
            _, address, length = command.split()
            address, length = int(address, 0), int(length)
            if any(address <= forbidden < address + length for forbidden in (0xFF91, 0xFF9D)):
                raise AssertionError("write-only GIME register was read")
            self.requests.append((self.current["id"], address, length, command))
            for start, data in self.current["memory"].items():
                if start <= address and address + length <= start + len(data):
                    offset = address - start
                    found = data[offset:offset + length]
                    return '7^done,memory=[{begin="0x%x",offset="0x0",end="0x%x",contents="%s"}]' % (address, address + length, found.hex())
            raise AssertionError("unadmitted fixture read at " + hex(address))

    def frame(self, identity, owner, commit, timer, actor_phase, rendered_phase=1,
              stale_actor=None, page_owner=None, pc_kind="post"):
        import hashlib
        pixels = bytearray(0x7800)
        for index, actor in enumerate(self.context["actors"]):
            phase = 0 if stale_actor == index else rendered_phase
            row = bytes([(phase * 64 + index + 1) & 255]) * 8
            offset = actor["destination"] - 0x2000
            for y in range(16):
                pixels[offset + y * 160:offset + y * 160 + 8] = row
        expected_pages = self.scenario["front_owner_pages"][str(owner if page_owner is None else page_owner)]
        pages = bytes([0x38, *expected_pages])
        fb = bytes([owner, 1-owner, 0]) + commit.to_bytes(2, "big")
        memory = {
            0x00B0: timer.to_bytes(2, "big"), 0x008F: fb,
            0x00A5: bytes((2, 0)), 0x00D3: bytes((actor_phase,)), 0x00D4: b"\0",
            0xFFA0: pages, 0x2000: bytes(pixels),
        }
        if pc_kind == "phase":
            memory[self.context["phase_pc"]] = self.context["phase_bytes"]
        else:
            memory[self.context["post_pc"]] = self.context["post_bytes"]
        return {"id": identity, "memory": memory}

    def exercise(self, *, stale=False, timer_mismatch=False, page_mismatch=False, callback_cap=None):
        context = dict(self.context)
        context["phase_hashes"] = self.synthetic_hashes
        if callback_cap is not None:
            context["max_callbacks"] = callback_cap
        fake = self.FakeMI(context)
        capture = runtime.ActorCapture(fake, self.scenario, context)
        fake.set_frame(self.frame("phase-transition", 0, 0, 14, 0, pc_kind="phase"))
        capture.stop(context["phase_pc"])
        fake.set_frame(self.frame("commit-seed", 0, 0, 14, 1))
        capture.stop(context["post_pc"])
        sample_timer = 22 if timer_mismatch else 14
        fake.set_frame(self.frame("owner-0", 0, 1, sample_timer, 1))
        capture.stop(context["post_pc"])
        if callback_cap is not None and capture.terminal:
            return capture.finish(), fake, capture
        fake.set_frame(self.frame("owner-1-mismatch" if page_mismatch else "owner-1", 1, 2,
                                  sample_timer, 1, stale_actor=7 if stale else None,
                                  page_owner=0 if page_mismatch else None))
        try:
            capture.stop(context["post_pc"])
        except core.HarnessError as error:
            return {"classification": "harness_failure", "reason": str(error)}, fake, capture
        return capture.finish(), fake, capture

    def test_current_artifact_binds_eight_distinct_actor_animations(self):
        self.assertEqual(len(self.context["actors"]), self.definition["fixture_inputs"]["actor_count"])
        self.assertEqual(len({tuple(a["cell"]) for a in self.context["actors"]}), 8)
        self.assertEqual(len({a["destination"] for a in self.context["actors"]}), 8)
        self.assertEqual(len({tuple(a["source_codes"]) for a in self.context["actors"]}), 8)
        self.assertEqual(len(self.context["phase_hashes"]), 3)
        self.assertEqual(len(self.context["arcade_reference_matches"]), 2)
        self.assertEqual(runtime.actor_frame_from_phase(3), 1)
        self.assertEqual(core.digest(self.description), self.scenario["accepted_description_sha256"])
        self.assertEqual(core.digest(self.description.parent / "source/build/ladybug.rom"), self.scenario["accepted_rom_sha256"])
        environment = self.project / "repro/engineering/20261107T135116Z-doctor-d37896a3c907/environment.json"
        self.assertEqual(core.digest(environment), self.scenario["accepted_environment_sha256"])

    def test_positive_and_stale_owner_negative_cover_all_eight(self):
        result, fake, capture = self.exercise()
        self.assertEqual((result["classification"], result["diagnosis"]), ("observed", "no_stale_pixels_observed"))
        self.assertEqual((capture.phase_change["from_phase"], capture.phase_change["to_phase"]), (0, 1))
        self.assertEqual([sample["front"] for sample in capture.samples], [0, 1])
        self.assertTrue(all(len(sample["actors"]) == 8 for sample in capture.samples))
        self.assertEqual(result["retained_actor_crops"], 2)
        self.assertEqual(sum("pixels_hex" in crop for sample in capture.samples for crop in sample["actors"]), 2)
        self.assertTrue(all(command.startswith("-data-read-memory-bytes ") for _, _, _, command in fake.requests))
        crop_reads = [(event, address, size) for event, address, size, _ in fake.requests if 0x2000 <= address < 0x9800]
        self.assertEqual(len(crop_reads), 2 * 8 * 16)
        self.assertTrue(all(size == 8 for _, _, size in crop_reads))
        for event in ("owner-0", "owner-1"):
            self.assertEqual(sum(1 for name, address, _, _ in fake.requests if name == event and 0x2000 <= address < 0x9800), 8 * 16)

        result, _, capture = self.exercise(stale=True)
        self.assertEqual(result["diagnosis"], "stale_actor_pixels")
        self.assertIn({"front": 1, "actor_index": 7, "observed_phases": [0], "expected_phase": 1}, result["stale_actors"])
        retained = [(sample["front"], index) for sample in capture.samples
                    for index, crop in enumerate(sample["actors"]) if "pixels_hex" in crop]
        self.assertEqual(retained, [(0, 7), (1, 7)])

    def test_timer_negative_front_mapping_and_callback_cap(self):
        result, _, _ = self.exercise(timer_mismatch=True)
        self.assertEqual(result["diagnosis"], self.definition["fixture_inputs"]["timer_mismatch_negative"]["expected_diagnosis"])

        result, fake, _ = self.exercise(page_mismatch=True)
        self.assertEqual((result["classification"], result["reason"]), ("harness_failure", "front_page_mismatch"))
        self.assertFalse(any(name == "owner-1-mismatch" and 0x2000 <= address < 0x9800
                             for name, address, _, _ in fake.requests))

        result, _, _ = self.exercise(callback_cap=1)
        self.assertEqual((result["classification"], result["reason"], result["coverage_complete"]),
                         ("incomplete", "callback_cap", False))

    def test_actor_memory_responses_are_redacted_from_debugger_log(self):
        import io
        client = runtime.MI.__new__(runtime.MI)
        client.buffer = b'1^done,memory=[{contents="deadbeef"}]\n'
        client.log = io.BytesIO()
        client.redact_memory = True
        self.assertIn('contents="deadbeef"', client.line())
        self.assertIn(b'contents="<4 bytes>"', client.log.getvalue())
        self.assertNotIn(b"deadbeef", client.log.getvalue())

    def test_observer_deadline_is_not_reported_as_missing_coverage(self):
        capture = runtime.ActorCapture(self.FakeMI(self.context), self.scenario, self.context)
        result = runtime.actor_final_result(capture, True)
        self.assertEqual((result["classification"], result["reason"], result["coverage_complete"]),
                         ("timeout", "observer_deadline", False))

    def test_fixed_one_use_command_is_bound_to_pinned_inputs(self):
        command = dispatch_wsl.fixed_command("ActorAB01Runtime", self.root)
        self.assertEqual(command[command.index("--description") + 1], str(self.description))
        self.assertEqual(command[command.index("--environment") + 1], str(self.project / "repro/engineering/20261107T135116Z-doctor-d37896a3c907/environment.json"))
        self.assertEqual(command[command.index("--scenario") + 1], str(self.scenario_path))
        self.assertEqual(command[command.index("--runs") + 1], str(self.root / "native"))
        wrapper = (self.project / "scripts/engineering/dispatch-wsl.ps1").read_text(encoding="utf-8")
        self.assertIn("ActorAB01Runtime", wrapper.splitlines()[1])
        with self.assertRaises(ValueError):
            dispatch_wsl.fixed_command("arbitrary", self.root)


class Tool019Q1Fixtures(Base):
    """Approved independent inputs exercise acquisition, MI parsing and host policy."""
    def setUp(self):
        super().setUp()
        self.project = Path(__file__).resolve().parents[1]
        self.definition_path = self.project / 'wiki/internal/tickets/evidence/tool019/fixture-definitions-20261107-01.json'
        self.definitions = core.load(self.definition_path)
        self.scenario = core.load(self.project / 'scripts/engineering/scenarios/attract-manual-down.json')
        self.description = self.project / self.definitions['accepted_build']['description']
        _, _, self.context = runtime.menu_plan(self.description, self.scenario)

    class FakeMI:
        def __init__(self, definition, pixels):
            self.timeline=definition['timeline']; self.pixels=pixels
            self.index=-1; self.current=None; self.requests=[]

        def resume(self):
            self.index+=1
            if self.index>=len(self.timeline): raise TimeoutError('fixture_deadline')
            self.current=self.timeline[self.index]
            return runtime.mi_pc('*stopped,reason="breakpoint-hit",frame={addr="'+self.current['pc']+'"}')

        def command(self, command):
            if not command.startswith('-data-read-memory-bytes '):
                return '1^done'
            _,address,length=command.split();address=int(address,0);length=int(length)
            self.requests.append((self.current['id'],address,length))
            if any(address<=bad<address+length for bad in (0xff91,0xff9d)):
                raise AssertionError('write-only address requested')
            data={int(k,16):bytes.fromhex(v) for k,v in self.current['memory_hex'].items()}
            data[int(self.current['pc'],16)]=bytes.fromhex(self.current['code_signature'])
            if self.current['publication_span'] is not None:
                # Keep the overlapping post-marker's following bytes too.
                data[0xea0]=bytes.fromhex(self.current['publication_span'])
            bank=self.current.get('pixel_reference')
            if bank is not None:
                for name,base in [('start_game',0x6b3c),('options',0x753c)]:
                    for row,hexline in enumerate(self.pixels[bank][name]['scanlines']):
                        data[base+row*160]=bytes.fromhex(hexline)
            # Actual MI result record, parsed by the production reader.
            found=None
            if address in data:found=data[address][:length]
            else:
                for start,block in data.items():
                    if start<=address<start+len(block):found=block[address-start:address-start+length];break
            if found is None: raise AssertionError('unadmitted fixture read '+hex(address))
            return '7^done,memory=[{begin="0x%x",offset="0x0",end="0x%x",contents="%s"}]' % (address,address+len(found),found.hex())

    def exercise(self, definition):
        fake=self.FakeMI(definition,self.definitions['pixel_banks'])
        capture=runtime.MenuCapture(fake,self.scenario,self.context,definition['user_visual_report'])
        try:
            while not capture.terminal:
                capture.stop(fake.resume())
            result=capture.finish()
        except TimeoutError:
            result=capture.finish()
        except core.HarnessError as error:
            result=dict(classification='harness_failure',reason=str(error),coverage_complete=False)
        return result,fake,capture

    def test_capture_definitions(self):
        for definition in self.definitions['capture_cases']:
            with self.subTest(case=definition['id']):
                result,fake,capture=self.exercise(definition)
                expected=definition['expected']
                self.assertEqual(result['classification'],expected['result_class'])
                self.assertEqual(result.get('reason'),expected.get('reason'))
                self.assertEqual(result.get('coverage_complete'),expected['coverage_complete'])
                if result['classification']!='harness_failure':
                    self.assertEqual(result['menu_outcome'],expected['menu_outcome'])
                for name in definition.get('forbidden_pixel_samples',[]):
                    self.assertFalse(any(s==name and 0x2000<=a<0xa000 for s,a,n in fake.requests))
                for sample in capture.samples:
                    if sample.get('role') in ('seed','no_commit','repaint_pending') or sample['kind']=='input':
                        self.assertNotIn('pixels',sample)
                if expected['menu_outcome']=='not_reproduced_in_this_press':
                    self.assertGreaterEqual(min(capture.owners.values()),2)

    def test_idle_and_pre_increment_are_not_product_failures(self):
        # Independent adjacent variant: idle commits before the user's press
        # are outside required post-input consecutive coverage.
        import copy
        definition=copy.deepcopy(self.definitions['capture_cases'][0])
        for sample in definition['timeline'][2:]:
            raw=bytearray.fromhex(sample['memory_hex']['0x008f']);seq=int.from_bytes(raw[3:],'big')+20
            raw[3:]=seq.to_bytes(2,'big');sample['memory_hex']['0x008f']=raw.hex()
        result,_,_=self.exercise(definition)
        self.assertEqual(result['menu_outcome'],'not_reproduced_in_this_press')
        held=copy.deepcopy(next(c for c in self.definitions['capture_cases'] if c['id']=='C08'))
        held['timeline'][-1]['memory_hex']['0x00df']='020000'
        result,_,_=self.exercise(held)
        self.assertEqual(result['classification'],'incomplete')
        self.assertEqual(result['menu_outcome'],'invalid_fixture')

    def test_fixed_accepted_artifact_binding(self):
        import copy
        for field in ("accepted_description_sha256", "accepted_rom_sha256"):
            wrong=copy.deepcopy(self.scenario);wrong[field]="0"*64
            with self.subTest(field=field),self.assertRaises(core.HarnessError):
                runtime.menu_plan(self.description,wrong)

    def test_mi_transport_with_fake_executable(self):
        fake=self.root/'fake-gdb'
        fake.write_text('#!'+sys.executable+'\n'+r'''
import re,sys
for line in sys.stdin:
 m=re.match(r'(\d+)(.*)',line.strip()); token,command=m.groups()
 if command.startswith('-exec-continue'):
  print(token+'^running',flush=True)
  print('*stopped,reason="breakpoint-hit",frame={addr="0x0ec6"}',flush=True)
 elif command.startswith('-data-read-memory-bytes'):
  print(token+'^done,memory=[{begin="0x0",offset="0x0",end="0x2",contents="1234"}]',flush=True)
 else: print(token+'^done',flush=True)
''',encoding='utf8')
        fake.chmod(0o755)
        with (self.root/'mi.log').open('wb') as log:
            client=runtime.MI(str(fake),time.monotonic()+3,log,self.root)
            try:
                client.command('-gdb-set architecture m6809')
                self.assertEqual(client.resume(),0xec6)
                self.assertEqual(runtime.mi_memory(client.command('-data-read-memory-bytes 0x0 2'),2),bytes.fromhex('1234'))
                with self.assertRaises(core.HarnessError):runtime.mi_memory('1^done,memory=[]',2)
            finally:client.close()
        self.assertIsNotNone(client.process.poll())

    def test_same_powershell_host_policy(self):
        # Same real host state function, no dispatcher main or game launch.
        ps=shutil.which('powershell.exe')
        self.assertIsNotNone(ps,'Windows PowerShell is required for host qualification')
        def win(path):return subprocess.check_output(['wslpath','-w',str(path)],text=True).strip()
        quote=lambda value:"'"+value.replace("'","''")+"'"
        code='& { . '+quote(win(self.project/'scripts/engineering/dispatch-wsl.ps1'))+'; $s=New-Tool019HostState; Update-Tool019Host $s ([pscustomobject]@{ms=1;event="owned_bridge_exited"}); if($s.result_class -ne "harness_failure" -or -not $s.complete){throw "Early bridge exit must fail immediately"}; Invoke-Tool019HostFixtures -FixturePath '+quote(win(self.definition_path))+' }'
        child=subprocess.run([ps,'-NoProfile','-NonInteractive','-Command',code],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=8)
        self.assertEqual(child.returncode,0,child.stderr.decode(errors='replace'))
        rows=json.loads(child.stdout.decode('utf-8-sig'))
        self.assertEqual(len(rows),len(self.definitions['host_cases']))
        actual={row['id']:row['actual'] for row in rows}
        for case in self.definitions['host_cases']:
            with self.subTest(case=case['id']):
                for key,value in case['expected'].items():
                    self.assertEqual(actual[case['id']][key],value)

    def test_fixed_operations_and_native_owned_timeout(self):
        self.assertEqual(dispatch_wsl.fixed_command('Tool019Q1',self.root)[-1],str(self.root/'fixtures'))
        with self.assertRaises(ValueError):dispatch_wsl.fixed_command('arbitrary',self.root)
        with redirect_stdout(io.StringIO()):
            result=dispatch_wsl.run_owned([sys.executable,'-c','import time;time.sleep(30)'],self.root,None,work_seconds=.12,grace_seconds=.7)
        self.assertEqual(result['classification'],'timeout')
        self.assertTrue(result['children_exited'])

    def test_native_eof_cancels_owned_child(self):
        import threading
        read_fd,write_fd=os.pipe()
        control=os.fdopen(read_fd,'rb',buffering=0)
        def close_when_spawned():
            deadline=time.monotonic()+1.5
            while time.monotonic()<deadline:
                log=self.root/'native-output.log'
                if log.exists() and b'CHILD' in log.read_bytes():break
                time.sleep(.01)
            os.close(write_fd)
        worker=threading.Thread(target=close_when_spawned);worker.start()
        code="import subprocess,sys,time; p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)'],start_new_session=True); print('CHILD',p.pid,flush=True); time.sleep(30)"
        try:
            with redirect_stdout(io.StringIO()):
                result=dispatch_wsl.run_owned([sys.executable,'-c',code],self.root,control,work_seconds=3,grace_seconds=.7)
            self.assertEqual(result['classification'],'cancelled')
            self.assertGreaterEqual(len(result['owned_pids']),2)
            self.assertTrue(result['children_exited'])
        finally:worker.join();control.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path)
    parser.add_argument("--case", choices=("baseline", "tool019-q1", "actor-ab-q1"), default="baseline")
    args = parser.parse_args()
    project = Path(__file__).resolve().parents[1]
    if args.case == "tool019-q1":
        dependency_paths = ["scripts/engineering/runtime.py", "scripts/engineering/dispatch_wsl.py", "scripts/engineering/dispatch-wsl.ps1", "scripts/engineering/scenarios/attract-manual-down.json", "scripts/test_engineering.py", "wiki/internal/tickets/evidence/tool019/fixture-definitions-20261107-01.json"]
        classes = (Tool019Q1Fixtures,)
    elif args.case == "actor-ab-q1":
        description = project / "repro/feat012-profile-signoff-20261108-02/build-runs/20261108T230414Z-keyboard-adaptive-dfbb2f299657/build.json"
        record = core.load(description)
        dependency_paths = ["scripts/engineering/runtime.py", "scripts/engineering/dispatch_wsl.py", "scripts/engineering/dispatch-wsl.ps1", "scripts/engineering/scenarios/attract-actor-ab.json", "scripts/test_engineering.py", "wiki/internal/tickets/evidence/feat012-actor-ab-01-fixtures-20261108.json",
                           str(description.relative_to(project)), "repro/engineering/20261107T135116Z-doctor-d37896a3c907/environment.json"]
        dependency_paths.append("assets/arcade/attract_actor_reference.json")
        dependency_paths += ["repro/feat012-profile-signoff-20261108-02/build-runs/20261108T230414Z-keyboard-adaptive-dfbb2f299657/" + name
                             for name in (record["rom"], "source/build/ladybug-presentation.json",
                                          "source/build/ladybug-enemy-runtime.rom", "source/build/ladybug-enemy-runtime.map",
                                          "source/build/ladybug-perimeter-reset-helper.bin", "source/build/ladybug-perimeter-reset-helper.map")]
        classes = (ActorAB01Q1Fixtures,)
    else:
        dependency_paths = []
        classes = (Fixture, ProcessTests)
    dependencies = {name: core.digest(project / name) for name in dependency_paths}
    start = time.monotonic()
    suite = unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromTestCase(case) for case in classes)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    current_dependencies = {name: core.digest(project / name) for name in dependency_paths}
    if current_dependencies != dependencies:
        raise core.HarnessError("Q1 dependency changed during qualification")
    if args.evidence:
        args.evidence.mkdir(parents=True, exist_ok=False)
        core.save_new(args.evidence / "qualification.json", {"schema": 1, "case": args.case, "dependencies": dependencies, "passed": result.wasSuccessful(), "tests": result.testsRun,
                      "skipped": len(result.skipped), "elapsed_seconds": round(time.monotonic() - start, 4),
                      "failures": [str(case) + "\n" + failure for case, failure in result.failures + result.errors],
                      "scope": "offline fixtures/fake tools only; no real game build or emulator", "test_source_sha256": core.digest(__file__), "harness": cli.checker_identity()})
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
