"""6809 instruction decoder.

Given the bytes at PC and the current CPU state, produces a structured
Instruction record: opcode info + addressing-mode operand + (where computable)
resolved effective address. Stays purely informational — never executes.

The decoder is data-driven from `opcode_table.py` (which loads the curated
JSON dictionaries). Unknown opcodes return a stub Instruction with
`unknown=True` so the annotation engine can render a polite "not yet curated"
message rather than crash.
"""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Optional, Dict

from . import opcode_table


@dataclass
class Instruction:
    addr: int                     # PC at which the instruction starts
    bytes_hex: str                # actual bytes consumed (uppercase, e.g. "8E1FFE")
    length: int                   # total bytes consumed (incl. prefix + postbyte + extras)
    mnemonic: str                 # "LDA", "BNE", … or "??" for unknown
    mode: str                     # addressing mode label
    operand_kind: str             # imm8 | imm16 | direct | extended | indexed_postbyte | …
    operand: Dict                 # mode-specific resolved operand details
    cycles: object                # int or {"min":int,"max":int,"note":str}
    cc: Dict                      # CC-effects map
    summary: str
    effect_template: str
    wiki: Optional[str]
    unknown: bool = False
    error: Optional[str] = None


def _sign8(v: int) -> int:
    return v - 0x100 if v & 0x80 else v


def _sign16(v: int) -> int:
    return v - 0x10000 if v & 0x8000 else v


def _u16(hi: int, lo: int) -> int:
    return ((hi & 0xFF) << 8) | (lo & 0xFF)


def _match_postbyte(pb: int):
    """Return the matching indexed-postbyte entry or None."""
    for e in opcode_table.indexed_postbyte_entries():
        mask = int(e["mask"], 0)
        val = int(e["value"], 0)
        if (pb & mask) == val:
            return e
    return None


def _indexed_register(pb: int) -> str:
    return opcode_table.register_codes()[(pb >> 5) & 0x3]


