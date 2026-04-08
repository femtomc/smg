from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any

from smg.graph import SemGraph
from smg.model import Edge, NodeType, RelType


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _matches_prefix(name: str, prefix: str) -> bool:
    return name == prefix or name.startswith(prefix + ".")


def _edge_dict(edge: Edge) -> dict[str, str]:
    return {
        "source": edge.source,
        "rel": edge.rel.value,
        "target": edge.target,
    }


class ConceptConfigurationError(ValueError):
    pass


@dataclass
class Concept:
    name: str
    prefixes: list[str]
    sync_points: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.prefixes = _unique(self.prefixes)
        self.sync_points = _unique(self.sync_points)

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "kind": "concept",
            "name": self.name,
            "prefixes": self.prefixes,
        }
        if self.sync_points:
            data["sync_points"] = self.sync_points
        return data

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), separators=(",", ":"))

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Concept:
        return cls(
            name=str(data["name"]),
            prefixes=[str(prefix) for prefix in data.get("prefixes", [])],
            sync_points=[str(sync_point) for sync_point in data.get("sync_points", [])],
        )


@dataclass
class MaterializedConcept:
    concept: Concept
    anchors: list[str]
    members: set[str]


@dataclass
class ConceptSummary:
    name: str
    prefixes: list[str]
    anchors: list[str]
    members: int
    internal_edges: int
    cross_in: int
    cross_out: int
    sync_fan_out: int
    sync_density: float
    sync_asymmetry: float

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "prefixes": self.prefixes,
            "anchors": self.anchors,
            "members": self.members,
            "internal_edges": self.internal_edges,
            "cross_in": self.cross_in,
            "cross_out": self.cross_out,
            "sync_fan_out": self.sync_fan_out,
            "sync_density": round(self.sync_density, 6),
            "sync_asymmetry": round(self.sync_asymmetry, 6),
        }


@dataclass
class ConceptDependency:
    source: str
    target: str
    edge_count: int
    rels: dict[str, int]
    witnesses: list[dict[str, object]]
    allowed_sync: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "source": self.source,
            "target": self.target,
            "edge_count": self.edge_count,
            "rels": self.rels,
            "witnesses": self.witnesses,
            "allowed_sync": self.allowed_sync,
        }


@dataclass
class ConceptViolation:
    source: str
    target: str
    message: str
    witnesses: list[dict[str, object]]

    def to_dict(self) -> dict[str, object]:
        return {
            "source": self.source,
            "target": self.target,
            "message": self.message,
            "witnesses": self.witnesses,
        }


@dataclass
class ConceptAnalysis:
    declared: list[ConceptSummary]
    dependencies: list[ConceptDependency]
    violations: list[ConceptViolation]

    def to_dict(self) -> dict[str, object]:
        return {
            "declared": [summary.to_dict() for summary in self.declared],
            "dependencies": [dependency.to_dict() for dependency in self.dependencies],
            "violations": [violation.to_dict() for violation in self.violations],
        }


def materialize_concepts(graph: SemGraph, concepts: list[Concept]) -> tuple[list[MaterializedConcept], dict[str, str]]:
    package_or_module_names = [
        node.name for node in graph.iter_nodes() if node.type in {NodeType.PACKAGE, NodeType.MODULE}
    ]
    all_names = [node.name for node in graph.iter_nodes()]
    materialized: list[MaterializedConcept] = []
    owners: dict[str, str] = {}

    for concept in sorted(concepts, key=lambda item: item.name):
        anchors = _resolve_anchors(package_or_module_names, concept.prefixes)
        members = {name for name in all_names if any(_matches_prefix(name, anchor) for anchor in anchors)}
        for member in sorted(members):
            owner = owners.get(member)
            if owner is not None and owner != concept.name:
                raise ConceptConfigurationError(
                    f"concept overlap on {member!r}: {owner!r} and {concept.name!r} both claim it"
                )
            owners[member] = concept.name
        materialized.append(MaterializedConcept(concept=concept, anchors=anchors, members=members))

    return materialized, owners


