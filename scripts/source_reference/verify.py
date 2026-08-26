"""Independent checks over generated source-reference output."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
from copy import deepcopy
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from .coverage import evaluate_coverage
from .model import EvidenceDimension, EvidenceState, ProjectReference
from .normalize import build_project_reference
from .render import render_project


@dataclass(frozen=True)
class VerificationResult:
    errors: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return not self.errors


class _HTMLInventory(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: set[str] = set()
        self.hrefs: list[str] = []
        self.rows: dict[str, tuple[str, ...]] = {}
        self.row_hrefs: dict[str, tuple[str, ...]] = {}
        self._row_id: str | None = None
        self._cells: list[str] = []
        self._cell_text: list[str] | None = None
        self._active_row_hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if values.get("id"):
            self.ids.add(str(values["id"]))
        if tag == "tr":
            self._row_id = str(values.get("id")) if values.get("id") else None
            self._cells = []
            self._active_row_hrefs = []
        if tag == "td" and self._row_id is not None:
            self._cell_text = []
        if tag == "a" and values.get("href"):
            self.hrefs.append(str(values["href"]))
            if self._row_id is not None:
                self._active_row_hrefs.append(str(values["href"]))

    def handle_data(self, data: str) -> None:
        if self._cell_text is not None:
            self._cell_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "td" and self._cell_text is not None:
            self._cells.append("".join(self._cell_text).strip())
            self._cell_text = None
        if tag == "tr" and self._row_id is not None:
            self.rows[self._row_id] = tuple(self._cells)
            self.row_hrefs[self._row_id] = tuple(self._active_row_hrefs)
            self._row_id = None
            self._cells = []
            self._active_row_hrefs = []


class _VisibleTextInventory(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.segments: list[tuple[str, str | None]] = []
        self._href_stack: list[str | None] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            self._href_stack.append(dict(attrs).get("href"))

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._href_stack:
            self._href_stack.pop()

    def handle_data(self, data: str) -> None:
        if data.strip():
            self.segments.append((data, self._href_stack[-1] if self._href_stack else None))


def _slug(value: str) -> str:
    result = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return result or "item"


def _line_id(path: str, line: int) -> str:
    return f"line-{_slug(path)}-{line}"


def _symbol_id(module: str, name: str) -> str:
    return f"symbol-{_slug(module)}-{_slug(name)}"


def _routine_id(module: str, name: str) -> str:
    return f"routine-{_slug(module)}-{_slug(name)}"


_MNEMONICS = {
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
_MNEMONIC_PAGES = {
    "asla": "asl", "aslb": "asl", "lsl": "asl", "lsla": "asl", "lslb": "asl",
    "asra": "asr", "asrb": "asr", "bhs": "bcc", "blo": "bcs", "clra": "clr",
    "clrb": "clr", "coma": "com", "comb": "com", "deca": "dec", "decb": "dec",
    "inca": "inc", "incb": "inc", "lbhs": "lbcc", "lblo": "lbcs", "lsra": "lsr",
    "lsrb": "lsr", "nega": "neg", "negb": "neg", "rola": "rol", "rolb": "rol",
    "rora": "ror", "rorb": "ror", "swi2": "swi", "swi3": "swi", "tsta": "tst",
    "tstb": "tst",
}


def _instruction_mnemonic(source_text: str) -> str | None:
    code = source_text.split(";", 1)[0]
    tokens = re.findall(r"[A-Za-z][A-Za-z0-9]*", code)
    if not tokens:
        return None
    index = 0 if code[:1].isspace() else 1
    if index >= len(tokens):
        return None
    mnemonic = tokens[index].lower()
    return mnemonic if mnemonic in _MNEMONICS else None


def _inventory(path: Path) -> _HTMLInventory:
    parser = _HTMLInventory()
    parser.feed(path.read_text(encoding="utf-8"))
    return parser


def _controlled_term_errors(policy: dict[str, Any], wiki_root: Path | None) -> list[str]:
    terms = policy.get("controlled_terms", [])
    pages = [str(value) for value in policy.get("controlled_term_pages", [])]
    if not terms and not pages:
        return []
    if wiki_root is None:
        return ["controlled-term verification requires --wiki-root"]
    errors: list[str] = []
    names = [str(item.get("term", "")).strip() for item in terms]
    definitions = [str(item.get("definition_id", "")).strip() for item in terms]
    for value in sorted({name for name in names if not name or names.count(name) > 1}):
        errors.append(f"duplicate or blank controlled term: {value or '[blank]'}")
    for value in sorted({item for item in definitions if not item or definitions.count(item) > 1}):
        errors.append(f"duplicate or blank controlled definition: {value or '[blank]'}")
    glossary = wiki_root / "internal" / "implementation" / "glossary.html"
    glossary_inventory = _inventory(glossary) if glossary.is_file() else None
    if glossary_inventory is None:
        errors.append("missing controlled glossary")
    else:
        for definition in definitions:
            if definition not in glossary_inventory.ids:
                errors.append(f"missing glossary definition: {definition}")
    for relative in pages:
        path = wiki_root / relative
        if not path.is_file():
            errors.append(f"missing controlled-term page: {relative}")
            continue
        parser = _VisibleTextInventory()
        parser.feed(path.read_text(encoding="utf-8"))
        for term, definition in zip(names, definitions):
            first = next(
                ((text, href) for text, href in parser.segments if term.lower() in text.lower()),
                None,
            )
            if first is None:
                continue
            _text, href = first
            if not href or href.partition("#")[2] != definition:
                errors.append(f"controlled term not linked on first use: {relative}:{term}")
    return errors


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _policy_errors(project: ProjectReference, policy: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    semantic_ids: list[str] = []
    all_symbols = {symbol.name for module in project.modules for symbol in module.symbols}
    all_routines = {
        routine.name: routine for module in project.modules for routine in module.routines
    }
    source_contract_marker = str(policy.get("source_contract_marker", "")).strip()
    for module in project.modules:
        primary_source_text = {
            line.text for line in module.source_lines if line.file == module.source
        }
        if source_contract_marker:
            for routine in module.routines:
                expected_contract = (
                    f"; {source_contract_marker} contract {routine.name} "
                    f"profile={routine.profile}: {routine.purpose}"
                )
                if expected_contract not in primary_source_text:
                    errors.append(f"missing source contract mirror: {module.id}:{routine.name}")
            for profile in sorted({routine.profile for routine in module.routines if routine.profile}):
                profile_routines = [routine for routine in module.routines if routine.profile == profile]
                representative = profile_routines[0]
                for field, value in (
                    ("Inputs", representative.inputs),
                    ("Outputs", representative.outputs),
                    ("Clobbers", representative.clobbers),
                    ("Reads", representative.reads),
                    ("Writes", representative.writes),
                    ("Side effects", representative.side_effects),
                    ("Invariants", representative.invariants),
                ):
                    expected_profile = (
                        f"; {source_contract_marker} profile {profile} {field}: {value}"
                    )
                    if expected_profile not in primary_source_text:
                        errors.append(
                            f"missing source profile mirror: {module.id}:{profile}:{field}"
                        )
        routines = {routine.name for routine in module.routines}
        blocks = {block.name for block in module.basic_blocks if block.purpose}
        classifications = {
            item.name for item in module.label_classifications if item.reason.strip()
        }
        for routine in module.routines:
            if not routine.contract_complete:
                errors.append(f"missing routine contract: {module.id}:{routine.name}")
            else:
                semantic_ids.append(routine.semantic_id)
        for symbol in module.symbols:
            if symbol.file is None:
                continue
            if symbol.name not in routines and symbol.name not in blocks and symbol.name not in classifications:
                errors.append(f"unclassified global label: {module.id}:{symbol.name}")
    for value in sorted({item for item in semantic_ids if semantic_ids.count(item) > 1}):
        errors.append(f"duplicate semantic id: {value}")
    for name in policy.get("required_symbols", []):
        if name not in all_symbols:
            errors.append(f"missing required symbol: {name}")
    for name in policy.get("required_routines", []):
        routine = all_routines.get(str(name))
        if routine is None or not routine.contract_complete:
            errors.append(f"missing required routine: {name}")
    memory_items = policy.get("memory_structures", [])
    memory_ids = [str(item.get("id", "")) for item in memory_items]
    for item in memory_items:
        if not item.get("owner") or not item.get("semantic_id") or not item.get("symbols"):
            errors.append(f"missing memory owner or definition: {item.get('id', '[unnamed]')}")
    for value in sorted({item for item in memory_ids if not item or memory_ids.count(item) > 1}):
        errors.append(f"duplicate or blank memory id: {value or '[blank]'}")
    referenced_memory_symbols = {
        reference.symbol
        for module in project.modules
        for reference in module.memory_references
    }
    for item in memory_items:
        if not any(str(symbol) in referenced_memory_symbols for symbol in item.get("symbols", [])):
            errors.append(f"memory definition has no source references: {item.get('id', '[unnamed]')}")
    ownership_items = policy.get("ownership_inventory", [])
    required_categories = [str(value) for value in policy.get("required_ownership_categories", [])]
    category_values = [str(item.get("category", "")) for item in ownership_items]
    for category in required_categories:
        if category_values.count(category) != 1:
            errors.append(f"ownership category must occur exactly once: {category}")
    inventory_ids: list[str] = []
    declared_items: list[str] = []
    for item in ownership_items:
        inventory_id = str(item.get("id", ""))
        inventory_ids.append(inventory_id)
        if not inventory_id or not item.get("category") or not item.get("owner") or not item.get("semantic_id"):
            errors.append(f"incomplete ownership inventory: {inventory_id or '[unnamed]'}")
        values = [str(value) for value in item.get("items", [])]
        if not values:
            errors.append(f"empty ownership inventory: {inventory_id or '[unnamed]'}")
        declared_items.extend(values)
    for value in sorted({item for item in inventory_ids if not item or inventory_ids.count(item) > 1}):
        errors.append(f"duplicate or blank ownership inventory id: {value or '[blank]'}")
    for value in sorted({item for item in declared_items if declared_items.count(item) > 1}):
        errors.append(f"duplicate ownership item: {value}")
    for value in [str(item) for item in policy.get("required_ownership_items", [])]:
        if declared_items.count(value) != 1:
            errors.append(f"ownership item must occur exactly once: {value}")

    equ_definition = re.compile(
        r"^\s*([A-Za-z_][A-Za-z0-9_.]*)\s+equ\s+\$([0-9A-Fa-f]{4})\b",
        re.IGNORECASE,
    )
    for module in project.modules:
        for line in module.source_lines:
            match = equ_definition.match(line.text.split(";", 1)[0])
            if not match:
                continue
            address = int(match.group(2), 16)
            owners = []
            for item in ownership_items:
                if any(
                    int(str(bounds["start"]), 0) <= address <= int(str(bounds["end"]), 0)
                    for bounds in item.get("equ_ranges", [])
                ):
                    owners.append(str(item.get("id", "[unnamed]")))
            if len(owners) != 1:
                errors.append(
                    f"fixed address must have exactly one owner: {module.id}:{match.group(1)}:${address:04X}:{owners}"
                )

    data_inventory = [
        item for item in ownership_items if "data" in [str(value) for value in item.get("label_kinds", [])]
    ]
    for module in project.modules:
        for classification in module.label_classifications:
            if classification.kind.value == "data" and len(data_inventory) != 1:
                errors.append(
                    f"data label must have exactly one owner: {module.id}:{classification.name}"
                )
    relocation_inventory = [item for item in ownership_items if item.get("model") == "relocations"]
    if ownership_items and sum(len(module.relocations) for module in project.modules) and len(relocation_inventory) != 1:
        errors.append("copied modules must have exactly one relocation inventory")
    evidence_by_dimension = {item.dimension: item for item in project.evidence}
    for value in policy.get("required_evidence", []):
        dimension = EvidenceDimension(str(value))
        evidence = evidence_by_dimension.get(dimension)
        if evidence is None or evidence.state is not EvidenceState.PASS or not evidence.sha256:
            errors.append(f"missing or non-passing evidence: {dimension.value}")
    evidence_ids = {item.id for item in project.evidence if item.state is EvidenceState.PASS}
    project_lines = {
        (module.id, line.file, line.number)
        for module in project.modules
        for line in module.source_lines
    }
    project_routines = {
        (module.id, routine.name)
        for module in project.modules
        for routine in module.routines
    }
    required_scenarios = [str(value) for value in policy.get("required_scenarios", [])]
    scenarios = policy.get("scenarios", [])
    scenario_ids = [str(scenario.get("id", "")) for scenario in scenarios]
    for value in sorted({item for item in scenario_ids if not item or scenario_ids.count(item) > 1}):
        errors.append(f"duplicate or blank scenario id: {value or '[blank]'}")
    for scenario_id in required_scenarios:
        if scenario_ids.count(scenario_id) != 1:
            errors.append(f"required scenario must occur exactly once: {scenario_id}")
    for scenario in scenarios:
        scenario_id = scenario.get("id", "[unnamed]")
        for field in ("criterion", "behavior", "state", "module", "routine", "verifier"):
            if not scenario.get(field):
                errors.append(f"missing scenario field {field}: {scenario_id}")
        module_id = str(scenario.get("module", ""))
        routine = str(scenario.get("routine", ""))
        if (module_id, routine) not in project_routines:
            errors.append(f"missing scenario routine: {scenario_id}:{module_id}:{routine}")
        memories = [str(value) for value in scenario.get("memory", [])]
        if not memories or any(value not in memory_ids for value in memories):
            errors.append(f"missing scenario memory: {scenario_id}")
        sources = scenario.get("source", [])
        if not sources:
            errors.append(f"missing scenario source: {scenario_id}")
        for source in sources:
            key = (str(source.get("module", "")), str(source.get("file", "")), int(source.get("line", 0)))
            if key not in project_lines:
                errors.append(f"missing scenario source line: {scenario_id}:{key[0]}:{key[1]}:{key[2]}")
        evidence_values = scenario.get("evidence", [])
        if isinstance(evidence_values, str):
            evidence_values = [evidence_values]
        if not evidence_values or any(value not in evidence_ids for value in evidence_values):
            errors.append(f"missing scenario evidence: {scenario_id}")
    return errors


def verify_generated(
    project: ProjectReference,
    policy: dict[str, Any],
    generated_root: Path,
    external_root: Path | None = None,
) -> VerificationResult:
    errors = _policy_errors(project, policy)
    errors.extend(_controlled_term_errors(policy, external_root))
    manifest_path = generated_root / "manifest.json"
    if not manifest_path.is_file():
        return VerificationResult(tuple(errors + ["missing generated manifest.json"]))
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return VerificationResult(tuple(errors + [f"invalid manifest: {exc}"]))
    if manifest.get("revision") != project.revision:
        errors.append("stale generated revision")
    expected_evidence = [
        {
            "id": item.id,
            "dimension": item.dimension.value,
            "state": item.state.value,
            "artifact": item.artifact,
            "sha256": item.sha256,
            "note": item.note,
        }
        for item in project.evidence
    ]
    if manifest.get("evidence") != expected_evidence:
        errors.append("stale generated evidence hashes")
    exclusion_paths = [item.path for item in project.exclusions]
    for value in sorted(
        {path for path in exclusion_paths if not path or exclusion_paths.count(path) > 1}
    ):
        errors.append(f"duplicate or blank exclusion path: {value or '[blank]'}")
    for item in project.exclusions:
        if not item.reason.strip():
            errors.append(f"missing exclusion reason: {item.path or '[blank]'}")
    expected_exclusions = [
        {"path": item.path, "reason": item.reason} for item in project.exclusions
    ]
    if manifest.get("exclusions") != expected_exclusions:
        errors.append("stale generated exclusions")
    manifest_modules = {item.get("id"): item for item in manifest.get("modules", [])}

    inventories: dict[Path, _HTMLInventory] = {}
    for module in project.modules:
        page = generated_root / f"module-{_slug(module.id)}.html"
        if not page.is_file():
            errors.append(f"missing module page: {module.id}")
            continue
        inventory = _inventory(page)
        inventories[Path(os.path.abspath(str(page)))] = inventory
        spans_by_line = {(item.file, item.line): item for item in module.emitted_spans}
        for line in module.source_lines:
            expected = _line_id(line.file, line.number)
            if expected not in inventory.ids:
                errors.append(f"missing source anchor: {module.id}:{line.file}:{line.number}")
                continue
            cells = inventory.rows.get(expected, ())
            if len(cells) != 8:
                errors.append(f"invalid source row: {module.id}:{line.file}:{line.number}")
                continue
            span = spans_by_line.get((line.file, line.number))
            if span is None:
                if cells[2] != "non-emitting":
                    errors.append(f"missing non-emitting marker: {module.id}:{line.file}:{line.number}")
                continue
            if not cells[1] or not cells[2] or cells[2] == "non-emitting":
                errors.append(f"missing emitted address or bytes: {module.id}:{line.file}:{line.number}")
            mnemonic = _instruction_mnemonic(line.text)
            if mnemonic is not None and project.instruction_reference:
                expected_href = (project.instruction_reference or "").replace(
                    "{mnemonic}", _MNEMONIC_PAGES.get(mnemonic, mnemonic)
                )
                if expected_href not in inventory.row_hrefs.get(expected, ()):
                    errors.append(f"missing instruction link: {module.id}:{line.file}:{line.number}:{mnemonic}")
                if not cells[4] or cells[4] == "[module]":
                    errors.append(f"missing instruction owner: {module.id}:{line.file}:{line.number}")
        for symbol in module.symbols:
            if symbol.file is not None and _symbol_id(module.id, symbol.name) not in inventory.ids:
                errors.append(f"missing symbol anchor: {module.id}:{symbol.name}")
        for routine in module.routines:
            if _routine_id(module.id, routine.name) not in inventory.ids:
                errors.append(f"missing routine anchor: {module.id}:{routine.name}")
        manifest_module = manifest_modules.get(module.id)
        if not manifest_module:
            errors.append(f"missing manifest module: {module.id}")
            continue
        expected_sources = {item.path: item.sha256 for item in module.source_files}
        actual_sources = {
            item.get("path"): item.get("sha256") for item in manifest_module.get("source_files", [])
        }
        if actual_sources != expected_sources:
            errors.append(f"stale source hashes: {module.id}")
        expected_artifacts = dict(module.artifact_hashes)
        actual_artifacts = {
            item.get("path"): item.get("sha256")
            for item in manifest_module.get("artifact_hashes", [])
        }
        if actual_artifacts != expected_artifacts:
            errors.append(f"stale artifact hashes: {module.id}")

    existence: dict[Path, bool] = {}
    for page in generated_root.glob("*.html"):
        page_key = Path(os.path.abspath(str(page)))
        if page_key not in inventories:
            inventories[page_key] = _inventory(page)
        inventory = inventories[page_key]
        for href in inventory.hrefs:
            if href.startswith(("http://", "https://", "mailto:")):
                continue
            path_text, _, fragment = href.partition("#")
            if external_root is not None and path_text.startswith("../../wiki/"):
                target = Path(
                    os.path.abspath(
                        str(external_root / path_text[len("../../wiki/"):])
                    )
                )
            else:
                target = (
                    Path(os.path.abspath(str(page.parent / path_text))) if path_text else page_key
                )
            if target not in existence:
                existence[target] = target.is_file()
            if not existence[target]:
                errors.append(f"broken link: {page.name} -> {href}")
                continue
            if fragment and target.suffix.lower() == ".html":
                if target not in inventories:
                    inventories[target] = _inventory(target)
                target_inventory = inventories[target]
                if fragment not in target_inventory.ids:
                    errors.append(f"broken fragment: {page.name} -> {href}")

    return VerificationResult(tuple(sorted(set(errors))))


def run_mutation_suite(fixture_config_path: Path) -> tuple[str, ...]:
    """Require nine discriminating fixture mutations to be rejected."""

    config = json.loads(fixture_config_path.read_text(encoding="utf-8"))
    root = fixture_config_path.parent.resolve()
    project = build_project_reference(config, root, root)
    coverage = evaluate_coverage(project, config["coverage"])
    failures: list[str] = []
    with tempfile.TemporaryDirectory(prefix="source-reference-mutations-") as temp_text:
        clean_root = Path(temp_text) / "clean"
        render_project(project, coverage, clean_root)
        clean = verify_generated(project, config["coverage"], clean_root)
        if not clean.passed:
            return ("fixture baseline failed before mutations: " + "; ".join(clean.errors),)

        policy_mutations = {
            "missing-routine": {"required_routines": ["not_present"]},
            "missing-symbol": {"required_symbols": ["not_present"]},
            "missing-memory-owner": {
                "memory_structures": [{"id": "broken", "owner": "", "semantic_id": ""}]
            },
            "missing-scenario-evidence": {
                "scenarios": [{"id": "broken", "evidence": "not_present"}]
            },
        }
        for name, addition in policy_mutations.items():
            mutated = deepcopy(config["coverage"])
            mutated.update(addition)
            errors = _policy_errors(project, mutated)
            if not errors:
                failures.append(f"mutation was accepted: {name}")

        missing_scenario = deepcopy(config["coverage"])
        missing_scenario["scenarios"] = []
        if not _policy_errors(project, missing_scenario):
            failures.append("mutation was accepted: missing-required-scenario")

        stale_root = Path(temp_text) / "stale"
        shutil.copytree(clean_root, stale_root)
        manifest_path = stale_root / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["revision"] = "stale"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        if verify_generated(project, config["coverage"], stale_root).passed:
            failures.append("mutation was accepted: stale-revision")

        for name, artifact in (
            ("stale-listing", "module_a.lst"),
            ("stale-map", "module_a.map"),
        ):
            case_root = Path(temp_text) / name
            shutil.copytree(root, case_root)
            artifact_path = case_root / artifact
            artifact_path.write_text(
                artifact_path.read_text(encoding="utf-8") + "\n",
                encoding="utf-8",
            )
            mutated_project = build_project_reference(config, case_root, case_root)
            if verify_generated(mutated_project, config["coverage"], clean_root).passed:
                failures.append(f"mutation was accepted: {name}")

        link_root = Path(temp_text) / "broken-link"
        shutil.copytree(clean_root, link_root)
        index_path = link_root / "index.html"
        index_path.write_text(
            index_path.read_text(encoding="utf-8") + '<a href="missing.html">broken</a>',
            encoding="utf-8",
        )
        if verify_generated(project, config["coverage"], link_root).passed:
            failures.append("mutation was accepted: broken-link")
    return tuple(failures)
