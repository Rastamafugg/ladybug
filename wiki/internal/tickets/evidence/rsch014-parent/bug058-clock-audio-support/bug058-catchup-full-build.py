"""Build an isolated candidate from a temporary scheduler edit, then restore source."""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path


def once(source: str, old: str, new: str) -> str:
    assert source.count(old) == 1, old
    return source.replace(old, new)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("candidate", type=Path)
    parser.add_argument("receipt", type=Path)
    parser.add_argument("--retain-rom", type=Path)
    parser.add_argument("--retain-build", type=Path)
    args = parser.parse_args()
    root = args.candidate.resolve()
    source = root / "src/adaptive_runtime.s"
    build = root / "build"
    original = source.read_bytes()
    text = original.decode("utf-8").replace("\r\n", "\n")
    text = once(text, "        lda #4\n        sta AD_BATCH", "        lda #2\n        sta AD_BATCH")
    text = once(text, "        tst AD_BARRIER\n        bne ab_ready\n        lda PRES_MODE", "        tst AD_BARRIER\n        bne ab_rebase\n        lda PRES_MODE")
    text = once(text, "        dec AD_BATCH\n        bne ab_step\nab_ready", "        dec AD_BATCH\n        bne ab_step\nab_rebase\n        clr AD_DEBT\n        clr AD_DEBT+1\nab_ready")
    text = once(text, "ab_transition\n        lda #1\n        sta AD_BARRIER\n        bra ab_ready", "ab_transition\n        lda #1\n        sta AD_BARRIER\n        bra ab_rebase")
    env = os.environ.copy()
    env["LADYBUG_ADAPTIVE"] = "1"
    env.pop("LADYBUG_BUILD_DIR", None)
    with tempfile.TemporaryDirectory(prefix="bug058-catchup-build-") as temporary:
        saved = Path(temporary) / "build"
        shutil.copytree(build, saved)
        try:
            source.write_bytes(text.encode("utf-8"))
            subprocess.run(["bash", "scripts/build.sh", "build"], cwd=root, env=env, check=True)
            layout = json.loads((build / "ladybug-sparse-layout.json").read_text())
            report = {
                "status": "full-build-pass",
                "baseline_rom_sha256": hashlib.sha256((saved / "ladybug.rom").read_bytes()).hexdigest(),
                "fitted_rom_sha256": hashlib.sha256((build / "ladybug.rom").read_bytes()).hexdigest(),
                "banked_helper_bytes": (build / "ladybug-adaptive-banked.bin").stat().st_size,
                "banked_helper_limit": 698,
                "gmc_source_spare_bytes": layout["gmc"]["spare_bytes"],
                "cartridge_bytes": (build / "ladybug.rom").stat().st_size,
                "source_reference_generated": (build / "source-reference/ownership.json").is_file(),
            }
            if args.retain_rom:
                retained = args.retain_rom.resolve()
                retained.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(build / "ladybug.rom", retained)
                assert hashlib.sha256(retained.read_bytes()).hexdigest() == report["fitted_rom_sha256"]
                report["retained_rom"] = str(retained)
            if args.retain_build:
                retained_build = args.retain_build.resolve()
                shutil.copytree(build, retained_build, dirs_exist_ok=True)
                report["retained_build"] = str(retained_build)
            args.receipt.write_text(json.dumps(report, indent=2) + "\n")
        finally:
            source.write_bytes(original)
            shutil.copytree(saved, build, dirs_exist_ok=True)
            assert source.read_bytes() == original
            assert (build / "ladybug.rom").read_bytes() == (saved / "ladybug.rom").read_bytes()


if __name__ == "__main__":
    main()