def analyze_concepts(graph: SemGraph, concepts: list[Concept]) -> ConceptAnalysis:
    materialized, owners = materialize_concepts(graph, concepts)
    by_name = {item.concept.name: item for item in materialized}

    internal_edges: Counter[str] = Counter()
    cross_in: Counter[str] = Counter()
    cross_out: Counter[str] = Counter()
    touched_edges: Counter[str] = Counter()
    pair_edges: dict[tuple[str, str], list[Edge]] = defaultdict(list)
    pair_unsanctioned: dict[tuple[str, str], list[Edge]] = defaultdict(list)

    for edge in graph.all_edges():
        if edge.rel == RelType.CONTAINS:
            continue

        source_owner = owners.get(edge.source)
        target_owner = owners.get(edge.target)
        touched = {owner for owner in (source_owner, target_owner) if owner is not None}
        for owner in touched:
            touched_edges[owner] += 1

        if source_owner is None or target_owner is None:
            continue
        if source_owner == target_owner:
            internal_edges[source_owner] += 1
            continue

        cross_out[source_owner] += 1
        cross_in[target_owner] += 1
        pair = (source_owner, target_owner)
        pair_edges[pair].append(edge)
        if not _allowed_sync(edge, by_name[source_owner].concept, by_name[target_owner].concept):
            pair_unsanctioned[pair].append(edge)

    declared = [
        ConceptSummary(
            name=item.concept.name,
            prefixes=item.concept.prefixes,
            anchors=item.anchors,
            members=len(item.members),
            internal_edges=internal_edges[item.concept.name],
            cross_in=cross_in[item.concept.name],
            cross_out=cross_out[item.concept.name],
            sync_fan_out=len({target for source, target in pair_edges if source == item.concept.name}),
            sync_density=_sync_density(
                cross_in[item.concept.name] + cross_out[item.concept.name],
                touched_edges[item.concept.name],
            ),
            sync_asymmetry=_sync_asymmetry(item.concept.name, pair_edges),
        )
        for item in materialized
    ]

    dependencies: list[ConceptDependency] = []
    violations: list[ConceptViolation] = []
    for pair in sorted(pair_edges):
        edges = sorted(pair_edges[pair], key=lambda edge: (edge.source, edge.rel.value, edge.target))
        unsanctioned = sorted(pair_unsanctioned[pair], key=lambda edge: (edge.source, edge.rel.value, edge.target))
        dependencies.append(
            ConceptDependency(
                source=pair[0],
                target=pair[1],
                edge_count=len(edges),
                rels=dict(sorted(Counter(edge.rel.value for edge in edges).items())),
                witnesses=_edge_witnesses(unsanctioned or edges),
                allowed_sync=not unsanctioned,
            )
        )
        if unsanctioned:
            violations.append(
                ConceptViolation(
                    source=pair[0],
                    target=pair[1],
                    message=f"{len(unsanctioned)} unsanctioned cross-concept edge(s)",
                    witnesses=_edge_witnesses(unsanctioned),
                )
            )

    return ConceptAnalysis(
        declared=declared,
        dependencies=dependencies,
        violations=violations,
    )


def _resolve_anchors(package_or_module_names: list[str], prefixes: list[str]) -> list[str]:
    matches = sorted(
        {name for prefix in prefixes for name in package_or_module_names if _matches_prefix(name, prefix)},
        key=lambda name: (name.count("."), name),
    )
    anchors: list[str] = []
    for name in matches:
        if any(_matches_prefix(name, anchor) for anchor in anchors):
            continue
        anchors.append(name)
    return anchors


def _allowed_sync(edge: Edge, source: Concept, target: Concept) -> bool:
    return _matches_any_prefix(edge.source, source.sync_points) or _matches_any_prefix(edge.target, target.sync_points)


def _matches_any_prefix(name: str, prefixes: list[str]) -> bool:
    return any(_matches_prefix(name, prefix) for prefix in prefixes)


def _edge_witnesses(edges: list[Edge], limit: int = 5) -> list[dict[str, object]]:
    return [
        {
            "kind": "edge",
            "edges": [_edge_dict(edge)],
        }
        for edge in edges[:limit]
    ]


def _sync_density(cross_edges: int, touched_edges: int) -> float:
    if touched_edges == 0:
        return 0.0
    return cross_edges / touched_edges


def _sync_asymmetry(concept_name: str, pair_edges: dict[tuple[str, str], list[Edge]]) -> float:
    related = {target for source, target in pair_edges if source == concept_name} | {
        source for source, target in pair_edges if target == concept_name
    }
    if not related:
        return 0.0

    bidirectional = 0
    unidirectional = 0
    for other in sorted(related):
        outgoing = (concept_name, other) in pair_edges
        incoming = (other, concept_name) in pair_edges
        if outgoing and incoming:
            bidirectional += 1
        else:
            unidirectional += 1
    return unidirectional / max(1, bidirectional)
