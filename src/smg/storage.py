from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from smg.concepts import Concept
from smg.graph import SemGraph
from smg.model import Edge, Node
from smg.rules import Rule

SMG_DIR = ".smg"
GRAPH_FILE = "graph.jsonl"
RULES_FILE = "rules"
CONCEPTS_FILE = "concepts"


def find_root(start: Path | None = None) -> Path | None:
    """Walk up from `start` looking for a `.smg/` directory."""
    current = (start or Path.cwd()).resolve()
    while True:
        if (current / SMG_DIR).is_dir():
            return current
        parent = current.parent
        if parent == current:
            return None
        current = parent


def init_project(path: Path | None = None) -> Path:
    """Create .smg/ directory and empty graph file. Return the project root."""
    root = (path or Path.cwd()).resolve()
    smg_dir = root / SMG_DIR
    smg_dir.mkdir(exist_ok=True)
    graph_file = smg_dir / GRAPH_FILE
    if not graph_file.exists():
        graph_file.touch()
    _ensure_git_exclude(root, f"{SMG_DIR}/")
    return root


def _ensure_git_exclude(root: Path, pattern: str) -> None:
    """Best-effort local git ignore to keep .smg/ out of status noise."""
    exclude_file = root / ".git" / "info" / "exclude"
    if not exclude_file.exists():
        return

    try:
        existing = exclude_file.read_text()
    except OSError:
        return

    if pattern in {line.strip() for line in existing.splitlines()}:
        return

    prefix = "" if not existing or existing.endswith("\n") else "\n"
    try:
        exclude_file.write_text(f"{existing}{prefix}{pattern}\n")
    except OSError:
        return


def load_graph(root: Path) -> SemGraph:
    """Read .smg/graph.jsonl and return a SemGraph."""
    graph = SemGraph()
    graph_file = root / SMG_DIR / GRAPH_FILE
    if not graph_file.exists():
        return graph

    nodes: list[Node] = []
    edges: list[Edge] = []

    with open(graph_file) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            kind = record.get("kind")
            if kind == "node":
                nodes.append(Node.from_dict(record))
            elif kind == "edge":
                edges.append(Edge.from_dict(record))

    # Load nodes first, then edges (edges require nodes to exist)
    for node in nodes:
        graph.add_node(node)
    for edge in edges:
        graph.add_edge(edge)

    return graph


def save_graph(graph: SemGraph, root: Path) -> None:
    """Serialize graph to .smg/graph.jsonl atomically."""
    smg_dir = root / SMG_DIR
    graph_file = smg_dir / GRAPH_FILE

    # Atomic write: write to temp file, then rename
    fd, tmp_path = tempfile.mkstemp(dir=smg_dir, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            for node in graph.all_nodes():
                f.write(node.to_json() + "\n")
            for edge in graph.all_edges():
                f.write(edge.to_json() + "\n")
        os.replace(tmp_path, graph_file)
    except BaseException:
        # Clean up temp file on failure
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def load_rules(root: Path) -> list[Rule]:
    """Read .smg/rules and return a list of Rule objects."""
    rules_file = root / SMG_DIR / RULES_FILE
    if not rules_file.exists():
        return []
    rules: list[Rule] = []
    with open(rules_file) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rules.append(Rule.from_dict(json.loads(line)))
    return rules


def save_rules(rules: list[Rule], root: Path) -> None:
    """Serialize rules to .smg/rules atomically."""
    smg_dir = root / SMG_DIR
    rules_file = smg_dir / RULES_FILE

    lines = [r.to_json() for r in sorted(rules, key=lambda r: r.name)]

    fd, tmp_path = tempfile.mkstemp(dir=smg_dir, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            for line in lines:
                f.write(line + "\n")
        os.replace(tmp_path, rules_file)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def load_concepts(root: Path) -> list[Concept]:
    """Read .smg/concepts and return a list of concept declarations."""
    concepts_file = root / SMG_DIR / CONCEPTS_FILE
    if not concepts_file.exists():
        return []
    concepts: list[Concept] = []
    with open(concepts_file) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            concepts.append(Concept.from_dict(json.loads(line)))
    return concepts


def save_concepts(concepts: list[Concept], root: Path) -> None:
    """Serialize concepts to .smg/concepts atomically."""
    smg_dir = root / SMG_DIR
    concepts_file = smg_dir / CONCEPTS_FILE

    lines = [concept.to_json() for concept in sorted(concepts, key=lambda concept: concept.name)]

    fd, tmp_path = tempfile.mkstemp(dir=smg_dir, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            for line in lines:
                f.write(line + "\n")
        os.replace(tmp_path, concepts_file)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
