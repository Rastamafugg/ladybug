"""Join source, listing, map, configuration, and delivery identities."""

from __future__ import annotations

import hashlib
import re
from dataclasses import replace
from pathlib import Path
from typing import Any

from .listing_parser import parse_listing
from .map_parser import parse_map
from .model import (
    AddressIdentity,
    AddressKind,
    BasicBlock,
    CallEdge,
    CallKind,
    Evidence,
    Exclusion,
    EvidenceDimension,
    EvidenceState,
    LabelClassification,
    LabelKind,
    MemoryReference,
    ModuleReference,
    ProjectReference,
    Relocation,
    Routine,
)
from .source_parser import read_source_tree


LABEL_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_.]*)(?:\s+.*)?$", re.IGNORECASE)
CALL_RE = re.compile(
    r"^\s*(?:[A-Za-z_][A-Za-z0-9_.]*\s+)?(jsr|bsr|lbsr|jmp)\s+([A-Za-z_][A-Za-z0-9_.]*)\b",
    re.IGNORECASE,
)
BRANCH_RE = re.compile(
    r"^\s*(?:[A-Za-z_][A-Za-z0-9_.]*\s+)?(?:b(?:cc|cs|eq|ge|gt|hi|hs|le|lo|ls|lt|mi|ne|pl|ra|rn|vc|vs)|lb(?:cc|cs|eq|ge|gt|hi|hs|le|lo|ls|lt|mi|ne|pl|ra|rn|vc|vs))\s+([A-Za-z_][A-Za-z0-9_.]*)\b",
    re.IGNORECASE,
)
OPCODE_RE = re.compile(
    r"^\s*(?:[A-Za-z_][A-Za-z0-9_.]*\s+)?([A-Za-z][A-Za-z0-9]*)\b",
    re.IGNORECASE,
)
EQU_ADDRESS_RE = re.compile(
    r"^\s*([A-Za-z_][A-Za-z0-9_.]*)\s+equ\s+\$([0-9A-Fa-f]{4})\b",
    re.IGNORECASE,
)
WRITE_OPCODES = {"clr", "clra", "clrb", "sta", "stb", "std", "sts", "stu", "stx", "sty"}
READ_WRITE_OPCODES = {
    "asl", "asla", "aslb", "asr", "asra", "asrb", "com", "coma", "comb",
    "dec", "deca", "decb", "inc", "inca", "incb", "lsl", "lsla", "lslb",
    "lsr", "lsra", "lsrb", "neg", "nega", "negb", "rol", "rola", "rolb",
    "ror", "rora", "rorb",
}


def _artifact_path(root: Path, value: str | None) -> Path | None:
    if value is None:
        return None
    return (root / value).resolve()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _integer(value: Any) -> int:
    if isinstance(value, int):
        return value
    return int(str(value), 0)


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "item"


def _identity(kind: AddressKind, item: dict[str, Any]) -> AddressIdentity:
    return AddressIdentity(
        kind=kind,
        address=_integer(item["address"]),
        physical_page=_integer(item["physical_page"]) if "physical_page" in item else None,
    )


def _relocations(module_id: str, items: list[dict[str, Any]]) -> tuple[Relocation, ...]:
    records: list[Relocation] = []
    for item in items:
        staged = item.get("cartridge_staged")
        records.append(
            Relocation(
                id=str(item["id"]),
                module=module_id,
                length=_integer(item["length"]),
                assembled=_identity(AddressKind.ASSEMBLED, item["assembled"]),
                cartridge_staged=(
                    _identity(AddressKind.CARTRIDGE_STAGED, staged) if staged else None
                ),
                runtime_destination=_identity(
                    AddressKind.RUNTIME_DESTINATION, item["runtime_destination"]
                ),
            )
        )
    return tuple(records)


def _labels(source_lines: tuple) -> dict[str, tuple[str, int]]:
    labels: dict[str, tuple[str, int]] = {}
    for line in source_lines:
        code = line.text.split(";", 1)[0].rstrip()
        if not code or code[0].isspace():
            continue
        match = LABEL_RE.match(code)
        if match:
            labels.setdefault(match.group(1), (line.file, line.number))
    return labels


def _calls(module_id: str, source_lines: tuple, declared: list[dict[str, Any]]) -> tuple[CallEdge, ...]:
    extracted: list[CallEdge] = []
    current_by_file: dict[str, str] = {}
    for line in source_lines:
        code = line.text.split(";", 1)[0].rstrip()
        if code and not code[0].isspace():
            label = LABEL_RE.match(code)
            if label:
                current_by_file[line.file] = label.group(1)
        match = CALL_RE.match(code)
        if not match:
            continue
        opcode, target = match.groups()
        kind = CallKind.TAIL_JUMP if opcode.lower() == "jmp" else CallKind.DIRECT
        extracted.append(
            CallEdge(
                module=module_id,
                source_file=line.file,
                source_line=line.number,
                caller=current_by_file.get(line.file),
                target=target,
                kind=kind,
            )
        )
    for item in declared:
        extracted.append(
            CallEdge(
                module=module_id,
                source_file=str(item.get("source_file", "[configuration]")),
                source_line=int(item.get("source_line", 0)),
                caller=item.get("caller"),
                target=str(item["target"]),
                kind=CallKind(str(item["kind"])),
            )
        )
    return tuple(
        sorted(
            extracted,
            key=lambda edge: (edge.source_file, edge.source_line, edge.kind, edge.target),
        )
    )


