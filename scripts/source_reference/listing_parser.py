"""Parse lwasm listings into source-line and emitted-byte relationships."""

from __future__ import annotations

import re
from pathlib import Path

from .model import EmittedSpan, SourceFile


SOURCE_MARKER_RE = re.compile(r"\(([^)]+)\):(\d{5})\s(.*)$")
EMITTED_PREFIX_RE = re.compile(r"^([0-9A-Fa-f]{4})\s+([0-9A-Fa-f]{2,16})?\s*$")
CONTINUATION_RE = re.compile(r"^\s{5}([0-9A-Fa-f]{2,16})\s*$")


class ListingParseError(ValueError):
    """Raised for an unsupported or ambiguous listing construct."""


def _resolve_display_path(display: str, source_files: tuple[SourceFile, ...]) -> str:
    suffix = display.strip().replace("\\", "/").lower()
    parts = [part for part in suffix.split("/") if part]
    relative_suffixes = {suffix}
    for root_name in ("src", "build"):
        if root_name in parts:
            relative_suffixes.add("/".join(parts[parts.index(root_name):]))
    if len(parts) >= 2:
        relative_suffixes.add("/".join(parts[-2:]))
    matches = [
        item.path
        for item in source_files
        if any(
            item.absolute_path.replace("\\", "/").lower().endswith(value)
            or item.path.lower().endswith(value)
            for value in relative_suffixes
        )
    ]
    unique = sorted(set(matches))
    if len(unique) != 1:
        raise ListingParseError(
            f"listing path {display!r} resolves to {len(unique)} source files: {unique}"
        )
    return unique[0]


def parse_listing(
    path: Path, module: str, source_files: tuple[SourceFile, ...]
) -> tuple[EmittedSpan, ...]:
    spans: list[EmittedSpan] = []
    last_index: int | None = None

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        marker = SOURCE_MARKER_RE.search(raw_line)
        if marker:
            prefix = raw_line[: marker.start()]
            emitted = EMITTED_PREFIX_RE.match(prefix)
            last_index = None
            if not emitted or not emitted.group(2):
                continue
            data = bytes.fromhex(emitted.group(2))
            spans.append(
                EmittedSpan(
                    module=module,
                    file=_resolve_display_path(marker.group(1), source_files),
                    line=int(marker.group(2)),
                    assembled_address=int(emitted.group(1), 16),
                    data=data,
                )
            )
            last_index = len(spans) - 1
            continue

        continuation = CONTINUATION_RE.match(raw_line)
        if continuation and last_index is not None:
            previous = spans[last_index]
            spans[last_index] = EmittedSpan(
                module=previous.module,
                file=previous.file,
                line=previous.line,
                assembled_address=previous.assembled_address,
                data=previous.data + bytes.fromhex(continuation.group(1)),
            )
            continue
        last_index = None

    if not spans:
        raise ListingParseError(f"no emitted source lines found in {path}")
    return tuple(spans)
