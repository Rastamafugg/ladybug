"""Apply explicit fail-closed documentation coverage policy."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .model import EvidenceDimension, EvidenceState, ProjectReference


@dataclass(frozen=True)
class CoverageResult:
    required_routines: int
    documented_routines: int
    global_labels: int
    classified_labels: int
    missing_routines: tuple[str, ...]
    unclassified_labels: tuple[str, ...]
    duplicate_semantic_ids: tuple[str, ...]
    missing_evidence: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return not (
            self.missing_routines
            or self.unclassified_labels
            or self.duplicate_semantic_ids
            or self.missing_evidence
        )


def evaluate_coverage(project: ProjectReference, policy: dict[str, Any]) -> CoverageResult:
    missing_routines: list[str] = []
    unclassified: list[str] = []
    semantic_ids: list[str] = []
    required_count = documented_count = label_count = classified_count = 0

    for module in project.modules:
        routines = {routine.name: routine for routine in module.routines}
        blocks = {block.name for block in module.basic_blocks if block.purpose}
        classifications = {
            item.name for item in module.label_classifications if item.reason.strip()
        }
        for routine in module.routines:
            required_count += 1
            if routine.contract_complete:
                documented_count += 1
                semantic_ids.append(routine.semantic_id)
            else:
                missing_routines.append(f"{module.id}:{routine.name}")
        for symbol in module.symbols:
            if symbol.file is None:
                continue
            label_count += 1
            if symbol.name in routines or symbol.name in blocks or symbol.name in classifications:
                classified_count += 1
            else:
                unclassified.append(f"{module.id}:{symbol.name}")

    duplicates = sorted({value for value in semantic_ids if semantic_ids.count(value) > 1})
    evidence_by_dimension = {
        evidence.dimension: evidence for evidence in project.evidence
    }
    missing_evidence: list[str] = []
    for value in policy.get("required_evidence", []):
        dimension = EvidenceDimension(str(value))
        evidence = evidence_by_dimension.get(dimension)
        if evidence is None or evidence.state is not EvidenceState.PASS or not evidence.sha256:
            missing_evidence.append(dimension.value)

    return CoverageResult(
        required_routines=required_count,
        documented_routines=documented_count,
        global_labels=label_count,
        classified_labels=classified_count,
        missing_routines=tuple(sorted(missing_routines)),
        unclassified_labels=tuple(sorted(unclassified)),
        duplicate_semantic_ids=tuple(duplicates),
        missing_evidence=tuple(sorted(missing_evidence)),
    )