def _branch_targets(source_lines: tuple) -> set[str]:
    targets: set[str] = set()
    for line in source_lines:
        code = line.text.split(";", 1)[0].rstrip()
        match = BRANCH_RE.match(code)
        if match:
            targets.add(match.group(1))
    return targets


def _memory_references(
    module_id: str,
    source_lines: tuple,
    structures: list[dict[str, Any]],
) -> tuple[MemoryReference, ...]:
    records: list[MemoryReference] = []
    equ_addresses: dict[str, int] = {}
    for line in source_lines:
        match = EQU_ADDRESS_RE.match(line.text.split(";", 1)[0])
        if match:
            equ_addresses[match.group(1)] = int(match.group(2), 16)
    for item in structures:
        semantic_id = item.get("semantic_id")
        symbols = {str(value) for value in item.get("symbols", [])}
        for bounds in item.get("equ_ranges", []):
            start = _integer(bounds["start"])
            end = _integer(bounds["end"])
            symbols.update(
                symbol for symbol, address in equ_addresses.items() if start <= address <= end
            )
        for line in source_lines:
            code = line.text.split(";", 1)[0]
            for symbol in sorted(symbols):
                if not re.search(rf"(?<![A-Za-z0-9_.]){re.escape(symbol)}(?![A-Za-z0-9_.])", code):
                    continue
                if re.match(rf"^\s*{re.escape(symbol)}\s+equ\b", code, re.IGNORECASE):
                    access = "definition"
                else:
                    opcode_match = OPCODE_RE.match(code)
                    opcode = opcode_match.group(1).lower() if opcode_match else ""
                    if opcode in WRITE_OPCODES:
                        access = "write"
                    elif opcode in READ_WRITE_OPCODES:
                        access = "read-write"
                    else:
                        access = "read"
                records.append(
                    MemoryReference(
                        module=module_id,
                        source_file=line.file,
                        source_line=line.number,
                        symbol=symbol,
                        access=access,
                        semantic_id=str(semantic_id) if semantic_id else None,
                    )
                )
    return tuple(
        sorted(records, key=lambda record: (record.source_file, record.source_line, record.symbol))
    )


def _evidence(items: list[dict[str, Any]], source_root: Path) -> tuple[Evidence, ...]:
    result: list[Evidence] = []
    for item in items:
        artifact = item.get("artifact")
        sha256 = item.get("sha256")
        if artifact and sha256 == "auto":
            path = (source_root / artifact).resolve()
            sha256 = _sha256(path) if path.is_file() else None
        result.append(
            Evidence(
                id=str(item["id"]),
                dimension=EvidenceDimension(str(item["dimension"])),
                state=EvidenceState(str(item["state"])),
                artifact=str(artifact) if artifact else None,
                sha256=str(sha256) if sha256 else None,
                note=item.get("note"),
            )
        )
    return tuple(result)


