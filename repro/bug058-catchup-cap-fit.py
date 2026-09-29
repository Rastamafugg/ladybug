"""Assemble an isolated two-step scheduler fit without changing the ROM tree."""
import argparse
import hashlib
import subprocess
from pathlib import Path


def once(source: str, old: str, new: str) -> str:
    assert source.count(old) == 1, old
    return source.replace(old, new)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("candidate", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    root = args.candidate.resolve()
    build = root / "build"
    original = (build / "ladybug-adaptive-banked.bin").read_bytes()
    assert len(original) == 690, "baseline helper changed"
    source = (build / "ladybug-adaptive-banked.s").read_text()
    source = once(source, "        lda #4\n        sta AD_BATCH", "        lda #2\n        sta AD_BATCH")
    source = once(source, "        tst AD_BARRIER\n        bne ab_ready\n        lda PRES_MODE", "        tst AD_BARRIER\n        bne ab_rebase\n        lda PRES_MODE")
    source = once(source, "        dec AD_BATCH\n        bne ab_step\nab_ready", "        dec AD_BATCH\n        bne ab_step\nab_rebase\n        clr AD_DEBT\n        clr AD_DEBT+1\nab_ready")
    source = once(source, "ab_transition\n        lda #1\n        sta AD_BARRIER\n        bra ab_ready", "ab_transition\n        lda #1\n        sta AD_BARRIER\n        bra ab_rebase")
    out = args.output.resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    asm = out.with_suffix(".s")
    asm.write_text(source)
    subprocess.run([
        "lwasm", "-9", "--format=raw", "-DADAPTIVE_RENDERING=1",
        "-I", str(build), "-I", str(root / "src"),
        "--output=" + str(out), "--map=" + str(out.with_suffix(".map")),
        str(asm),
    ], check=True)
    fitted = out.read_bytes()
    assert len(fitted) == 696 and len(fitted) <= 698
    print(f"baseline=690/698 fitted={len(fitted)}/698 sha256={hashlib.sha256(fitted).hexdigest()}")


if __name__ == "__main__":
    main()
