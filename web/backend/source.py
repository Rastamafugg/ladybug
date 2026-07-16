"""Parse the lwasm .lst into structured lines for the source pane.

Each .lst line is shaped like:

    "C02A 8EC000           (path):00102               ldx     #CART_BASE"

with the address in the leftmost column (blank on non-emitting lines), an
optional byte column, then `(path):lineno  source_text`. We pull out the
address (if any) and the source text — bytes are ignored for now.
"""
from __future__ import annotations
import re
from pathlib import Path


_RE_LST_LINE = re.compile(
    r"^([0-9A-Fa-f]{4,})?\s+\S*\s*\([^)]+\):(\d+)\s?(.*)$"
)

# Directives whose address is data, not an instruction — an exec breakpoint
# there never fires. (EQU lines never reach this check: their value prints in
# the byte column, so they parse with addr=None.)
_DATA_DIRECTIVES = frozenset({
    "fcb", "fdb", "fqb", "fcc", "fcn", "fcs", "rmb", "zmb", "fill",
})


def _is_data_line(text: str) -> bool:
    """True when the source text's mnemonic field is a data directive.

    The mnemonic is the first token when the line starts with whitespace,
    or the second when a label leads. Checking both is safe: no 6809
    instruction shares a name with these directives.
    """
    tokens = text.split(";", 1)[0].split()
    return any(t.lower() in _DATA_DIRECTIVES for t in tokens[:2])


def parse_lst(path: Path) -> list:
    """Return list of dicts {addr, line_no, text, exec}.

    `addr` is None on non-emitting lines. `exec` is True only for lines whose
    address holds an instruction — data lines (fcb/fdb/...) keep their addr
    for memory navigation but must not accept exec breakpoints.
    """
    out: list = []
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for raw in f:
            line = raw.rstrip("\n")
            m = _RE_LST_LINE.match(line)
            if not m:
                continue
            addr_hex, line_no, text = m.group(1), m.group(2), m.group(3)
            addr = int(addr_hex, 16) if addr_hex else None
            out.append({
                "addr": addr,
                "line_no": int(line_no),
                "text": text,
                "exec": addr is not None and not _is_data_line(text),
            })
    # A label-only line carries the address of whatever follows it (its own
    # text has no mnemonic, so the loop above marked it exec). Inherit exec
    # from the next addressed line when it shares the address: labels before
    # code stay breakpointable, labels before data tables don't.
    nxt = None
    for row in reversed(out):
        if row["addr"] is None:
            continue
        if nxt is not None and nxt["addr"] == row["addr"]:
            row["exec"] = nxt["exec"]
        nxt = row
    return out