def build_project_reference(
    config: dict[str, Any], source_root: Path, artifact_root: Path
) -> ProjectReference:
    """Build the immutable project model from explicit inputs."""

    modules: list[ModuleReference] = []
    contract_profiles = config.get("contract_profiles", {})
    routine_catalog = config.get("routine_catalog")
    label_rules = config.get("coverage", {}).get("label_rules", [])
    memory_structures = config.get("coverage", {}).get("memory_structures", [])
    memory_structures = memory_structures + config.get("coverage", {}).get(
        "ownership_inventory", []
    )
    authored_label_names: set[str] = set()
    declared_external_symbols: list[tuple[str, str]] = []
    for item in config["modules"]:
        module_id = str(item["id"])
        source = (source_root / item["source"]).resolve()
        listing = _artifact_path(artifact_root, item.get("listing"))
        map_file = _artifact_path(artifact_root, item.get("map"))
        binary = _artifact_path(artifact_root, item.get("binary"))
        include_dirs = tuple(
            (artifact_root / value).resolve() for value in item.get("artifact_include_dirs", [""])
        ) + tuple(
            (source_root / value).resolve() for value in item.get("source_include_dirs", ["src"])
        )
        source_files, source_lines = read_source_tree(
            source, source_root, artifact_root, include_dirs
        )
        spans = parse_listing(listing, module_id, source_files) if listing else ()
        labels = _labels(source_lines)
        authored_label_names.update(labels)
        symbols = tuple(
            replace(symbol, file=labels.get(symbol.name, (None, None))[0], line=labels.get(symbol.name, (None, None))[1])
            for symbol in (parse_map(map_file, module_id) if map_file else ())
        )
        calls = _calls(module_id, source_lines, item.get("declared_calls", []))
        routine_config = {str(record["name"]): record for record in item.get("routines", [])}
        external_symbols = {str(value) for value in item.get("external_symbols", [])}
        declared_external_symbols.extend((module_id, name) for name in external_symbols)
        required: dict[str, set[str]] = {}
        for edge in calls:
            if edge.kind in (CallKind.DIRECT, CallKind.FIXED_JUMP, CallKind.INDIRECT) and edge.target not in external_symbols:
                required.setdefault(edge.target, set()).add("called")
        for name, record in routine_config.items():
            required.setdefault(name, set()).update(str(value) for value in record.get("reasons", []))
        symbol_by_name = {symbol.name: symbol for symbol in symbols}
        routines: list[Routine] = []
        for name in sorted(required):
            record = routine_config.get(name, {})
            profile = contract_profiles.get(record.get("profile"), {})
            symbol = symbol_by_name.get(name)
            location = labels.get(name, (None, None))
            semantic_id = record.get("semantic_id")
            if not semantic_id and record and routine_catalog:
                semantic_id = f"{routine_catalog}#routine-{_slug(module_id)}-{_slug(name)}"
            routines.append(
                Routine(
                    module=module_id,
                    name=name,
                    file=location[0],
                    line=location[1],
                    assembled_address=symbol.assembled_address if symbol else None,
                    semantic_id=semantic_id,
                    profile=str(record["profile"]) if record.get("profile") else None,
                    required_reasons=tuple(sorted(required[name])),
                    purpose=record.get("purpose"),
                    inputs=record.get("inputs", profile.get("inputs")),
                    outputs=record.get("outputs", profile.get("outputs")),
                    clobbers=record.get("clobbers", profile.get("clobbers")),
                    reads=record.get("reads", profile.get("reads")),
                    writes=record.get("writes", profile.get("writes")),
                    side_effects=record.get("side_effects", profile.get("side_effects")),
                    invariants=record.get("invariants", profile.get("invariants")),
                )
            )
        configured_blocks = {str(record["name"]): record for record in item.get("basic_blocks", [])}
        for name in _branch_targets(source_lines):
            if name not in required and name in labels:
                configured_blocks.setdefault(
                    name,
                    {
                        "name": name,
                        "routine": None,
                        "purpose": "Branch target inferred from current source",
                    },
                )
        basic_blocks = tuple(
            BasicBlock(
                module=module_id,
                name=name,
                routine=record.get("routine"),
                purpose=record.get("purpose"),
            )
            for name, record in sorted(configured_blocks.items())
        )
        explicit_classifications = {
            str(record["name"]): LabelClassification(
                module=module_id,
                name=str(record["name"]),
                kind=LabelKind(str(record["kind"])),
                reason=str(record["reason"]),
            )
            for record in item.get("label_classifications", [])
        }
        for symbol in symbols:
            if symbol.file is None or symbol.name in explicit_classifications:
                continue
            for rule in label_rules:
                name_pattern = rule.get("pattern")
                file_pattern = rule.get("file_pattern")
                if name_pattern and not re.fullmatch(str(name_pattern), symbol.name):
                    continue
                if file_pattern and not re.search(str(file_pattern), symbol.file):
                    continue
                explicit_classifications[symbol.name] = LabelClassification(
                    module=module_id,
                    name=symbol.name,
                    kind=LabelKind(str(rule["kind"])),
                    reason=str(rule["reason"]),
                )
                break
        artifact_hashes = []
        if listing is not None:
            artifact_hashes.append((str(item["listing"]), _sha256(listing)))
        if map_file is not None:
            artifact_hashes.append((str(item["map"]), _sha256(map_file)))
        if binary is not None:
            artifact_hashes.append((str(item["binary"]), _sha256(binary)))
        modules.append(
            ModuleReference(
                id=module_id,
                title=str(item.get("title", module_id)),
                source=str(item["source"]),
                listing=str(listing) if listing else None,
                map_file=str(map_file) if map_file else None,
                binary=str(binary) if binary else None,
                source_files=source_files,
                source_lines=source_lines,
                emitted_spans=spans,
                symbols=symbols,
                routines=tuple(routines),
                basic_blocks=basic_blocks,
                label_classifications=tuple(
                    explicit_classifications[name]
                    for name in sorted(explicit_classifications)
                ),
                memory_references=_memory_references(
                    module_id, source_lines, memory_structures
                ),
                calls=calls,
                relocations=_relocations(module_id, item.get("relocations", [])),
                artifact_hashes=tuple(artifact_hashes),
            )
        )
    unknown_externals = sorted(
        f"{module_id}:{name}"
        for module_id, name in declared_external_symbols
        if name not in authored_label_names
    )
    if unknown_externals:
        raise ValueError(
            "external call targets lack project-authored/imported labels: "
            + ", ".join(unknown_externals)
        )
    return ProjectReference(
        title=str(config["title"]),
        revision=str(config["revision"]),
        instruction_reference=config.get("instruction_reference"),
        modules=tuple(modules),
        evidence=_evidence(config.get("evidence", []), source_root),
        exclusions=tuple(
            Exclusion(path=str(item["path"]), reason=str(item["reason"]))
            for item in config.get("exclusions", [])
        ),
    )
