"""Immutable records shared by the source-reference pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class CallKind(str, Enum):
    DIRECT = "direct"
    TAIL_JUMP = "tail-jump"
    FIXED_JUMP = "fixed-jump"
    INDIRECT = "indirect"


class AddressKind(str, Enum):
    ASSEMBLED = "assembled"
    CARTRIDGE_STAGED = "cartridge-staged"
    RUNTIME_DESTINATION = "runtime-destination"


class EvidenceDimension(str, Enum):
    STRUCTURAL = "structural"
    REPRESENTATION = "representation"
    DELIVERY = "delivery"
    RUNTIME_REACHABILITY = "runtime-reachability"
    VISIBLE_OUTPUT = "visible-output"
    TIMING = "timing"


class EvidenceState(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    MISSING = "missing"
    STALE = "stale"


class LabelKind(str, Enum):
    DATA = "data"
    BOUNDARY = "boundary"
    CONSTANT = "constant"
    GENERATED = "generated"


@dataclass(frozen=True)
class SourceFile:
    path: str
    absolute_path: str
    sha256: str


@dataclass(frozen=True)
class SourceLine:
    file: str
    number: int
    text: str


@dataclass(frozen=True)
class EmittedSpan:
    module: str
    file: str
    line: int
    assembled_address: int
    data: bytes


@dataclass(frozen=True)
class Symbol:
    module: str
    name: str
    assembled_address: int
    file: str | None = None
    line: int | None = None


@dataclass(frozen=True)
class Routine:
    module: str
    name: str
    file: str | None
    line: int | None
    assembled_address: int | None
    semantic_id: str | None
    profile: str | None
    required_reasons: tuple[str, ...]
    purpose: str | None
    inputs: str | None
    outputs: str | None
    clobbers: str | None
    reads: str | None
    writes: str | None
    side_effects: str | None
    invariants: str | None

    @property
    def contract_complete(self) -> bool:
        return bool(
            self.semantic_id
            and self.purpose
            and self.inputs
            and self.outputs
            and self.clobbers
            and self.reads
            and self.writes
            and self.side_effects
            and self.invariants
        )


@dataclass(frozen=True)
class BasicBlock:
    module: str
    name: str
    routine: str | None
    purpose: str | None


@dataclass(frozen=True)
class LabelClassification:
    module: str
    name: str
    kind: LabelKind
    reason: str


@dataclass(frozen=True)
class MemoryReference:
    module: str
    source_file: str
    source_line: int
    symbol: str
    access: str
    semantic_id: str | None


@dataclass(frozen=True)
class CallEdge:
    module: str
    source_file: str
    source_line: int
    caller: str | None
    target: str
    kind: CallKind


@dataclass(frozen=True)
class AddressIdentity:
    kind: AddressKind
    address: int
    physical_page: int | None = None


@dataclass(frozen=True)
class Relocation:
    id: str
    module: str
    length: int
    assembled: AddressIdentity
    cartridge_staged: AddressIdentity | None
    runtime_destination: AddressIdentity


@dataclass(frozen=True)
class Evidence:
    id: str
    dimension: EvidenceDimension
    state: EvidenceState
    artifact: str | None
    sha256: str | None
    note: str | None = None


@dataclass(frozen=True)
class Exclusion:
    path: str
    reason: str


@dataclass(frozen=True)
class ModuleReference:
    id: str
    title: str
    source: str
    listing: str | None
    map_file: str | None
    binary: str | None
    source_files: tuple[SourceFile, ...]
    source_lines: tuple[SourceLine, ...]
    emitted_spans: tuple[EmittedSpan, ...]
    symbols: tuple[Symbol, ...]
    routines: tuple[Routine, ...]
    basic_blocks: tuple[BasicBlock, ...]
    label_classifications: tuple[LabelClassification, ...]
    memory_references: tuple[MemoryReference, ...]
    calls: tuple[CallEdge, ...]
    relocations: tuple[Relocation, ...]
    artifact_hashes: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class ProjectReference:
    title: str
    revision: str
    instruction_reference: str | None
    modules: tuple[ModuleReference, ...]
    evidence: tuple[Evidence, ...]
    exclusions: tuple[Exclusion, ...]
