#!/usr/bin/env python3
"""Generate disposable lwasm source-reference HTML."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from source_reference.coverage import evaluate_coverage
from source_reference.normalize import build_project_reference
from source_reference.render import render_project


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--source-root", type=Path, default=Path.cwd())
    parser.add_argument("--artifact-root", type=Path)
    args = parser.parse_args()

    config = json.loads(args.config.read_text(encoding="utf-8"))
    source_root = args.source_root.resolve()
    artifact_root = (args.artifact_root or source_root / "build").resolve()
    project = build_project_reference(config, source_root, artifact_root)
    coverage = evaluate_coverage(project, config["coverage"])
    render_project(project, coverage, args.output.resolve())
    print(
        f"source reference: {len(project.modules)} modules, "
        f"{sum(len(module.source_lines) for module in project.modules)} source lines, "
        f"coverage={'pass' if coverage.passed else 'incomplete'}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
