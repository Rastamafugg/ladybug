"""Render disposable source-reference HTML and its revision manifest."""

from __future__ import annotations

import html
import json
import re
from pathlib import Path

from .coverage import CoverageResult
from .links import module_page, routine_id, source_line_id, symbol_id
from .model import ModuleReference, ProjectReference


TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9]*")
MNEMONICS = {
    "abx", "adca", "adcb", "adda", "addb", "addd", "anda", "andb", "andcc",
    "asl", "asla", "aslb", "asr", "asra", "asrb", "bcc", "bcs", "beq", "bge",
    "bgt", "bhi", "bhs", "bita", "bitb", "ble", "blo", "bls", "blt", "bmi",
    "bne", "bpl", "bra", "brn", "bsr", "bvc", "bvs", "clr", "clra", "clrb",
    "cmpa", "cmpb", "cmpd", "cmps", "cmpu", "cmpx", "cmpy", "com", "coma",
    "comb", "cwai", "daa", "dec", "deca", "decb", "eora", "eorb", "exg",
    "inc", "inca", "incb", "jmp", "jsr", "lbcc", "lbcs", "lbeq", "lbge",
    "lbgt", "lbhi", "lbhs", "lble", "lblo", "lbls", "lblt", "lbmi", "lbne",
    "lbpl", "lbra", "lbrn", "lbsr", "lbvc", "lbvs", "lda", "ldb", "ldd",
    "lds", "ldu", "ldx", "ldy", "leas", "leau", "leax", "leay", "lsl",
    "lsla", "lslb", "lsr", "lsra", "lsrb", "mul", "neg", "nega", "negb",
    "nop", "ora", "orb", "orcc", "pshs", "pshu", "puls", "pulu", "rol",
    "rola", "rolb", "ror", "rora", "rorb", "rti", "rts", "sbca", "sbcb",
    "sex", "sta", "stb", "std", "sts", "stu", "stx", "sty", "suba", "subb",
    "subd", "swi", "swi2", "swi3", "sync", "tfr", "tst", "tsta", "tstb",
}
MNEMONIC_PAGES = {
    "asla": "asl", "aslb": "asl", "lsl": "asl", "lsla": "asl", "lslb": "asl",
    "asra": "asr", "asrb": "asr", "bhs": "bcc", "blo": "bcs", "clra": "clr",
    "clrb": "clr", "coma": "com", "comb": "com", "deca": "dec", "decb": "dec",
    "inca": "inc", "incb": "inc", "lbhs": "lbcc", "lblo": "lbcs", "lsra": "lsr",
    "lsrb": "lsr", "nega": "neg", "negb": "neg", "rola": "rol", "rolb": "rol",
    "rora": "ror", "rorb": "ror", "swi2": "swi", "swi3": "swi", "tsta": "tst",
    "tstb": "tst",
}