def _resolve_indexed(pb: int, extras: bytes, regs: Dict) -> Dict:
    """Resolve an indexed-mode effective address against current regs.

    `regs` is a dict like {'x': 0xC10A, 'pc': 0x..., …}. Returns a dict with
    at minimum `form`, `register`, `extra_bytes`, `indirect`, and `ea` when
    computable.
    """
    entry = _match_postbyte(pb)
    if entry is None:
        return {"form": "??", "register": None, "extra_bytes": 0,
                "indirect": False, "ea": None,
                "error": f"unknown indexed postbyte ${pb:02X}"}
    form = entry["form"]
    reg = _indexed_register(pb)
    extra = int(entry["extra_bytes"])
    indirect = bool(entry["indirect"])
    out: Dict = {
        "form": form,
        "postbyte": f"${pb:02X}",
        "register": reg,
        "extra_bytes": extra,
        "indirect": indirect,
    }
    rv = (regs or {}).get(reg.lower()) if reg else None

    # Compute EA per form. We don't apply pre/post inc/dec to register state
    # (that's what execution does — we just describe what *will* happen).
    ea = None
    if form == ",R" and rv is not None:
        ea = rv & 0xFFFF
    elif form == "[,R]" and rv is not None:
        out["ea_via"] = rv & 0xFFFF  # EA is M:M+1(rv), can't deref here
    elif form == ",R+" and rv is not None:
        ea = rv & 0xFFFF
        out["post_op"] = f"{reg} ← {reg} + 1"
    elif form == ",R++" and rv is not None:
        ea = rv & 0xFFFF
        out["post_op"] = f"{reg} ← {reg} + 2"
    elif form == "[,R++]" and rv is not None:
        out["ea_via"] = rv & 0xFFFF
        out["post_op"] = f"{reg} ← {reg} + 2"
    elif form == ",-R" and rv is not None:
        ea = (rv - 1) & 0xFFFF
        out["pre_op"] = f"{reg} ← {reg} - 1"
    elif form == ",--R" and rv is not None:
        ea = (rv - 2) & 0xFFFF
        out["pre_op"] = f"{reg} ← {reg} - 2"
    elif form == "[,--R]" and rv is not None:
        out["ea_via"] = (rv - 2) & 0xFFFF
        out["pre_op"] = f"{reg} ← {reg} - 2"
    elif form == "n5,R":
        off = pb & 0x1F
        if off & 0x10:
            off -= 0x20
        out["offset"] = off
        if rv is not None:
            ea = (rv + off) & 0xFFFF
    elif form in ("n8,R", "[n8,R]"):
        off = _sign8(extras[0]) if extras else 0
        out["offset"] = off
        if rv is not None:
            base = (rv + off) & 0xFFFF
            if indirect:
                out["ea_via"] = base
            else:
                ea = base
    elif form in ("n16,R", "[n16,R]"):
        off = _sign16(_u16(extras[0], extras[1])) if len(extras) >= 2 else 0
        out["offset"] = off
        if rv is not None:
            base = (rv + off) & 0xFFFF
            if indirect:
                out["ea_via"] = base
            else:
                ea = base
    elif form in ("A,R", "[A,R]"):
        a = (regs or {}).get("a")
        if a is not None and rv is not None:
            base = (rv + _sign8(a)) & 0xFFFF
            (out.__setitem__("ea_via", base) if indirect else None) or (ea := base if not indirect else ea)
            if not indirect:
                ea = base
            else:
                out["ea_via"] = base
    elif form in ("B,R", "[B,R]"):
        b = (regs or {}).get("b")
        if b is not None and rv is not None:
            base = (rv + _sign8(b)) & 0xFFFF
            if indirect:
                out["ea_via"] = base
            else:
                ea = base
    elif form in ("D,R", "[D,R]"):
        a = (regs or {}).get("a"); bb = (regs or {}).get("b")
        if a is not None and bb is not None and rv is not None:
            d = _sign16(((a & 0xFF) << 8) | (bb & 0xFF))
            base = (rv + d) & 0xFFFF
            if indirect:
                out["ea_via"] = base
            else:
                ea = base
    elif form in ("n8,PCR", "[n8,PCR]"):
        # PC value used by the CPU is the address AFTER the full instruction.
        # Caller-supplied 'pc_after_insn' lives in regs as 'pc_after_insn'.
        pc_after = regs.get("pc_after_insn") if regs else None
        off = _sign8(extras[0]) if extras else 0
        out["offset"] = off
        if pc_after is not None:
            base = (pc_after + off) & 0xFFFF
            if indirect:
                out["ea_via"] = base
            else:
                ea = base
    elif form in ("n16,PCR", "[n16,PCR]"):
        pc_after = regs.get("pc_after_insn") if regs else None
        off = _sign16(_u16(extras[0], extras[1])) if len(extras) >= 2 else 0
        out["offset"] = off
        if pc_after is not None:
            base = (pc_after + off) & 0xFFFF
            if indirect:
                out["ea_via"] = base
            else:
                ea = base
    elif form == "[n16]":
        if len(extras) >= 2:
            out["ea_via"] = _u16(extras[0], extras[1])

    if ea is not None:
        out["ea"] = ea
    return out


