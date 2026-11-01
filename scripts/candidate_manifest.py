#!/usr/bin/env python3
"""Write and verify deterministic SHA-256 lists for candidate packages."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import sys
import tempfile
import unicodedata
from typing import Iterable


SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")


class ManifestError(ValueError):
    """Raised when a package path or checksum manifest is invalid."""


def _root_path(root_arg: str | Path) -> Path:
    try:
        root = Path(root_arg).resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise ManifestError(f"package root is unavailable: {root_arg}") from exc
    if not root.is_dir():
        raise ManifestError(f"package root is not a directory: {root}")
    return root


def _relative_name(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ManifestError(f"{label} must be a non-empty relative path")
    if "\\" in value or any(unicodedata.category(char) in {"Cc", "Cs"} for char in value):
        raise ManifestError(f"{label} contains a backslash or control character: {value!r}")
    if value.startswith("/") or re.match(r"\A[A-Za-z]:", value):
        raise ManifestError(f"{label} must not be absolute: {value!r}")

    path = PurePosixPath(value)
    if path.as_posix() != value or any(part in ("", ".", "..") for part in value.split("/")):
        raise ManifestError(f"{label} is not a normalized package-relative path: {value!r}")
    return value


def _inside_root(root: Path, relative_name: str, label: str, *, strict: bool) -> Path:
    candidate = root.joinpath(*PurePosixPath(relative_name).parts)
    try:
        resolved = candidate.resolve(strict=strict)
    except (OSError, RuntimeError) as exc:
        raise ManifestError(f"{label} is unavailable: {relative_name}") from exc
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ManifestError(f"{label} escapes the package root: {relative_name}") from exc
    return resolved


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise ManifestError(f"cannot read package file: {path}") from exc
    return digest.hexdigest()


def _load_file_list(root: Path, files_json_name: str) -> list[str]:
    files_json_path = _inside_root(root, files_json_name, "path-list JSON", strict=True)
    if not files_json_path.is_file():
        raise ManifestError(f"path-list JSON is not a file: {files_json_name}")
    try:
        paths = json.loads(files_json_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ManifestError(f"cannot parse UTF-8 path-list JSON: {files_json_name}") from exc
    if not isinstance(paths, list):
        raise ManifestError("path-list JSON must contain an array of relative paths")

    normalized = [_relative_name(value, "listed path") for value in paths]
    if len(set(normalized)) != len(normalized):
        raise ManifestError("path-list JSON contains duplicate paths")
    if not normalized:
        raise ManifestError("path-list JSON must contain at least one file")
    return sorted(normalized)


def _validate_listed_files(root: Path, names: Iterable[str], manifest_name: str) -> list[tuple[str, Path]]:
    manifest_resolved = _inside_root(root, manifest_name, "manifest path", strict=False)
    resolved_files: list[tuple[str, Path]] = []
    for name in names:
        path = _inside_root(root, name, "listed file", strict=True)
        if not path.is_file():
            raise ManifestError(f"listed path is not a regular file: {name}")
        if path == manifest_resolved:
            raise ManifestError("a manifest must not list itself")
        resolved_files.append((name, path))
    return resolved_files


def write_manifest(root_arg: str | Path, manifest_arg: str, files_json_arg: str) -> int:
    """Create an atomic, sorted, LF-only sha256sum-compatible manifest."""
    root = _root_path(root_arg)
    manifest_name = _relative_name(manifest_arg, "manifest path")
    files_json_name = _relative_name(files_json_arg, "path-list JSON path")
    manifest_path = _inside_root(root, manifest_name, "manifest path", strict=False)
    if manifest_path.exists() and manifest_path.is_dir():
        raise ManifestError(f"manifest target is a directory: {manifest_name}")
    if Path(root, *PurePosixPath(manifest_name).parts).is_symlink():
        raise ManifestError(f"manifest target must not be a symlink: {manifest_name}")

    names = _load_file_list(root, files_json_name)
    files = _validate_listed_files(root, names, manifest_name)
    output = b"".join(
        f"{_file_sha256(path)}  {name}\n".encode("utf-8")
        for name, path in files
    )

    parent = manifest_path.parent
    if not parent.is_dir():
        raise ManifestError(f"manifest parent directory does not exist: {manifest_name}")
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", prefix=f".{manifest_path.name}.", suffix=".tmp",
            dir=parent, delete=False,
        ) as stream:
            temp_path = Path(stream.name)
            stream.write(output)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_path, manifest_path)
    except OSError as exc:
        raise ManifestError(f"cannot write manifest: {manifest_name}") from exc
    finally:
        if temp_path is not None and temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass
    return len(files)


def _parse_manifest(manifest_bytes: bytes) -> list[tuple[str, str]]:
    if not manifest_bytes:
        raise ManifestError("manifest is empty")
    if b"\r" in manifest_bytes:
        raise ManifestError("manifest contains CR bytes; only LF line endings are allowed")
    if not manifest_bytes.endswith(b"\n"):
        raise ManifestError("manifest must end each record with LF")

    records: list[tuple[str, str]] = []
    seen: set[str] = set()
    for line_number, line in enumerate(manifest_bytes[:-1].split(b"\n"), start=1):
        if len(line) < 67 or line[64:66] != b"  ":
            raise ManifestError(f"malformed checksum record on line {line_number}")
        digest_bytes = line[:64]
        if not SHA256_RE.fullmatch(digest_bytes.decode("ascii", errors="replace")):
            raise ManifestError(f"invalid lowercase SHA-256 on line {line_number}")
        try:
            name = line[66:].decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ManifestError(f"path is not UTF-8 on line {line_number}") from exc
        name = _relative_name(name, f"path on line {line_number}")
        if name in seen:
            raise ManifestError(f"duplicate path in manifest: {name}")
        seen.add(name)
        records.append((digest_bytes.decode("ascii"), name))
    if not records:
        raise ManifestError("manifest has no checksum records")
    if [name for _, name in records] != sorted(name for _, name in records):
        raise ManifestError("manifest paths are not sorted")
    return records


def verify_manifest(root_arg: str | Path, manifest_arg: str) -> int:
    """Verify a strict LF-only manifest without changing package files."""
    root = _root_path(root_arg)
    manifest_name = _relative_name(manifest_arg, "manifest path")
    manifest_path = _inside_root(root, manifest_name, "manifest path", strict=True)
    if not manifest_path.is_file():
        raise ManifestError(f"manifest is not a regular file: {manifest_name}")
    try:
        records = _parse_manifest(manifest_path.read_bytes())
    except OSError as exc:
        raise ManifestError(f"cannot read manifest: {manifest_name}") from exc

    for expected_digest, name in records:
        path = _inside_root(root, name, "listed file", strict=True)
        if path == manifest_path:
            raise ManifestError("a manifest must not list itself")
        if not path.is_file():
            raise ManifestError(f"listed path is not a regular file: {name}")
        actual_digest = _file_sha256(path)
        if actual_digest != expected_digest:
            raise ManifestError(f"SHA-256 mismatch: {name}")
    return len(records)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="operation", required=True)

    write_parser = subparsers.add_parser("write", help="write a candidate-package checksum manifest")
    write_parser.add_argument("--root", required=True, help="candidate package root")
    write_parser.add_argument("--manifest", required=True, help="manifest path relative to the package root")
    write_parser.add_argument("--files-json", required=True, help="UTF-8 JSON array of package-relative file paths")

    verify_parser = subparsers.add_parser("verify", help="verify a candidate-package checksum manifest")
    verify_parser.add_argument("--root", required=True, help="candidate package root")
    verify_parser.add_argument("--manifest", required=True, help="manifest path relative to the package root")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.operation == "write":
            count = write_manifest(args.root, args.manifest, args.files_json)
            print(f"WROTE {args.manifest}: {count} file(s), LF-only")
        else:
            count = verify_manifest(args.root, args.manifest)
            print(f"PASS {args.manifest}: {count} file(s)")
    except ManifestError as exc:
        print(f"candidate-manifest: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