def _page(title: str, body: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{html.escape(title)}</title>
  <style>
    body {{ font-family: system-ui, sans-serif; margin: 1.5rem; color: #202124; }}
    nav a {{ margin-right: 1rem; }}
    table {{ border-collapse: collapse; width: 100%; }}
    th, td {{ border-bottom: 1px solid #ddd; padding: .25rem .4rem; text-align: left; vertical-align: top; }}
    code, pre {{ font-family: ui-monospace, SFMono-Regular, Consolas, monospace; }}
    .fail {{ color: #a40000; }} .pass {{ color: #116611; }} .muted {{ color: #666; }}
  </style>
</head>
<body>
<nav><a href="index.html">Project</a><a href="addresses.html">Addresses</a><a href="symbols.html">Symbols</a><a href="routines.html">Routines</a><a href="sources.html">Sources</a></nav>
{body}
</body>
</html>
"""


def _write(path: Path, value: str) -> None:
    path.write_text(value, encoding="utf-8")


def _instruction_link(project: ProjectReference, source_text: str) -> str | None:
    if not project.instruction_reference:
        return None
    code = source_text.split(";", 1)[0]
    tokens = TOKEN_RE.findall(code)
    if not tokens:
        return None
    # Project sources place opcodes in the indented operation field and labels
    # in column zero.  Testing position explicitly avoids consuming an opcode
    # as an optional label when its operand begins with an alphabetic token.
    index = 0 if code[:1].isspace() else 1
    if index >= len(tokens):
        return None
    mnemonic = tokens[index].lower()
    if mnemonic not in MNEMONICS:
        return None
    return project.instruction_reference.replace(
        "{mnemonic}", MNEMONIC_PAGES.get(mnemonic, mnemonic)
    )


def _module_body(project: ProjectReference, module: ModuleReference) -> str:
    spans = {(span.file, span.line): span for span in module.emitted_spans}
    symbols_by_line: dict[tuple[str, int], list[str]] = {}
    symbol_addresses_by_line: dict[tuple[str, int], list[int]] = {}
    for symbol in module.symbols:
        if symbol.file is not None and symbol.line is not None:
            symbols_by_line.setdefault((symbol.file, symbol.line), []).append(symbol.name)
            symbol_addresses_by_line.setdefault((symbol.file, symbol.line), []).append(
                symbol.assembled_address
            )
    memory_by_line: dict[tuple[str, int], list] = {}
    for reference in module.memory_references:
        memory_by_line.setdefault((reference.source_file, reference.source_line), []).append(reference)
    routines = {routine.name: routine for routine in module.routines}
    blocks = {block.name: block for block in module.basic_blocks}
    owner_starts: dict[str, list[tuple[int, int, str]]] = {}
    for symbol in module.symbols:
        if symbol.file is None or symbol.line is None:
            continue
        if symbol.name in routines:
            priority = 2
            owner = html.escape(symbol.name)
        elif symbol.name in blocks:
            priority = 1
            declared_owner = blocks[symbol.name].routine
            owner = (
                f"{html.escape(declared_owner)} / {html.escape(symbol.name)}"
                if declared_owner else f"[block] / {html.escape(symbol.name)}"
            )
        else:
            continue
        owner_starts.setdefault(symbol.file, []).append((symbol.line, priority, owner))
    for values in owner_starts.values():
        values.sort(key=lambda item: (item[0], item[1]))
    rows: list[str] = []
    for line in module.source_lines:
        span = spans.get((line.file, line.number))
        symbol_addresses = symbol_addresses_by_line.get((line.file, line.number), [])
        address = (
            f"${span.assembled_address:04X}" if span
            else f"${symbol_addresses[0]:04X}" if symbol_addresses
            else ""
        )
        data = span.data.hex().upper() if span else "non-emitting"
        line_labels = " ".join(
            f'<span id="{symbol_id(module.id, name)}">{html.escape(name)}</span>'
            for name in symbols_by_line.get((line.file, line.number), [])
        )
        instruction = _instruction_link(project, line.text)
        instruction_cell = (
            f'<a href="{html.escape(instruction, quote=True)}">instruction</a>'
            if instruction
            else ""
        )
        owner = next(
            (value for start, _priority, value in reversed(owner_starts.get(line.file, [])) if start <= line.number),
            f"[block] / {html.escape(module.id)}-entry",
        )
        memory = " ".join(
            f'<a href="{html.escape(item.semantic_id or "", quote=True)}"><code>{html.escape(item.symbol)}</code></a> ({html.escape(item.access)})'
            for item in memory_by_line.get((line.file, line.number), [])
        )
        rows.append(
            f'<tr id="{source_line_id(line.file, line.number)}">'
            f"<td><code>{html.escape(line.file)}:{line.number}</code></td>"
            f"<td><code>{address}</code></td><td><code>{data}</code></td>"
            f"<td>{line_labels}</td><td>{owner}</td><td>{memory}</td><td><code>{html.escape(line.text)}</code></td>"
            f"<td>{instruction_cell}</td></tr>"
        )
    routine_items = []
    for routine in module.routines:
        semantic = (
            f'<a href="{html.escape(routine.semantic_id, quote=True)}">contract</a>'
            if routine.contract_complete
            else '<span class="fail">missing contract</span>'
        )
        routine_items.append(
            f'<li id="{routine_id(module.id, routine.name)}"><code>{html.escape(routine.name)}</code> '
            f"{semantic}; reasons: {html.escape(', '.join(routine.required_reasons))}; "
            f"purpose: {html.escape(routine.purpose or 'missing')}</li>"
        )
    block_items = [
        f'<li><code>{html.escape(module.id)}-entry</code>: module entry, fixed jump table, '
        "or declarations before the first named control owner.</li>"
    ]
    block_items.extend(
        f'<li><code>{html.escape(block.name)}</code>: '
        f'{html.escape(block.purpose or "missing purpose")}; '
        f'enclosing routine <code>{html.escape(block.routine or "resolved by source order")}</code>.</li>'
        for block in module.basic_blocks
    )
    call_items = [
        f"<li><code>{html.escape(edge.caller or '[unknown]')}</code> &rarr; "
        f"<code>{html.escape(edge.target)}</code> ({html.escape(edge.kind.value)}; "
        f"{html.escape(edge.source_file)}:{edge.source_line})</li>"
        for edge in module.calls
    ]
    classification_items = [
        f"<li><code>{html.escape(item.name)}</code>: {html.escape(item.kind.value)}; "
        f"{html.escape(item.reason)}</li>"
        for item in module.label_classifications
    ]
    relocation_items = [
        f"<li><code>{html.escape(item.id)}</code>: assembled ${item.assembled.address:04X}; "
        f"staged {('$' + format(item.cartridge_staged.address, '04X')) if item.cartridge_staged else 'none'}; "
        f"runtime ${item.runtime_destination.address:04X}; {item.length} bytes</li>"
        for item in module.relocations
    ]
    memory_items = [
        f'<li><a href="{html.escape(item.semantic_id or "", quote=True)}"><code>{html.escape(item.symbol)}</code></a>: '
        f"{html.escape(item.access)} at "
        f'<a href="#{source_line_id(item.source_file, item.source_line)}">'
        f"{html.escape(item.source_file)}:{item.source_line}</a></li>"
        for item in module.memory_references
    ]
    return (
        f"<h1>{html.escape(module.title)}</h1>"
        f"<p>Revision <code>{html.escape(project.revision)}</code>. Source <code>{html.escape(module.source)}</code>.</p>"
        f"<h2>Routines</h2><ul>{''.join(routine_items) or '<li>None classified.</li>'}</ul>"
        f"<h2>Basic blocks</h2><ul>{''.join(block_items)}</ul>"
        f"<h2>Typed labels</h2><ul>{''.join(classification_items) or '<li>None declared.</li>'}</ul>"
        f"<h2>Calls</h2><ul>{''.join(call_items) or '<li>None extracted or declared.</li>'}</ul>"
        f"<h2>Memory references</h2><ul>{''.join(memory_items) or '<li>None declared.</li>'}</ul>"
        f"<h2>Delivery identities</h2><ul>{''.join(relocation_items) or '<li>No relocation declared.</li>'}</ul>"
        "<h2>Source lines</h2><table><thead><tr><th>Source</th><th>Address</th><th>Bytes</th>"
        f"<th>Symbols</th><th>Owner</th><th>Memory</th><th>Text</th><th>Reference</th></tr></thead><tbody>{''.join(rows)}</tbody></table>"
    )


def _manifest(project: ProjectReference, coverage: CoverageResult) -> dict:
    return {
        "schema": 1,
        "title": project.title,
        "revision": project.revision,
        "coverage": {
            "passed": coverage.passed,
            "required_routines": coverage.required_routines,
            "documented_routines": coverage.documented_routines,
            "global_labels": coverage.global_labels,
            "classified_labels": coverage.classified_labels,
            "missing_routines": list(coverage.missing_routines),
            "unclassified_labels": list(coverage.unclassified_labels),
            "duplicate_semantic_ids": list(coverage.duplicate_semantic_ids),
            "missing_evidence": list(coverage.missing_evidence),
        },
        "modules": [
            {
                "id": module.id,
                "page": module_page(module.id),
                "source_files": [
                    {"path": item.path, "sha256": item.sha256} for item in module.source_files
                ],
                "artifact_hashes": [
                    {"path": path, "sha256": sha256} for path, sha256 in module.artifact_hashes
                ],
                "counts": {
                    "source_lines": len(module.source_lines),
                    "emitted_lines": len(module.emitted_spans),
                    "symbols": len(module.symbols),
                    "routines": len(module.routines),
                    "calls": len(module.calls),
                    "memory_references": len(module.memory_references),
                    "relocations": len(module.relocations),
                },
            }
            for module in project.modules
        ],
        "evidence": [
            {
                "id": item.id,
                "dimension": item.dimension.value,
                "state": item.state.value,
                "artifact": item.artifact,
                "sha256": item.sha256,
                "note": item.note,
            }
            for item in project.evidence
        ],
        "exclusions": [
            {"path": item.path, "reason": item.reason}
            for item in project.exclusions
        ],
    }


def render_project(project: ProjectReference, coverage: CoverageResult, output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    for module in project.modules:
        _write(output / module_page(module.id), _page(module.title, _module_body(project, module)))

    module_items = "".join(
        f'<li><a href="{module_page(module.id)}">{html.escape(module.title)}</a>: '
        f"{len(module.source_lines)} source lines, {len(module.symbols)} symbols</li>"
        for module in project.modules
    )
    state = "pass" if coverage.passed else "fail"
    index_body = (
        f"<h1>{html.escape(project.title)}</h1><p>Revision <code>{html.escape(project.revision)}</code>.</p>"
        f'<p class="{state}">Coverage: {state}. {coverage.documented_routines}/{coverage.required_routines} required routines; '
        f"{coverage.classified_labels}/{coverage.global_labels} global labels classified.</p>"
        f"<h2>Modules</h2><ul>{module_items}</ul>"
    )
    _write(output / "index.html", _page(project.title, index_body))

    address_rows = []
    symbol_rows = []
    routine_rows = []
    source_rows = []
    for module in project.modules:
        page = module_page(module.id)
        for span in sorted(module.emitted_spans, key=lambda item: (item.assembled_address, item.file, item.line)):
            address_rows.append(
                f"<tr><td><code>${span.assembled_address:04X}</code></td><td>{html.escape(module.id)}</td>"
                f'<td><a href="{page}#{source_line_id(span.file, span.line)}">{html.escape(span.file)}:{span.line}</a></td>'
                f"<td><code>{span.data.hex().upper()}</code></td></tr>"
            )
        for symbol in module.symbols:
            href = f"{page}#{symbol_id(module.id, symbol.name)}" if symbol.file else page
            symbol_rows.append(
                f'<tr><td><a href="{href}"><code>{html.escape(symbol.name)}</code></a></td>'
                f"<td>{html.escape(module.id)}</td><td><code>${symbol.assembled_address:04X}</code></td></tr>"
            )
        for routine in module.routines:
            routine_rows.append(
                f'<tr id="{routine_id(module.id, routine.name)}"><td><code>{html.escape(routine.name)}</code></td>'
                f"<td>{html.escape(module.id)}</td><td>{html.escape(routine.semantic_id or 'missing')}</td></tr>"
            )
        for source_file in module.source_files:
            first = next((line for line in module.source_lines if line.file == source_file.path), None)
            href = f"{page}#{source_line_id(source_file.path, first.number)}" if first else page
            source_rows.append(
                f'<tr><td><a href="{href}"><code>{html.escape(source_file.path)}</code></a></td>'
                f"<td>{html.escape(module.id)}</td><td><code>{source_file.sha256}</code></td></tr>"
            )

    _write(output / "addresses.html", _page("Address index", f"<h1>Address index</h1><table><tbody>{''.join(address_rows)}</tbody></table>"))
    _write(output / "symbols.html", _page("Symbol index", f"<h1>Symbol index</h1><table><tbody>{''.join(symbol_rows)}</tbody></table>"))
    _write(output / "routines.html", _page("Routine index", f"<h1>Routine index</h1><table><tbody>{''.join(routine_rows)}</tbody></table>"))
    _write(output / "sources.html", _page("Source-file index", f"<h1>Source-file index</h1><table><tbody>{''.join(source_rows)}</tbody></table>"))
    (output / "manifest.json").write_text(
        json.dumps(_manifest(project, coverage), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
