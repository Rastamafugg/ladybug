"""Pure parser and bounded timeline classifier for native XRoar trace text.

This is not a collector. It reads caller-supplied finite trace text and an
independently established identity context. It starts no process and performs
no I/O. Synthetic qualification input is not product evidence.
"""

import re

RECEIPT_SHA256 = "6959493425fcca3789bee8dcb4219fb65fbd211002de72c4b92622b6be9836d4"
ROM_SHA256 = "2c8add7b35ca4b5b01c119ed9ad35b0e1bf6ba9a48c26bc43262ac0321084e9c"
PROFILE = "complete-adaptive"
MARKERS = {
    "timer": (0x07E7, "dcb0", "ldd"),
    "phase": (0x07F3, "8403", "anda"),
    "frames": (0xACBD, "de02", "ldu"),
    "publish": (0x0EAD, "b7ff9d", "sta"),
    "front": (0x0EB0, "968f", "lda"),
    "back": (0x0EB2, "d690", "ldb"),
    "phase_store": (0x0790, "97d3", "sta"),
}

_CPU = re.compile(
    r"^([0-9a-fA-F]{4})\|\s*([0-9a-fA-F]{2,16})\s+"
    r"([A-Za-z][A-Za-z0-9]*)\s+(.*?)\s+"
    r"cc=([0-9a-fA-F]{2})\s+a=([0-9a-fA-F]{2})\s+"
    r"b=([0-9a-fA-F]{2})\s+dp=([0-9a-fA-F]{2})\s+"
    r"x=([0-9a-fA-F]{4})\s+y=([0-9a-fA-F]{4})\s+"
    r"u=([0-9a-fA-F]{4})\s+s=([0-9a-fA-F]{4})"
    r"(?:\s+dt=(-?[0-9]+))?\s*$"
)
_VECTOR_HEAD = re.compile(r"^([0-9a-fA-F]{4})\| (.*)$")
_VECTORS = {0xFFF0: "[?]", 0xFFF2: "[SWI3]", 0xFFF4: "[SWI2]",
            0xFFF6: "[FIRQ]", 0xFFF8: "[IRQ]", 0xFFFA: "[SWI]",
            0xFFFC: "[NMI]", 0xFFFE: "[RESET]"}


class SetupRejected(ValueError):
    """The trace or identity context cannot support interpretation."""


def parse_line(line):
    """Parse one CPU row; native trace registers are postinstruction values."""
    match = _CPU.match(line.rstrip("\r\n"))
    if not match:
        return None
    (pc, opcode, mnemonic, operand, cc, a, b, dp, x, y, u, s, dt) = match.groups()
    regs = {"cc": int(cc, 16), "a": int(a, 16), "b": int(b, 16),
            "d": (int(a, 16) << 8) | int(b, 16), "dp": int(dp, 16),
            "x": int(x, 16), "y": int(y, 16), "u": int(u, 16), "s": int(s, 16)}
    return {"kind": "cpu", "pc": int(pc, 16), "opcode": opcode.lower(),
            "mnemonic": mnemonic.lower(), "operand": operand.strip(),
            "regs": regs, "dt": int(dt) if dt is not None else None}


def _parse_vector(line):
    """Parse native vector rows, which have event dt but no CPU registers."""
    if "  dt=" not in line:
        return None
    head, raw_dt = line.rsplit("  dt=", 1)
    match = _VECTOR_HEAD.match(head)
    if not match or not re.fullmatch(r"-?[0-9]+", raw_dt.strip()):
        return None
    pc, fields = match.groups()
    # mc6809_trace.c prints vector bytes and name in fixed 12/24-column fields.
    if len(fields) < 12:
        return None
    vector_pc = int(pc, 16)
    vector_bytes = fields[:12].strip().lower()
    vector_name = fields[12:36].strip()
    if vector_pc not in _VECTORS or vector_name != _VECTORS[vector_pc]:
        return None
    if vector_bytes and not re.fullmatch(r"(?:[0-9a-f]{2})+", vector_bytes):
        return None
    return {"kind": "vector", "pc": vector_pc, "opcode": vector_bytes,
            "name": vector_name, "dt": int(raw_dt.strip())}


