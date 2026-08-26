"""Stable IDs and links for generated and semantic documentation."""

from __future__ import annotations

import re


def slug(value: str) -> str:
    result = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return result or "item"


def module_page(module_id: str) -> str:
    return f"module-{slug(module_id)}.html"


def source_line_id(path: str, line: int) -> str:
    return f"line-{slug(path)}-{line}"


def symbol_id(module_id: str, name: str) -> str:
    return f"symbol-{slug(module_id)}-{slug(name)}"


def routine_id(module_id: str, name: str) -> str:
    return f"routine-{slug(module_id)}-{slug(name)}"
