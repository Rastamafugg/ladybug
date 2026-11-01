#!/usr/bin/env python3
"""Focused controls for candidate_manifest.py."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest

from candidate_manifest import ManifestError, verify_manifest, write_manifest


SCRIPT = Path(__file__).with_name("candidate_manifest.py").resolve()


class CandidateManifestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        (self.root / "nested").mkdir()
        (self.root / "alpha.txt").write_bytes(b"alpha\n")
        (self.root / "nested" / "beta.txt").write_bytes(b"beta\x00bytes")
        (self.root / "paths.json").write_text(
            json.dumps(["nested/beta.txt", "alpha.txt"], ensure_ascii=False),
            encoding="utf-8",
        )

    def write(self) -> bytes:
        write_manifest(self.root, "control.sha256", "paths.json")
        return (self.root / "control.sha256").read_bytes()

    def test_writer_is_sorted_deterministic_and_lf_only(self):
        first = self.write()
        alpha_hash = hashlib.sha256(b"alpha\n").hexdigest()
        beta_hash = hashlib.sha256(b"beta\x00bytes").hexdigest()
        self.assertEqual(
            first,
            f"{alpha_hash}  alpha.txt\n{beta_hash}  nested/beta.txt\n".encode("ascii"),
        )
        self.assertNotIn(b"\r", first)
        self.assertEqual(write_manifest(self.root, "control.sha256", "paths.json"), 2)
        self.assertEqual((self.root / "control.sha256").read_bytes(), first)

    def test_python_verifier_and_gnu_sha256sum_accept_valid_output(self):
        self.write()
        self.assertEqual(verify_manifest(self.root, "control.sha256"), 2)
        sha256sum = shutil.which("sha256sum")
        self.assertIsNotNone(sha256sum, "sha256sum must be available in the WSL test environment")
        result = subprocess.run(
            [sha256sum, "-c", "control.sha256"],
            cwd=self.root, capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_crlf_is_rejected_and_and_chain_skips_sentinel(self):
        manifest = self.write().replace(b"\n", b"\r\n")
        (self.root / "control-crlf.sha256").write_bytes(manifest)
        with self.assertRaisesRegex(ManifestError, "CR bytes"):
            verify_manifest(self.root, "control-crlf.sha256")

        sentinel = self.root / "build-was-started.txt"
        command = "{} {} verify --root {} --manifest {} && {} -c {}".format(
            shlex.quote(sys.executable),
            shlex.quote(str(SCRIPT)),
            shlex.quote(str(self.root)),
            shlex.quote("control-crlf.sha256"),
            shlex.quote(sys.executable),
            shlex.quote("from pathlib import Path; Path('build-was-started.txt').write_text('started')"),
        )
        result = subprocess.run(
            ["bash", "-c", command], cwd=self.root,
            capture_output=True, text=True, check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(sentinel.exists())

    def test_verifier_rejects_duplicate_malformed_unsorted_and_missing_records(self):
        valid = self.write()
        lines = valid.splitlines(keepends=True)
        with self.subTest("duplicate"):
            (self.root / "bad.sha256").write_bytes(valid + lines[0])
            with self.assertRaisesRegex(ManifestError, "duplicate"):
                verify_manifest(self.root, "bad.sha256")
        with self.subTest("malformed digest"):
            (self.root / "bad.sha256").write_bytes(b"z" * 64 + b"  alpha.txt\n")
            with self.assertRaisesRegex(ManifestError, "invalid lowercase SHA-256"):
                verify_manifest(self.root, "bad.sha256")
        with self.subTest("unsorted"):
            (self.root / "bad.sha256").write_bytes(lines[1] + lines[0])
            with self.assertRaisesRegex(ManifestError, "not sorted"):
                verify_manifest(self.root, "bad.sha256")
        with self.subTest("missing file"):
            (self.root / "bad.sha256").write_bytes(
                f"{hashlib.sha256(b'x').hexdigest()}  absent.bin\n".encode("ascii")
            )
            with self.assertRaisesRegex(ManifestError, "unavailable"):
                verify_manifest(self.root, "bad.sha256")

    def test_verifier_rejects_hash_mismatch(self):
        self.write()
        (self.root / "alpha.txt").write_bytes(b"changed\n")
        with self.assertRaisesRegex(ManifestError, "SHA-256 mismatch"):
            verify_manifest(self.root, "control.sha256")

    def test_verifier_rejects_unsafe_paths(self):
        digest = hashlib.sha256(b"unused").hexdigest()
        cases = [
            ("../outside.txt", "normalized package-relative"),
            ("/outside.txt", "absolute"),
            ("alpha\\\\beta.txt", "backslash"),
        ]
        for index, (name, message) in enumerate(cases):
            with self.subTest(name=name):
                manifest_name = f"unsafe-{index}.sha256"
                (self.root / manifest_name).write_text(
                    f"{digest}  {name}\n", encoding="utf-8",
                )
                with self.assertRaisesRegex(ManifestError, message):
                    verify_manifest(self.root, manifest_name)

    def test_verifier_rejects_manifest_listing_itself(self):
        (self.root / "self.sha256").write_bytes(b"0" * 64 + b"  self.sha256\n")
        with self.assertRaisesRegex(ManifestError, "must not list itself"):
            verify_manifest(self.root, "self.sha256")

    def test_writer_rejects_duplicate_and_unsafe_file_paths(self):
        cases = [
            (["alpha.txt", "alpha.txt"], "duplicate"),
            (["../outside.txt"], "normalized package-relative"),
            ([str(self.root / "alpha.txt")], "absolute"),
            (["alpha\\\\beta.txt"], "backslash"),
            (["alpha\nname.txt"], "control character"),
        ]
        for paths, message in cases:
            with self.subTest(paths=paths):
                (self.root / "paths.json").write_text(json.dumps(paths), encoding="utf-8")
                with self.assertRaisesRegex(ManifestError, message):
                    write_manifest(self.root, "control.sha256", "paths.json")
                self.assertFalse((self.root / "control.sha256").exists())

    @unittest.skipUnless(os.name == "posix", "symlink escape control requires POSIX/WSL")
    def test_writer_rejects_symlink_escape(self):
        outside_temp = tempfile.TemporaryDirectory()
        self.addCleanup(outside_temp.cleanup)
        outside = Path(outside_temp.name) / "outside.txt"
        outside.write_text("outside", encoding="utf-8")
        (self.root / "escape.txt").symlink_to(outside)
        (self.root / "paths.json").write_text(json.dumps(["escape.txt"]), encoding="utf-8")
        with self.assertRaisesRegex(ManifestError, "escapes the package root"):
            write_manifest(self.root, "control.sha256", "paths.json")
        digest = hashlib.sha256(b"outside").hexdigest()
        (self.root / "escape.sha256").write_text(
            f"{digest}  escape.txt\n", encoding="ascii",
        )
        with self.assertRaisesRegex(ManifestError, "escapes the package root"):
            verify_manifest(self.root, "escape.sha256")


if __name__ == "__main__":
    unittest.main(verbosity=2)