def parse_trace(text):
    """Parse finite native CPU/vector events; reject timing-looking unknowns."""
    events = []
    for line in text.splitlines():
        if not line.strip():
            continue
        event = parse_line(line)
        if event is None:
            event = _parse_vector(line)
        if event is not None:
            events.append(event)
        elif "|" in line or "dt=" in line:
            raise SetupRejected("unrecognized timing trace row")
    if not events:
        raise SetupRejected("no native trace events")
    return events


def _identity_error(identity):
    """Check caller-supplied provenance; this function does not prove it."""
    if not isinstance(identity, dict):
        return "missing identity context"
    if identity.get("receipt_sha256") != RECEIPT_SHA256:
        return "receipt identity mismatch"
    if identity.get("rom_sha256") != ROM_SHA256:
        return "ROM identity mismatch"
    if identity.get("profile") != PROFILE:
        return "profile mismatch"
    if identity.get("runtime_bytes_and_mapping_proved") is not True:
        return "runtime byte/mapping proof missing"
    expected = {name: marker[1] for name, marker in MARKERS.items()}
    if identity.get("marker_bytes") != expected:
        return "executed marker bytes or mapping mismatch"
    return None


def analyze(trace_text, identity):
    """Return bounded guest timelines; pixels and host FPS remain unsupported."""
    error = _identity_error(identity)
    if error:
        return {"kind": "SETUP_REJECTED", "reason": error}
    try:
        events = parse_trace(trace_text)
    except SetupRejected as exc:
        return {"kind": "SETUP_REJECTED", "reason": str(exc)}

    cpu_count = sum(event["kind"] == "cpu" for event in events)
    if cpu_count > 32768:
        return {"kind": "SETUP_REJECTED", "reason": "32768 CPU-instruction cap exceeded"}
    # dt exists on every timing row. The first trace event's delta is invalid,
    # whether it is a vector row or a CPU instruction; ignore it completely.
    if events[0]["dt"] is None:
        return {"kind": "SETUP_REJECTED", "reason": "first event dt field absent"}

    event_tick = 0
    interval = 0
    timers = []
    active_timer = None
    frames = []
    publications = []
    pending_publication = None
    for index, event in enumerate(events):
        if index:
            if event["dt"] is None or event["dt"] < 0:
                return {"kind": "SETUP_REJECTED", "reason": "event dt missing or negative"}
            event_tick += event["dt"]
            interval += event["dt"]
        if event["kind"] != "cpu":
            continue
        pc = event["pc"]
        regs = event["regs"]
        if pending_publication is not None:
            expected_pc = 0x0EB0 if pending_publication["front"] is None else 0x0EB2
            if pc != expected_pc:
                return {"kind": "SETUP_REJECTED", "reason": "IRQ publication load order mismatch"}

        marker_name = next((name for name, marker in MARKERS.items() if marker[0] == pc), None)
        if marker_name is None:
            continue
        marker_pc, marker_opcode, marker_mnemonic = MARKERS[marker_name]
        if event["opcode"] != marker_opcode or event["mnemonic"] != marker_mnemonic:
            return {"kind": "SETUP_REJECTED", "reason": marker_name + " marker opcode mismatch"}
        if regs["dp"] != 0:
            return {"kind": "SETUP_REJECTED", "reason": marker_name + " marker DP is not zero"}

        if marker_name == "timer":
            if active_timer is not None and timers[active_timer]["phase"] is None:
                return {"kind": "SETUP_REJECTED", "reason": "timer sample lacks paired phase"}
            timers.append({"t": regs["d"], "phase": None,
                           "event_tick": event_tick, "spacing": interval})
            active_timer = len(timers) - 1
            interval = 0
        elif marker_name == "phase":
            if active_timer is None or timers[active_timer]["phase"] is not None:
                return {"kind": "SETUP_REJECTED", "reason": "unpaired or duplicate phase sample"}
            if regs["a"] > 3:
                return {"kind": "SETUP_REJECTED", "reason": "phase result outside 0..3"}
            timers[active_timer]["phase"] = regs["a"]  # preserve observed value; do not mask it
        elif marker_name == "frames":
            frames.append({"value": regs["u"], "event_tick": event_tick})
        elif marker_name == "publish":
            if pending_publication is not None:
                return {"kind": "SETUP_REJECTED", "reason": "nested IRQ publication"}
            pending_publication = {"ordinal": len(publications) + 1,
                                   "event_tick": event_tick, "voff1_a": regs["a"],
                                   "front": None, "back": None}
        elif marker_name == "front":
            if pending_publication is None:
                return {"kind": "SETUP_REJECTED", "reason": "orphan FRONT load"}
            pending_publication["front"] = regs["a"]
        elif marker_name == "back":
            if pending_publication is None or pending_publication["front"] is None:
                return {"kind": "SETUP_REJECTED", "reason": "orphan BACK load"}
            pending_publication["back"] = regs["b"]
            publications.append(pending_publication)
            pending_publication = None
        # phase_store confirms an executed write only; it does not reveal the
        # resulting memory value beyond the source-defined A operand.

    if pending_publication is not None:
        return {"kind": "SETUP_REJECTED", "reason": "incomplete IRQ publication record"}
    if len(timers) < 33:
        return {"kind": "SETUP_REJECTED", "reason": "missing timer coverage"}
    cycle = timers[:33]
    values = [sample["t"] for sample in cycle]
    if values[0] < 6 or values != list(range(values[0], values[0] + 33)):
        return {"kind": "SETUP_REJECTED", "reason": "timer samples not 33 consecutive values"}
    if values[-1] - values[0] != 32:
        return {"kind": "SETUP_REJECTED", "reason": "timer coverage does not span 32 advances"}
    if any(sample["phase"] is None for sample in cycle):
        return {"kind": "SETUP_REJECTED", "reason": "missing phase coverage"}
    if len(frames) < 2 or frames[0]["event_tick"] > cycle[0]["event_tick"] or frames[-1]["event_tick"] < cycle[-1]["event_tick"]:
        return {"kind": "SETUP_REJECTED", "reason": "FRAMES samples do not cover timer cycle"}
    if not publications:
        return {"kind": "SETUP_REJECTED", "reason": "missing IRQ publication coverage"}

    observed = [sample["phase"] for sample in cycle]
    expected = [((t - 6) >> 3) & 3 for t in values]
    phase_mismatch = observed != expected
    spacings = [sample["spacing"] for sample in cycle[1:]]
    spacing_unequal = len(set(spacings)) > 1
    field_steps = [((b["value"] - a["value"]) & 0xFFFF)
                   for a, b in zip(frames, frames[1:])]
    summary = {"timers": values, "phase": observed,
               "subphase": [(t - 6) & 7 for t in values],
               "timer_event_ticks": [sample["event_tick"] for sample in cycle],
               "timer_spacing_event_ticks": spacings,
               "frames": [sample["value"] for sample in frames],
               "frame_event_ticks": [sample["event_tick"] for sample in frames],
               "frame_steps": field_steps,
               "publications": publications,
               "phase_mismatch": phase_mismatch,
               "unequal_observed_spacing": spacing_unequal,
               "display_replay": "UNSUPPORTED_WITHOUT_PIXELS",
               "host_fps": "UNSUPPORTED"}
    if phase_mismatch:
        summary["kind"] = "PHASE_ANOMALY"
    elif spacing_unequal:
        summary["kind"] = "UNEQUAL_OBSERVED_SPACING"
    else:
        summary["kind"] = "GUEST_TIMER_PHASE_CONSISTENT"
    return summary
