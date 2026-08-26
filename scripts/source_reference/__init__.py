"""Generic lwasm source-reference generation for DOC-002."""

from .model import ProjectReference
from .normalize import build_project_reference

__all__ = ["ProjectReference", "build_project_reference"]
