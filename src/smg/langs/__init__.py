from __future__ import annotations

import sys
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from smg.model import Edge, Node

if TYPE_CHECKING:
    from smg.metrics import BranchMap


@dataclass
class ExtractResult:
    nodes: list[Node] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)


@runtime_checkable
class LanguageExtractor(Protocol):
    extensions: list[str]
    branch_map: BranchMap

    def extract(self, source: bytes, file_path: str, module_name: str) -> ExtractResult: ...


# Extension -> extractor mapping, populated by register()
REGISTRY: dict[str, LanguageExtractor] = {}


def register(extractor: LanguageExtractor) -> None:
    for ext in extractor.extensions:
        REGISTRY[ext] = extractor


def get_extractor(extension: str) -> LanguageExtractor | None:
    return REGISTRY.get(extension)


def load_extractors() -> None:
    """Import all lang modules to trigger registration, warning on failures."""
    _extractor_modules = ("python", "javascript", "zig", "c")
    for name in _extractor_modules:
        try:
            __import__(f"smg.langs.{name}")
        except ImportError as exc:
            print(f"smg: failed to load extractor '{name}': {exc}", file=sys.stderr)
    if not REGISTRY:
        print(
            "smg: no extractors loaded — install dependencies with: uv pip install smg[scan]",
            file=sys.stderr,
        )
