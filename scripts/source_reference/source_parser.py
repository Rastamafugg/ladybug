"""Read authored assembly files and resolve their static include trees."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from .model import SourceFile, SourceLine


INCLUDE_RE = re.compile(r'^\s*include\s+["\']([^"\']+)["\']', re.IGNORECASE)


class SourceParseError(ValueError):
    """Raised when a configured source or include cannot be resolved."""


def _canonical(path: Path, source_root: Path, artifact_root: Path) -> str:
    path = path.resolve()
    for prefix, label in ((source_root.resolve(), ""), (artifact_root.resolve(), "build")):
        try:
            relative = path.relative_to(prefix)
        except ValueError:
            continue
        value = relative.as_posix()
        return f"{label}/{value}" if label else value
    return path.as_posix()


def _resolve_include(name: str, parent: Path, include_dirs: tuple[Path, ...]) -> Path:
    candidates = (parent, *include_dirs)
    for directory in candidates:
        candidate = (directory / name).resolve()
        if candidate.is_file():
            return candidate
    raise SourceParseError(f"unresolved include {name!r} from {parent}")


def read_source_tree(
    top_level: Path,
    source_root: Path,
    artifact_root: Path,
    include_dirs: tuple[Path, ...] = (),
) -> tuple[tuple[SourceFile, ...], tuple[SourceLine, ...]]:
    """Return every source file and line reachable through quoted includes."""

    search_dirs = tuple(path.resolve() for path in include_dirs)
    pending = [top_level.resolve()]
    visited: set[Path] = set()
    files: list[SourceFile] = []
    lines: list[SourceLine] = []

    while pending:
        path = pending.pop()
        if path in visited:
            continue
        if not path.is_file():
            raise SourceParseError(f"source file does not exist: {path}")
        visited.add(path)
        raw = path.read_bytes()
        canonical = _canonical(path, source_root, artifact_root)
        files.append(
            SourceFile(
                path=canonical,
                absolute_path=str(path),
                sha256=hashlib.sha256(raw).hexdigest(),
            )
        )
        text = raw.decode("utf-8")
        for number, value in enumerate(text.splitlines(), 1):
            lines.append(SourceLine(file=canonical, number=number, text=value))
            match = INCLUDE_RE.match(value)
            if match:
                pending.append(_resolve_include(match.group(1), path.parent, search_dirs))

    files.sort(key=lambda item: item.path)
    lines.sort(key=lambda item: (item.file, item.number))
    return tuple(files), tuple(lines)
