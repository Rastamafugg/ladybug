"""Annotation engine — turns a decoded `Instruction` into a human-readable
payload for the UI's instruction-annotation pane.

Inputs:
    inst         decoded Instruction (from decoder.decode)
    regs         current register dict (lower-case keys)
    ea_bytes     optional bytes already-fetched at the operand's effective
                 address; if absent, the annotation will say "EA = $XXXX"
                 without resolving the memory value.

Output: a plain dict (JSON-serialisable).
"""
from __future__ import annotations
from typing import Optional, Dict

from . import regions


# Store-style mnemonics that *write* to memory — we surface the
# cart-window XRoar no-op warning when the EA targets $C000-$FDFF.
_WRITE_MNEMONICS = {
    "STA", "STB", "STD", "STX", "STY", "STS", "STU",
    "CLR", "INC", "DEC", "NEG", "COM", "ASL", "LSL", "ASR", "LSR",
    "ROL", "ROR", "TST",
}


def _fmt_byte(v: int) -> str:
    return f"${v & 0xFF:02X}"


def _fmt_word(v: int) -> str:
    return f"${v & 0xFFFF:04X}"


def _fmt_signed8(v: int) -> str:
    return f"{v:+d}"


def _substitute(template: str, operand: Dict, regs: Dict) -> str:
    """Replace ${name} placeholders in `template` using operand + regs."""
    if not template:
        return ""
    out = template
    # Build a lookup of known names → formatted string.
    subs: Dict[str, str] = {}
    if "imm8" in operand:
        subs["imm8"] = f"{operand['imm8']:02X}"
    if "imm16" in operand:
        subs["imm16"] = f"{operand['imm16']:04X}"
    if "ea" in operand:
        subs["ea"] = f"{operand['ea']:04X}"
    if "target" in operand:
        subs["target"] = f"{operand['target']:04X}"
    if "offset" in operand:
        subs["offset"] = _fmt_signed8(operand["offset"])
    # TFR / EXG carry register names directly.
    if "src" in operand:
        subs["src"] = operand["src"]
    if "dst" in operand:
        subs["dest"] = operand["dst"]
    for name, formatted in subs.items():
        out = out.replace("${" + name + "}", formatted)
        out = out.replace("{" + name + "}", formatted)
    return out


def _disasm(inst, regs) -> str:
    """A compact one-line "mnemonic operand" string."""
    op = inst.operand
    m = inst.mnemonic
    if inst.operand_kind == "imm8" and "imm8" in op:
        return f"{m} #{_fmt_byte(op['imm8'])}"
    if inst.operand_kind == "imm16" and "imm16" in op:
        return f"{m} #{_fmt_word(op['imm16'])}"
    if inst.operand_kind == "direct" and "ea" in op:
        return f"{m} <{_fmt_byte(op.get('imm8', 0))}   ; @{_fmt_word(op['ea'])}"
    if inst.operand_kind == "extended" and "ea" in op:
        return f"{m} {_fmt_word(op['ea'])}"
    if inst.operand_kind in ("relative8", "relative16") and "target" in op:
        return f"{m} {_fmt_word(op['target'])}"
    if inst.operand_kind == "indexed_postbyte":
        form = op.get("form", "?")
        reg = op.get("register") or ""
        rendered = form.replace("R", reg) if reg else form
        ea = op.get("ea")
        if ea is not None:
            return f"{m} {rendered}   ; @{_fmt_word(ea)}"
        return f"{m} {rendered}"
    if inst.operand_kind == "tfr_exg_postbyte":
        return f"{m} {op.get('src','?')},{op.get('dst','?')}"
    if inst.operand_kind == "psh_pul_postbyte":
        regs_list = ",".join(op.get("regs", []))
        return f"{m} {regs_list}" if regs_list else m
    return m


def _ea_region_note(inst, ea: int, regs: Dict) -> Optional[str]:
    """Surface XRoar-quirk warnings or memory-region context for an EA."""
    if ea is None:
        return None
    region = regions.lookup(ea)
    if region is None:
        return None
    # Cart-window write — the documented XRoar 1.10 no-op.
    if inst.mnemonic in _WRITE_MNEMONICS and 0xC000 <= ea <= 0xFDFF:
        return f"⚠ write to cart-window ($C000-$FDFF) is a no-op on XRoar 1.10 — see [tooling/xroar.md]."
    return f"EA in “{region['name']}” region."


def annotate(inst, regs: Optional[Dict] = None) -> Dict:
    regs = dict(regs or {})

    if inst.unknown:
        return {
            "addr": inst.addr,
            "bytes": inst.bytes_hex,
            "disasm": "??",
            "summary": inst.summary or "(opcode not curated)",
            "effect": "",
            "cycles": inst.cycles,
            "cc": inst.cc,
            "wiki": inst.wiki,
            "operand": inst.operand,
            "notes": [inst.error] if inst.error else [],
            "unknown": True,
        }

    op = inst.operand
    disasm = _disasm(inst, regs)
    effect = _substitute(inst.effect_template, op, regs)

    notes = []
    ea = op.get("ea")
    note = _ea_region_note(inst, ea, regs) if ea is not None else None
    if note:
        notes.append(note)
    if "post_op" in op:
        notes.append(op["post_op"])
    if "pre_op" in op:
        notes.append(op["pre_op"])
    if op.get("error"):
        notes.append(op["error"])

    return {
        "addr": inst.addr,
        "bytes": inst.bytes_hex,
        "length": inst.length,
        "mnemonic": inst.mnemonic,
        "mode": inst.mode,
        "disasm": disasm,
        "summary": inst.summary,
        "effect": effect,
        "cycles": inst.cycles,
        "cc": inst.cc,
        "operand": op,
        "wiki": inst.wiki,
        "notes": notes,
        "unknown": False,
    }
