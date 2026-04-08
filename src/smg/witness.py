"""Helpers for minimal violation witnesses and legacy projections."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Witness:
    """One minimal counterexample for a rule violation."""

    kind: str
    edges: list[dict[str, Any]] | None = None
    nodes: list[str] | None = None
    cycle: list[str] | None = None
    subject: str | None = None
    assertion: str | None = None
    facts: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {"kind": self.kind}
        if self.edges:
            data["edges"] = self.edges
        if self.nodes:
            data["nodes"] = self.nodes
        if self.cycle:
            data["cycle"] = self.cycle
        if self.subject is not None:
            data["subject"] = self.subject
        if self.assertion is not None:
            data["assertion"] = self.assertion
        if self.facts:
            data["facts"] = self.facts
        return data


def edge_witness(edge: dict[str, Any]) -> Witness:
    return Witness(kind="edge", edges=[edge])


def node_witness(node: str) -> Witness:
    return Witness(kind="node", nodes=[node])


def cycle_witness(cycle: list[str]) -> Witness:
    return Witness(kind="cycle", cycle=cycle)


def predicate_witness(subject: str, assertion: str, facts: dict[str, Any]) -> Witness:
    return Witness(kind="predicate", subject=subject, assertion=assertion, facts=facts)