def decode(addr: int, blob: bytes, regs: Optional[Dict] = None) -> Instruction:
    """Decode the instruction at `addr` given `blob` (>=1 byte at addr) and
    current `regs` (lower-case keys: pc, a, b, x, y, u, s, dp, cc).
    """
    regs = dict(regs or {})

    if not blob:
        return Instruction(
            addr=addr, bytes_hex="", length=0, mnemonic="??", mode="?",
            operand_kind="?", operand={}, cycles=0, cc={}, summary="",
            effect_template="", wiki=None, unknown=True, error="no bytes",
        )

    cursor = 0
    page = None
    b0 = blob[cursor]; cursor += 1

    entry = None
    if b0 == 0x10 and len(blob) > cursor:
        page = "page2"
        b1 = blob[cursor]; cursor += 1
        entry = opcode_table.lookup_page2(b1)
    elif b0 == 0x11 and len(blob) > cursor:
        page = "page3"
        b1 = blob[cursor]; cursor += 1
        entry = opcode_table.lookup_page3(b1)
    else:
        entry = opcode_table.lookup_primary(b0)

    if entry is None:
        return Instruction(
            addr=addr, bytes_hex=blob[:cursor].hex().upper(),
            length=cursor, mnemonic="??", mode="?", operand_kind="?",
            operand={}, cycles=0, cc={}, summary="(opcode not curated)",
            effect_template="", wiki=None, unknown=True,
            error=f"no entry for {'page-2 ' if page=='page2' else 'page-3 ' if page=='page3' else ''}${b0:02X}{(blob[cursor-1] if page else 0):02X}" if page else f"no entry for ${b0:02X}",
        )

    kind = entry.get("operand_kind", "inherent")
    operand: Dict = {}
    length_field = entry.get("length", 1)

    if kind == "imm8":
        if cursor < len(blob):
            v = blob[cursor]; cursor += 1
            operand = {"imm8": v}
        total = length_field if isinstance(length_field, int) else cursor

    elif kind == "imm16":
        if cursor + 1 < len(blob):
            v = _u16(blob[cursor], blob[cursor+1]); cursor += 2
            operand = {"imm16": v}
        total = length_field if isinstance(length_field, int) else cursor

    elif kind == "direct":
        if cursor < len(blob):
            off = blob[cursor]; cursor += 1
            dp = regs.get("dp", 0) & 0xFF
            operand = {"imm8": off, "ea": (dp << 8) | off}
        total = length_field if isinstance(length_field, int) else cursor

    elif kind == "extended":
        if cursor + 1 < len(blob):
            v = _u16(blob[cursor], blob[cursor+1]); cursor += 2
            operand = {"imm16": v, "ea": v}
        total = length_field if isinstance(length_field, int) else cursor

    elif kind == "relative8":
        if cursor < len(blob):
            off = _sign8(blob[cursor]); cursor += 1
            # PC at branch time points past the instruction.
            target = (addr + cursor + off) & 0xFFFF
            operand = {"offset": off, "target": target}
        total = length_field if isinstance(length_field, int) else cursor

    elif kind == "relative16":
        if cursor + 1 < len(blob):
            off = _sign16(_u16(blob[cursor], blob[cursor+1])); cursor += 2
            target = (addr + cursor + off) & 0xFFFF
            operand = {"offset": off, "target": target}
        total = length_field if isinstance(length_field, int) else cursor

    elif kind == "indexed_postbyte":
        if cursor < len(blob):
            pb = blob[cursor]; cursor += 1
            # We need to know how many extras the postbyte will consume to
            # compute pc_after_insn correctly for PCR forms. Match first.
            pb_entry = _match_postbyte(pb)
            extra_n = int(pb_entry["extra_bytes"]) if pb_entry else 0
            extras = bytes(blob[cursor:cursor + extra_n])
            cursor += extra_n
            # PCR forms reference the PC after the full instruction.
            regs_with_pc_after = dict(regs)
            regs_with_pc_after["pc_after_insn"] = (addr + cursor) & 0xFFFF
            operand = _resolve_indexed(pb, extras, regs_with_pc_after)
        total = cursor  # variable length

    elif kind == "tfr_exg_postbyte":
        if cursor < len(blob):
            pb = blob[cursor]; cursor += 1
            operand = {"postbyte": pb,
                       "src": _tfr_reg(pb >> 4),
                       "dst": _tfr_reg(pb & 0x0F)}
        total = length_field if isinstance(length_field, int) else cursor

    elif kind == "psh_pul_postbyte":
        if cursor < len(blob):
            pb = blob[cursor]; cursor += 1
            operand = {"postbyte": pb, "regs": _psh_regs(pb)}
        total = length_field if isinstance(length_field, int) else cursor

    elif kind == "inherent":
        total = length_field if isinstance(length_field, int) else cursor

    else:
        total = length_field if isinstance(length_field, int) else cursor
        operand = {"error": f"unhandled operand_kind {kind}"}

    bytes_consumed = blob[:total]
    return Instruction(
        addr=addr,
        bytes_hex=bytes_consumed.hex().upper(),
        length=total,
        mnemonic=entry["mnemonic"],
        mode=entry.get("mode", "?"),
        operand_kind=kind,
        operand=operand,
        cycles=entry.get("cycles", 0),
        cc=entry.get("cc", {}),
        summary=entry.get("summary", ""),
        effect_template=entry.get("effect_template", ""),
        wiki=entry.get("wiki"),
    )


_TFR_REGS = {
    0x0: "D", 0x1: "X", 0x2: "Y", 0x3: "U", 0x4: "S", 0x5: "PC",
    0x8: "A", 0x9: "B", 0xA: "CC", 0xB: "DP",
}


def _tfr_reg(code: int) -> str:
    return _TFR_REGS.get(code & 0xF, f"?(${code:X})")


# Push/pull postbyte bit positions: high → low = PC, U, Y, X, DP, B, A, CC
_PSH_BITS = ["PC", "U", "Y", "X", "DP", "B", "A", "CC"]


def _psh_regs(pb: int):
    return [name for i, name in enumerate(_PSH_BITS) if pb & (0x80 >> i)]
