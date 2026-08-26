#!/usr/bin/env python3
"""Verify source-reference coverage, freshness, anchors, links, and mutations."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from source_reference.coverage import evaluate_coverage
from source_reference.normalize import build_project_reference
from source_reference.render import render_project
from source_reference.verify import run_mutation_suite, verify_generated


def main() -> int:
    parser = argparse.ArgumentParser()
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--config", type=Path)
    source.add_argument("--fixture", type=Path)
    parser.add_argument("--generated-root", required=True, type=Path)
    parser.add_argument("--source-root", type=Path, default=Path.cwd())
    parser.add_argument("--artifact-root", type=Path)
    parser.add_argument("--wiki-root", type=Path)
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--mutation-suite", action="store_true")
    parser.add_argument("--max-errors", type=int, default=50)
    args = parser.parse_args()

    config_path = (args.fixture or args.config).resolve()
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if args.fixture:
        source_root = config_path.parent
        artifact_root = config_path.parent
    else:
        source_root = args.source_root.resolve()
        artifact_root = (args.artifact_root or source_root / "build").resolve()
    project = build_project_reference(config, source_root, artifact_root)
    coverage = evaluate_coverage(project, config["coverage"])
    if args.fixture:
        render_project(project, coverage, args.generated_root.resolve())
    result = verify_generated(project, config["coverage"], args.generated_root.resolve(), args.wiki_root)
    errors = list(result.errors)
    if args.mutation_suite:
        fixture_path = Path(__file__).parent / "fixtures" / "source-reference" / "project.json"
        mutation_errors = run_mutation_suite(fixture_path)
        errors.extend(mutation_errors)
        if not mutation_errors:
            print("source documentation mutation suite: PASS: 9/9 mutations rejected")
    if errors:
        unique_errors = sorted(set(errors))
        for error in unique_errors[: args.max_errors]:
            print(f"source documentation: FAIL: {error}")
        if len(unique_errors) > args.max_errors:
            print(
                f"source documentation: FAIL: {len(unique_errors) - args.max_errors} additional errors omitted"
            )
        return 1
    print(
        f"source documentation: PASS: {len(project.modules)} modules, "
        f"{coverage.documented_routines}/{coverage.required_routines} routines, "
        f"{coverage.classified_labels}/{coverage.global_labels} labels"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
